"""Frozen published-model quality comparator; not a performance campaign."""

import argparse
import gc
import hashlib
import importlib.util
import json
import math
import random
import shutil
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path

LABELS = ("CONTRADICT", "NOT_ENOUGH_INFO", "SUPPORT")
MODELS = {"rationale": "rationale_roberta_large_scifact",
          "label": "label_roberta_large_fever_scifact"}


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(2**20):
            digest.update(chunk)
    return digest.hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    def convert(item):
        if isinstance(item, set):
            return sorted(item)
        raise TypeError(f"Unsupported JSON value: {type(item).__name__}")

    encoded = json.dumps(value, indent=2, sort_keys=True, allow_nan=False, default=convert)
    with path.open("x") as stream:
        stream.write(encoded + "\n")


def reference(run):
    spec = importlib.util.spec_from_file_location("frozen_scifact", run / "scifact_reference.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def model_directory(models, name):
    configs = list((models / name).rglob("config.json"))
    if len(configs) != 1:
        raise ValueError(f"Expected one model config: {name}")
    return configs[0].parent


def freeze(run, prior, models, source):
    reference(prior).verify(prior)
    inputs = read(prior / "inputs.json")
    qwen = [read(p) for p in sorted((prior / "predictions").glob("*.json"))]
    if [r["index"] for r in qwen] != list(range(len(inputs["edges"]))):
        raise ValueError("Incomplete Qwen reference")
    run.mkdir(parents=True, exist_ok=False)
    for name in ("inputs.json", "truth.json", "scifact_reference.py", "baseline-source.json"):
        shutil.copyfile(prior / name, run / name)
    for name in ("verisci_reference.py", "VERISCI_REFERENCE_PROTOCOL.md"):
        shutil.copyfile(Path(__file__).with_name(name), run / name)
    write(run / "qwen-predictions.json", qwen)
    shutil.copyfile(models / "compatibility-preflight.json", run / "compatibility-preflight.json")
    upstream = run / "upstream"
    upstream.mkdir()
    for part in ("rationale_selection", "label_prediction"):
        shutil.copyfile(source / f"verisci/inference/{part}/transformer.py", upstream / f"{part}.py")
    for name in ("script/pipeline.sh", "LICENSE.md", "requirements.txt",
                 "transformers-v2.7.0-modeling_roberta.py"):
        shutil.copyfile(source / name, upstream / Path(name).name)
    model_files = {}
    for name in MODELS.values():
        receipt = read(models / f"{name}.json")
        for member, info in receipt["files"].items():
            path = models / name / member
            if sha(path) != info["sha256"] or path.stat().st_size != info["bytes"]:
                raise ValueError(f"Downloaded model changed: {name}/{member}")
        shutil.copyfile(models / f"{name}.json", run / f"{name}.json")
        directory = model_directory(models, name)
        model_files[name] = {str(p.relative_to(directory)): sha(p)
                             for p in sorted(directory.rglob("*")) if p.is_file()}
    write(run / "manifest.json", {
        "files": {str(p.relative_to(run)): sha(p) for p in sorted(run.rglob("*")) if p.is_file()},
        "model_files": model_files, "rows": len(qwen), "threshold": .5,
        "prior_manifest_sha256": sha(prior / "manifest.json"),
        "device": "cpu", "dtype": "float32", "attention": "eager", "torch_threads": 4})
    return {"frozen_rows": len(qwen), "manifest_sha256": sha(run / "manifest.json")}


def verify(run, models=None):
    manifest = read(run / "manifest.json")
    for name, expected in manifest["files"].items():
        if sha(run / name) != expected:
            raise ValueError(f"Frozen file changed: {name}")
    if models is not None:
        for name, files in manifest["model_files"].items():
            directory = model_directory(models, name)
            for member, expected in files.items():
                if sha(directory / member) != expected:
                    raise ValueError(f"Model changed: {name}/{member}")
    return manifest


def selected_evidence(row, indices):
    if indices != sorted(set(indices)) or any(i < 0 or i >= len(row["abstract"]) for i in indices):
        raise ValueError("Invalid rationale indices")
    return " ".join(row["abstract"][i] for i in indices)


def encode(tokenizer, texts, claims, truncate=False):
    batch = tokenizer(texts, claims, padding=True, truncation=False, return_tensors="pt")
    overlength = batch["input_ids"].shape[1] > 512
    if overlength:
        if not truncate:
            raise ValueError("Rationale pair exceeds 512 tokens")
        batch = tokenizer(texts, claims, padding=True, truncation="only_first",
                          max_length=512, return_tensors="pt")
    return batch, overlength


def infer(run, models):
    import inspect
    from importlib.metadata import version

    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    manifest = verify(run, models)
    inputs = read(run / "inputs.json")  # Hash-verified truth is never parsed here.
    torch.set_num_threads(manifest["torch_threads"])
    torch.set_num_interop_threads(1)
    torch.manual_seed(0)
    write(run / "environment.json", {"python": sys.version, "device": "cpu", "dtype": "float32",
        "versions": {p: version(p) for p in ("torch", "transformers", "tokenizers", "numpy")},
        "threads": torch.get_num_threads(), "interop_threads": torch.get_num_interop_threads()})
    began = time.perf_counter()
    try:
        for stage, name in MODELS.items():
            directory = model_directory(models, name)
            started = time.perf_counter()
            tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True)
            model, info = AutoModelForSequenceClassification.from_pretrained(directory,
                local_files_only=True, dtype=torch.float32, attn_implementation="eager",
                output_loading_info=True)
            model.eval()
            write(run / f"{stage}-loading.json", {"report": info,
                "seconds": time.perf_counter()-started, "model_class": type(model).__name__,
                "model_source_sha256": sha(Path(inspect.getfile(type(model)))),
                "tokenizer_class": type(tokenizer).__name__, "fast_tokenizer": tokenizer.is_fast})
            # Transformers 2.7.0 created this pooler but its classifier never used it.
            allowed = {"roberta.embeddings.position_ids", "roberta.pooler.dense.weight",
                       "roberta.pooler.dense.bias"}
            if (info.get("missing_keys") or info.get("mismatched_keys") or info.get("error_msgs")
                    or set(info.get("unexpected_keys", [])) - allowed):
                raise ValueError(f"Unexplained model loading changes: {name}")
            if model.config.num_labels != (2 if stage == "rationale" else 3):
                raise ValueError("Wrong model label count")
            folder = run / stage
            folder.mkdir(exist_ok=False)
            started = time.perf_counter()
            with torch.inference_mode():
                for index, row in enumerate(inputs["edges"]):
                    if stage == "rationale":
                        batch, truncated = encode(tokenizer, row["abstract"],
                                                  [row["claim"]]*len(row["abstract"]))
                        scores = model(**batch).logits.softmax(dim=1)[:, 1].tolist()
                        indices = [i for i, score in enumerate(scores) if score >= manifest["threshold"]]
                        result = {"index": index, "scores": scores, "selected": indices}
                    else:
                        indices = read(run / "rationale" / f"{index:04d}.json")["selected"]
                        evidence = selected_evidence(row, indices)
                        batch, truncated = None, False
                        if indices:
                            batch, truncated = encode(tokenizer, [evidence], [row["claim"]], truncate=True)
                            scores = model(**batch).logits.softmax(dim=1)[0].tolist()
                        else:
                            scores = [0., 1., 0.]
                        result = {"index": index, "probabilities": scores, "selected": indices,
                                  "label": LABELS[max(range(3), key=lambda i: scores[i])]}
                    result["truncated"] = truncated
                    result["input_ids"] = batch["input_ids"].tolist() if batch is not None else []
                    write(folder / f"{index:04d}.json", result)
                    if (index+1) % 25 == 0 or index+1 == len(inputs["edges"]):
                        print(json.dumps({"stage": stage, "completed": index+1,
                                          "total": len(inputs["edges"])}), flush=True)
            write(run / f"{stage}-timing.json", {"seconds": time.perf_counter()-started,
                                                "rows": len(inputs["edges"])})
            del model, tokenizer
            gc.collect()
    except Exception:
        write(run / "inference-error.json", {"traceback": traceback.format_exc()})
        raise
    write(run / "inference.json", {"seconds_including_load": time.perf_counter()-began,
                                    "rows": len(inputs["edges"])})
    return {"completed": len(inputs["edges"])}


def macro_f1(confusion):
    scores = []
    for i in range(3):
        denominator = sum(confusion[i*3:i*3+3]) + sum(confusion[i::3])
        scores.append(2*confusion[i*3+i]/denominator if denominator else 1.)
    return sum(scores)/3


def paired_bootstrap(inputs, gold, qwen, baseline, repetitions=2000):
    groups = defaultdict(lambda: [[0]*9, [0]*9])
    for row, g, q, b in zip(inputs["edges"], gold, qwen, baseline):
        for arm, prediction in enumerate((q, b)):
            groups[row["claim_id"]][arm][LABELS.index(g)*3+LABELS.index(prediction)] += 1
    groups = list(groups.values())
    rng, differences = random.Random(0), []
    for _ in range(repetitions):
        selected = rng.choices(groups, k=len(groups))
        totals = [[sum(group[arm][i] for group in selected) for i in range(9)] for arm in range(2)]
        differences.append(macro_f1(totals[0])-macro_f1(totals[1]))
    differences.sort()
    return {"method": "paired claim bootstrap, nearest-rank percentiles", "seed": 0,
            "repetitions": repetitions, "claim_groups": len(groups),
            "interval_95": [differences[math.ceil(.025*repetitions)-1],
                            differences[math.ceil(.975*repetitions)-1]]}


def evaluate(run):
    verify(run)
    inputs, truth = read(run / "inputs.json"), read(run / "truth.json")
    outputs = [read(p) for p in sorted((run / "label").glob("*.json"))]
    if [r["index"] for r in outputs] != list(range(len(inputs["edges"]))):
        raise ValueError("Incomplete VeriSci denominator")
    labels = [r["label"] for r in outputs]
    qwen = [r["label"] for r in read(run / "qwen-predictions.json")]
    evaluator = reference(run)
    result = {name: evaluator.evaluate_labels(inputs, values, truth["labels"])
              for name, values in (("verisci", labels), ("qwen3", qwen))}
    result["qwen_minus_verisci_macro_f1"] = result["qwen3"]["macro_f1"]-result["verisci"]["macro_f1"]
    result["paired_difference"] = paired_bootstrap(inputs, truth["labels"], qwen, labels)
    result["rows"] = len(labels)
    result["no_selected_rationale"] = sum(not r["selected"] for r in outputs)
    result["truncated_label_inputs"] = sum(r["truncated"] for r in outputs)
    result["release_gate_closed"] = False
    write(run / "results.json", result)
    return {"rows": len(labels), "verisci_macro_f1": result["verisci"]["macro_f1"],
            "qwen_macro_f1": result["qwen3"]["macro_f1"], "difference": result["paired_difference"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "infer", "evaluate", "verify"))
    parser.add_argument("run", type=Path)
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--models", type=Path)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    if args.command == "freeze":
        output = freeze(args.run, args.prior, args.models, args.source)
    elif args.command == "infer":
        output = infer(args.run, args.models)
    elif args.command == "evaluate":
        output = evaluate(args.run)
    else:
        output = {"verified_files": len(verify(args.run, args.models)["files"])}
    print(json.dumps(output, allow_nan=False))
