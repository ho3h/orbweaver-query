"""Matched candidate-restricted Quail/vLLM diagnostic, pinned to one upstream revision.

This uses upstream inference engines; it is not an Orbweaver speedup mechanism.
The public vLLM planner rejects Apply, so the reference lowers the same full join
to upstream RequestExecution with the existing candidate-pair input port.
"""

import argparse
from collections import Counter
from dataclasses import replace
from hashlib import sha256
from importlib.metadata import version
import json
import math
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import time
import traceback
from types import SimpleNamespace

import quail
from quail.backends.base import BackendExecutionContext
from quail.backends.request import RequestBackend, execute_request_graph
from quail.backends.vllm import VLLMEngine
from quail.execution.execute import execute_query
from quail.execution.runner import ExecutionContext, ForeignRuntime
from quail.physical import AiJoin, Foreign, PortRef, Project, RequestExecution, RequestJoinSpec, Scan
from quail.physical.base import input_ports
from quail.planner.plan import PhysicalPlan
from quail.specs import QWEN3_4B_FP8

from orbweaver_query.quail import QuailPairs

PIN = "41b883b838687cfbf018080f068f3e81bf2f8e64"
BACKEND = "orbweaver_vllm_reference"
PREDICATE = ("Using only the scientific abstract {1}, does it support claim {0}? "
             "Answer FALSE if it contradicts the claim or provides insufficient evidence.")
SOURCE_INPUT_SHA = "678d0fb5e2c3f23a6d629bd1f12c222c9eb1c066090697c532cb7b6db9d2c8a2"
SOURCE_TRUTH_SHA = "b939a0781cb72d597509f40e4ce6dca441340f5d02323ceb7d7399fba109e20c"


def sha(path):
    h = sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(2**20):
            h.update(chunk)
    return h.hexdigest()


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def read(path):
    return json.loads(Path(path).read_text())


def pinned_source():
    source = Path(quail.__file__).resolve().parents[1]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if commit != PIN or subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=source, text=True).strip():
        raise ValueError("Use a clean checkout of the pinned Quail source")
    return commit


class PinnedTokenVLLMEngine(VLLMEngine):
    """Keep upstream tuning, pin model/tokenizer revision and accept exact tokens."""

    kind = BACKEND

    def llm_kwargs(self, spec):
        return {**super().llm_kwargs(spec), "revision": spec.revision,
                "tokenizer_revision": spec.revision, "dtype": "bfloat16",
                "kv_cache_dtype": "auto"}

    def boot(self, spec, allowed_ids):
        state, boot = super().boot(spec, allowed_ids)
        state["client"].accepts_text = False
        return state, boot


def reference_plan(bound):
    """Lower one full two-document join, preserving Quail's anchor and token parts."""
    query = bound.query
    plan = query.plan()
    if plan.backend != "quail" or plan.workers != 1:
        raise ValueError("Reference lowering requires a single-GPU Quail plan")
    foreign, = plan.graph.nodes_by_type(Foreign.type_name)
    join, = plan.graph.nodes_by_type(AiJoin.type_name)
    project, = plan.graph.nodes_by_type(Project.type_name)
    scans = plan.graph.nodes_by_type(Scan.type_name)
    stage, = join.stages
    if (len(scans) != 2 or len(plan.nodes) != 5 or stage.semantics != "full"
            or stage.pairs_from != foreign.node_id):
        raise ValueError("Reference lowering supports only the captured full pair join")
    prompt = query.logical.operators().joins[0].prompt
    if tuple(plan.settings["pre_ids"]) != tuple(prompt.preamble_token_ids):
        raise ValueError("Logical and physical preamble tokens differ")
    labels = tuple((alias, tuple(label)) for alias, label, _ in prompt.label_token_ids)
    frames = tuple((alias, tuple(frame)) for alias, _, frame in prompt.label_token_ids)
    if (dict(frames)[stage.anchor] != stage.frame_token_ids
            or tuple((alias, label) for alias, label in labels if alias in stage.partners)
            != stage.label_token_ids or tuple(prompt.tail_token_ids) != stage.tail_token_ids):
        raise ValueError("Logical and physical join token parts differ")
    aliases = tuple(scan.alias for scan in scans)
    spec = RequestJoinSpec(written_pos=stage.written_pos, aliases=aliases, outer_aliases=aliases,
        anchor=stage.anchor, semantics="full", selectivity=stage.selectivity,
        label_token_ids=labels, frame_token_ids=frames, tail_token_ids=stage.tail_token_ids)
    request = RequestExecution(node_id="request-model", inputs=input_ports(tuple(
        [PortRef(scan.node_id, f"ids:{scan.alias}") for scan in scans]
        + [PortRef(foreign.node_id, f"pairs:{foreign.written_pos}")])),
        backend_name=BACKEND, aliases=aliases,
        preamble_token_ids=tuple(prompt.preamble_token_ids), joins=(spec,))
    if BACKEND not in query.session.registry.backends:
        query.session.registry.register_backend(RequestBackend(
            name=BACKEND, engine=PinnedTokenVLLMEngine(), filter_submission="operator-at-a-time"))
    lowered = PhysicalPlan(model=plan.model, device=plan.device, workers=1, backend=BACKEND,
        nodes=(*scans, foreign, request, replace(project, inputs=input_ports((
            PortRef(request.node_id, f"join_answers:{stage.written_pos}"),)))),
        settings={"true_ids": plan.settings["true_ids"], "false_ids": plan.settings["false_ids"],
                  "filter_submission": "operator-at-a-time", "join_submission": "anchor-major",
                  "order_rule": "matched_quail_anchor"})
    lowered.graph.validate(runtime_keys=set(query.session.registry.runtimes))
    lowered.graph.validate_backend(BACKEND)
    return lowered


def pair_inputs(bound):
    """Prepare actual Foreign pairs, document tokens and stable application IDs."""
    plan = bound.query.plan()
    foreign, = plan.graph.nodes_by_type(Foreign.type_name)
    request = bound.query._prepare_physical()
    scans = plan.graph.nodes_by_type(Scan.type_name)
    documents = {scan.alias: request.inputs[scan.input_id].documents for scan in scans}
    tables = request.column_tables()
    inputs = {port.name: list(range(len(documents[port.source.port.split(":")[1]])))
              for port in foreign.inputs}
    result = ForeignRuntime().execute(foreign, inputs, ExecutionContext(
        runtimes=bound.query.session.registry.runtimes, sources=request.relations,
        functions=bound.query.session.registry.functions))
    pairs = result.outputs[f"pairs:{foreign.written_pos}"]
    return request, documents, tables, pairs


def prompt_audit(bound):
    """Per-pair hashes of the exact segmented tokens consumed by Quail's join."""
    _, documents, tables, pairs = pair_inputs(bound)
    join, = bound.query.plan().graph.nodes_by_type(AiJoin.type_name)
    stage, = join.stages
    prompt = bound.query.logical.operators().joins[0].prompt
    partner, = stage.partners
    labels = dict(stage.label_token_ids)
    records = []
    for left, right in zip(pairs["l"].to_pylist(), pairs["r"].to_pylist()):
        ids = {"l": left, "r": right}
        tokens = (list(prompt.preamble_token_ids) + list(documents[stage.anchor][ids[stage.anchor]])
                  + list(stage.frame_token_ids) + list(labels[partner])
                  + list(documents[partner][ids[partner]]) + list(stage.tail_token_ids))
        records.append(dict(head=tables["l"]["id"][left].as_py(),
            target=tables["r"]["id"][right].as_py(), tokens=len(tokens),
            token_sha256=digest([int(token) for token in tokens])))
    records.sort(key=lambda row: (row["head"], row["target"]))
    if {(row["head"], row["target"]) for row in records} != set(bound.candidates.candidate_pairs):
        raise ValueError("Physical candidate domain differs from captured application pairs")
    if len(records) != len(bound.candidates.candidate_pairs):
        raise ValueError("Physical candidate domain contains duplicates")
    return dict(anchor=stage.anchor, pairs=records,
                requested_tokens=sum(row["tokens"] for row in records),
                max_prompt_tokens=max(row["tokens"] for row in records))


def tokenizer(path):
    from gigatoken import Tokenizer
    encoder = Tokenizer(str(path))
    return lambda text: [int(token) for token in encoder.encode(text)]


def recording_preflight(bound):
    """Run the actual request runtime with a recording decision oracle, without a GPU."""
    audit = prompt_audit(bound)
    _, _, tables, _ = pair_inputs(bound)
    plan = reference_plan(bound)
    true_ids, false_ids = plan.settings["true_ids"], plan.settings["false_ids"]
    if set(true_ids) & set(false_ids) or not true_ids or not false_ids:
        raise ValueError("Answer token classes must be nonempty and disjoint")

    class Client:
        accepts_text = False

        def __init__(self):
            self.prompts = []
            self.resets = 0

        def reset_prefix_cache(self):
            self.resets += 1
            return True

        def generate(self, prompts, sampling_params, use_tqdm=False):
            outputs = []
            for prompt in prompts:
                if set(prompt) != {"prompt_token_ids"}:
                    raise ValueError("Reference submitted text rather than frozen segmented tokens")
                tokens = [int(token) for token in prompt["prompt_token_ids"]]
                self.prompts.append(tokens)
                decision = int(digest(tokens)[:8], 16) % 2 == 0
                outputs.append(SimpleNamespace(prompt_token_ids=tokens, num_cached_tokens=0,
                    outputs=[SimpleNamespace(token_ids=[true_ids[0] if decision else false_ids[0]])]))
            return outputs

    client = Client()
    backend = bound.query.session.registry.backend(BACKEND)

    def execute(request):
        context = BackendExecutionContext(request=request, graph=plan.graph,
            registry=bound.query.session.registry, gpu_count=1, runtime_state={})
        return execute_request_graph(context, backend,
            dict(client=client, sampling_params=None, capacity={"kv_cache_size_tokens": 1_000_000}),
            dict(kind="decision-oracle-NOT-inference", boot_s=0.0))

    result = execute_query(bound.query, plan=plan, physical_executor=execute)
    expected = Counter((row["token_sha256"], row["tokens"]) for row in audit["pairs"])
    actual = Counter((digest(tokens), len(tokens)) for tokens in client.prompts)
    if actual != expected or client.resets != 1:
        raise ValueError("Request prompt multiset or prefix-cache reset differs from the contract")
    answer_table = result.answer_tables["joins"][0]
    actual_decisions = {(tables["l"]["id"][left].as_py(), tables["r"]["id"][right].as_py()): answer
        for left, right, answer in zip(answer_table["l"].to_pylist(), answer_table["r"].to_pylist(),
                                answer_table["answer"].to_pylist())}
    wanted = {(row["head"], row["target"]): int(row["token_sha256"][:8], 16) % 2 == 0
              for row in audit["pairs"]}
    if actual_decisions != wanted or len(answer_table) != len(wanted):
        raise ValueError("Reference attached decisions to the wrong candidate pairs")
    positive = result.collect()
    restored = bound.candidates.restore(zip(positive["l.id"].to_pylist(), positive["r.id"].to_pylist()))
    wanted_rows = bound.candidates.restore([pair for pair, bit in wanted.items() if bit])
    if restored != wanted_rows:
        raise ValueError("Reference output projection changed the ordered bag")
    return dict(kind="CPU request-runtime preflight; no model inference or timing claim",
        pairs=len(wanted), prompt_multiset_equal=True, decisions_equal=True,
        prefix_cache_resets=client.resets, output_bindings=len(restored),
        requested_tokens=audit["requested_tokens"], prompt_audit_sha256=digest(audit))


def session(encoder):
    return quail.Session(quail.EngineConfig(model=QWEN3_4B_FP8.name, device="h100-sxm"),
                         tokenizer=encoder)


def freeze(run, source_inputs, truth):
    from huggingface_hub import HfApi, snapshot_download

    pinned_source()
    if sha(source_inputs) != SOURCE_INPUT_SHA or sha(truth) != SOURCE_TRUTH_SHA:
        raise ValueError("Use the complete frozen SciFact development input and truth")
    original = read(source_inputs)
    labels = read(truth)["labels"]
    if len(labels) != len(original["edges"]) or set(labels) - {"SUPPORT", "CONTRADICT", "NOT_ENOUGH_INFO"}:
        raise ValueError("One SciFact label is required per source candidate")
    rows, gold = [], []
    for edge, label in zip(original["edges"], labels):
        head, target = f"claim:{edge['claim_id']}", f"document:{edge['document_id']}"
        for _ in range(edge["source_occurrences"]):
            rows.append(dict(head=head, target=target, head_text=edge["claim"],
                target_text=edge["title"]+"\n\n"+" ".join(edge["abstract"]), ordinal=len(rows)))
        gold.append(dict(head=head, target=target, answer=label == "SUPPORT"))
    model = QWEN3_4B_FP8
    info = HfApi().model_info(model.hf_name, revision=model.revision, files_metadata=True)
    if info.sha != model.revision:
        raise ValueError("Model revision did not resolve exactly")
    model_path = Path(snapshot_download(model.hf_name, revision=model.revision,
                                       allow_patterns=["*.json", "*.txt", "*.model", "*.tiktoken"]))
    weight_files = {file.rfilename: file.lfs.sha256 for file in info.siblings
                    if file.rfilename.endswith(".safetensors") and file.lfs is not None}
    if not weight_files:
        raise ValueError("No content-addressed model weights in pinned revision")
    candidates = QuailPairs(rows)
    with session(tokenizer(model_path)) as engine:
        bound = candidates.bind(engine, PREDICATE, kind="barrier")
        audit = prompt_audit(bound)
        if audit["max_prompt_tokens"] > 8192:
            raise ValueError("Prompt exceeds the fixed 8192-token diagnostic budget")
        vllm_plan = reference_plan(bound)
        plans = {"quail": bound.query.plan().to_envelope(engine.registry.codecs),
                 "vllm": vllm_plan.to_envelope(engine.registry.codecs)}
    run.mkdir(parents=True, exist_ok=False)
    write(run/"inputs.json", rows)
    write(run/"truth.json", gold)
    write(run/"prompts.json", audit)
    write(run/"plans.json", plans)
    tokenizer_files = {}
    (run/"tokenizer").mkdir()
    for path in sorted(model_path.iterdir()):
        if path.is_file() and not path.name.endswith(".safetensors"):
            shutil.copyfile(path, run/"tokenizer"/path.name)
            tokenizer_files[path.name] = sha(path)
    for name in (Path(__file__).name, "QUAIL_EXECUTION_PROTOCOL.md"):
        shutil.copyfile(Path(__file__).with_name(name), run/name)
    write(run/"manifest.json", dict(version=1, quail_commit=PIN, model=model.hf_name,
        model_revision=model.revision, predicate=PREDICATE, source_inputs_sha256=sha(source_inputs),
        source_truth_sha256=sha(truth), candidate_identity=candidates.identity,
        model_files={**tokenizer_files, **weight_files},
        files={str(path.relative_to(run)): sha(path) for path in sorted(run.rglob("*")) if path.is_file()},
        bridge_sha256=sha(Path(__file__).parents[2]/"src/orbweaver_query/quail.py")))
    return dict(candidates=candidates.describe(), **{k: v for k, v in audit.items() if k != "pairs"})


def verify(run):
    manifest = read(run/"manifest.json")
    if manifest["quail_commit"] != pinned_source():
        raise ValueError("Upstream source changed")
    for name, expected in manifest["files"].items():
        if sha(run/name) != expected:
            raise ValueError(f"Frozen file changed: {name}")
    from orbweaver_query import quail as bridge
    if sha(bridge.__file__) != manifest["bridge_sha256"]:
        raise ValueError("Candidate bridge source changed")
    if sha(__file__) != manifest["files"][Path(__file__).name]:
        raise ValueError("Benchmark source changed")
    return manifest


def worker(run, arm, output, repeats):
    manifest = verify(run)
    output.mkdir(parents=True, exist_ok=False)
    write(output/"started.json", dict(arm=arm, repeats=repeats, manifest_sha256=sha(run/"manifest.json"),
                                    python=platform.python_version(), platform=platform.platform()))
    try:
        import torch
        from huggingface_hub import snapshot_download

        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise RuntimeError("Expose exactly one H100 SXM CUDA device for this diagnostic")
        device = torch.cuda.get_device_properties(0)
        if "H100" not in device.name or "SXM" not in device.name or device.total_memory < 75*2**30:
            raise RuntimeError("This frozen configuration requires an H100 SXM with at least 75 GiB")
        if version("vllm") != "0.26.0":
            raise RuntimeError("Use the pinned vLLM 0.26.0 backend")
        model_path = Path(snapshot_download(manifest["model"], revision=manifest["model_revision"],
                                           allow_patterns=list(manifest["model_files"])))
        for name, expected in manifest["model_files"].items():
            if sha(model_path/name) != expected:
                raise ValueError(f"Model file changed: {name}")
        write(output/"environment.json", dict(device=device.name, total_memory=device.total_memory,
            device_uuid=str(getattr(device, "uuid", "unavailable")),
            host=platform.node(), cuda=torch.version.cuda, dependencies={name: version(name) for name in
                ("torch", "vllm", "quail-engine", "gigatoken", "pyarrow", "numpy")},
            model_files_verified=True))
        setup_started = time.perf_counter()
        candidates = QuailPairs(read(run/"inputs.json"))
        if candidates.identity != manifest["candidate_identity"]:
            raise ValueError("Captured candidate identity changed")
        with session(tokenizer(run/"tokenizer")) as engine:
            bound = candidates.bind(engine, manifest["predicate"], kind="barrier")
            if prompt_audit(bound) != read(run/"prompts.json"):
                raise ValueError("Per-pair prompt tokens changed")
            plan = bound.query.plan() if arm == "quail" else reference_plan(bound)
            if plan.to_envelope(engine.registry.codecs) != read(run/"plans.json")[arm]:
                raise ValueError("Frozen physical plan changed")
            preparation_s = time.perf_counter()-setup_started
            for trial in range(repeats+1):
                torch.cuda.synchronize()
                began = time.perf_counter()
                result = execute_query(bound.query, plan=plan)
                table = result.collect()
                restored = candidates.restore(zip(table["l.id"].to_pylist(), table["r.id"].to_pylist()))
                torch.cuda.synchronize()
                elapsed = time.perf_counter()-began
                if arm == "vllm" and result.report["backend_metrics"]["capacity"]["enable_prefix_caching"] is not True:
                    raise ValueError("The actual vLLM runtime disabled prefix caching")
                answers = result.answer_tables["joins"][0]
                # Result projection contains positives only; retain and validate the complete decision domain.
                _, _, tables, _ = pair_inputs(bound)
                decisions = [dict(head=tables["l"]["id"][left].as_py(),
                    target=tables["r"]["id"][right].as_py(), answer=bool(answer))
                    for left, right, answer in zip(answers["l"].to_pylist(), answers["r"].to_pylist(),
                                             answers["answer"].to_pylist())]
                keys = [(row["head"], row["target"]) for row in decisions]
                if len(keys) != len(set(keys)) or set(keys) != set(candidates.candidate_pairs):
                    raise ValueError("Inference did not return exactly one decision per candidate")
                write(output/f"trial-{trial:02d}.json", dict(trial=trial, cold_boot=trial == 0,
                    elapsed_s=elapsed, preparation_s=preparation_s, report=result.report,
                    decisions=sorted(decisions, key=lambda r: (r["head"], r["target"])),
                    output_bindings=len(restored), output_sha256=digest(restored)))
        write(output/"complete.json", dict(arm=arm, measured_trials=repeats, cold_boot_trials=1))
    except BaseException:
        write(output/"failure.json", dict(traceback=traceback.format_exc()))
        raise


def decisions_by_pair(rows):
    values = {}
    for row in rows:
        pair = row["head"], row["target"]
        if pair in values or type(row["answer"]) is not bool:
            raise ValueError("Decisions require unique pairs and Boolean answers")
        values[pair] = row["answer"]
    return values


def binary_metrics(truth, predictions):
    if set(truth) != set(predictions):
        raise ValueError("Quality requires the complete labeled candidate domain")
    tp = sum(truth[key] and predictions[key] for key in truth)
    tn = sum(not truth[key] and not predictions[key] for key in truth)
    fp = sum(not truth[key] and predictions[key] for key in truth)
    fn = sum(truth[key] and not predictions[key] for key in truth)
    def ratio(a, b):
        return a/b if b else 0.0
    f1 = ratio(2*tp, 2*tp+fp+fn)
    return dict(tp=tp, tn=tn, fp=fp, fn=fn, precision=ratio(tp, tp+fp),
                recall=ratio(tp, tp+fn), support_f1=f1,
                macro_f1=(f1+ratio(2*tn, 2*tn+fp+fn))/2,
                accuracy=ratio(tp+tn, tp+tn+fp+fn))


def summarize(run):
    verify(run)
    truth = decisions_by_pair(read(run/"truth.json"))
    arms, predictions, identities = {}, {}, []
    for arm in ("quail", "vllm"):
        processes, predictions[arm] = [], []
        for repetition in range(3):
            folder = run/"workers"/f"{arm}-{repetition}"
            if not (folder/"complete.json").is_file() or (folder/"failure.json").exists():
                raise ValueError(f"Missing or failed worker: {folder}; retain it and do not report a speedup")
            complete, started, environment = (read(folder/name) for name in
                ("complete.json", "started.json", "environment.json"))
            if (complete != dict(arm=arm, measured_trials=3, cold_boot_trials=1)
                    or started["manifest_sha256"] != sha(run/"manifest.json") or started["arm"] != arm
                    or started["repeats"] != 3 or not environment["model_files_verified"]):
                raise ValueError("Worker identity or measurement count differs from the frozen protocol")
            identities.append(environment)
            trials = []
            if len(list(folder.glob("trial-*.json"))) != 4:
                raise ValueError("Exactly one cold and three warm queries are required per process")
            for trial in range(4):
                record = read(folder/f"trial-{trial:02d}.json")
                if (record["trial"] != trial or record["cold_boot"] is not (trial == 0)
                        or not math.isfinite(record["elapsed_s"]) or record["elapsed_s"] <= 0):
                    raise ValueError("Invalid measurement")
                bits = decisions_by_pair(record["decisions"])
                metrics = binary_metrics(truth, bits)
                predictions[arm].append(bits)
                trials.append(dict(trial=trial, elapsed_s=record["elapsed_s"], quality=metrics,
                                   output_sha256=record["output_sha256"]))
            processes.append(dict(repetition=repetition, cold_boot_elapsed_s=trials[0]["elapsed_s"],
                measured_median_s=statistics.median(row["elapsed_s"] for row in trials[1:]), trials=trials))
        arms[arm] = dict(processes=processes,
                        median_of_process_medians_s=statistics.median(p["measured_median_s"] for p in processes),
                        repeat_decisions_identical=all(p == predictions[arm][0] for p in predictions[arm]))
    if any(environment != identities[0] for environment in identities[1:]):
        raise ValueError("Arms/processes have different hardware or dependency identities")
    disagreement = sorted([*key] for key in truth
                          if predictions["quail"][0][key] != predictions["vllm"][0][key])
    repeatable = all(value["repeat_decisions_identical"] for value in arms.values())
    return dict(kind="Development inference-backend diagnostic; not an Orbweaver speedup claim",
        arms=arms, decision_disagreements=disagreement, repeat_decisions_identical=repeatable,
        exact_answer_comparison_valid=repeatable and not disagreement,
        descriptive_vllm_over_quail_ratio=(arms["vllm"]["median_of_process_medians_s"]
                                           / arms["quail"]["median_of_process_medians_s"]),
        graph_export_included=False, acceptance_gate_closed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    frozen = sub.add_parser("freeze")
    frozen.add_argument("run", type=Path)
    frozen.add_argument("--inputs", type=Path, required=True)
    frozen.add_argument("--truth", type=Path, required=True)
    check = sub.add_parser("verify")
    check.add_argument("run", type=Path)
    preflight = sub.add_parser("preflight")
    preflight.add_argument("run", type=Path)
    preflight.add_argument("--output", type=Path, required=True)
    summary = sub.add_parser("summarize")
    summary.add_argument("run", type=Path)
    summary.add_argument("--output", type=Path, required=True)
    execute = sub.add_parser("worker")
    execute.add_argument("run", type=Path)
    execute.add_argument("--arm", choices=("quail", "vllm"), required=True)
    execute.add_argument("--output", type=Path, required=True)
    execute.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.command == "freeze":
        print(json.dumps(freeze(args.run, args.inputs, args.truth), indent=2))
    elif args.command == "verify":
        verify(args.run)
        print("Frozen source, model-input, tokenizer, prompt, plan and truth hashes verified")
    elif args.command == "preflight":
        manifest = verify(args.run)
        with session(tokenizer(args.run/"tokenizer")) as engine:
            bound = QuailPairs(read(args.run/"inputs.json")).bind(engine, manifest["predicate"], kind="barrier")
            if prompt_audit(bound) != read(args.run/"prompts.json"):
                raise ValueError("Frozen prompt audit changed")
            result = recording_preflight(bound)
        write(args.output, result)
        print(json.dumps(result, indent=2))
    elif args.command == "summarize":
        result = summarize(args.run)
        write(args.output, result)
        print(json.dumps(result, indent=2))
    else:
        if args.repeats < 1:
            raise ValueError("At least one measured repetition is required")
        worker(args.run, args.arm, args.output, args.repeats)


if __name__ == "__main__":
    main()
