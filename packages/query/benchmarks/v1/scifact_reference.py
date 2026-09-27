"""Freeze and evaluate a conventional model on labeled semantic graph queries."""

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path

ARCHIVE_SHA = "11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be"
LABELS = ("SUPPORT", "CONTRADICT", "NOT_ENOUGH_INFO")
SYSTEM = ("Classify the claim using only the supplied scientific abstract. "
          "Return exactly one letter: A if the abstract supports the claim, "
          "B if it contradicts the claim, or C if it provides insufficient "
          "information to establish either. Do not use outside knowledge.")


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(2**20):
            digest.update(chunk)
    return digest.hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def rows_from_archive(path, member):
    with tarfile.open(path) as archive:
        return [json.loads(line) for line in archive.extractfile(member).read().splitlines()]


def graph_inputs(claims, corpus):
    """Gold and model inputs are separate; the supplied candidate domain is complete."""
    documents = {row["doc_id"]: row for row in corpus}
    if len(documents) != len(corpus) or len({c["id"] for c in claims}) != len(claims):
        raise ValueError("Duplicate corpus or claim IDs")
    inputs, truth = [], []
    for claim in sorted(claims, key=lambda r: r["id"]):
        targets = claim["cited_doc_ids"]
        if set(claim["evidence"]) - {str(t) for t in targets}:
            raise ValueError("Evidence outside the supplied cited domain")
        for doc_id in sorted(set(targets)):
            document = documents[doc_id]
            annotations = claim["evidence"].get(str(doc_id), [])
            labels = {a["label"] for a in annotations}
            if len(labels) > 1 or labels - set(LABELS[:2]):
                raise ValueError("Conflicting or unsupported gold edge labels")
            inputs.append({"claim_id": claim["id"], "document_id": doc_id,
                           "claim": claim["claim"], "title": document["title"],
                           "abstract": document["abstract"], "source_occurrences": targets.count(doc_id)})
            truth.append(next(iter(labels)) if labels else LABELS[2])
    return {"claims": [c["id"] for c in sorted(claims, key=lambda r: r["id"])],
            "edges": inputs}, truth


def query_answers(inputs, labels):
    if len(inputs["edges"]) != len(labels) or set(labels) - set(LABELS):
        raise ValueError("One recognized label is required for every edge")
    support, contradict = set(), set()
    by_document = defaultdict(lambda: defaultdict(set))
    for row, label in zip(inputs["edges"], labels):
        by_document[row["document_id"]][label].add(row["claim_id"])
        if label == "SUPPORT":
            support.add(row["claim_id"])
        elif label == "CONTRADICT":
            contradict.add(row["claim_id"])
    witnesses = sorted((a, d, b) for d, groups in by_document.items()
                       for a in groups["SUPPORT"] for b in groups["CONTRADICT"] if a != b)
    return {"supported": sorted(support), "uncontested": sorted(support-contradict),
            "disagreement": [list(row) for row in witnesses]}


def prompt(row):
    return "\n".join(("Scientific abstract:", row["title"], *row["abstract"],
                      "", "Claim:", row["claim"], "", "Classification (A, B, or C):"))


def freeze(run, archive, model_path):
    from mlx_lm.utils import load_tokenizer

    if sha(archive) != ARCHIVE_SHA:
        raise ValueError("Dataset archive checksum mismatch")
    claims = rows_from_archive(archive, "data/claims_dev.jsonl")
    corpus = rows_from_archive(archive, "data/corpus.jsonl")
    inputs, truth = graph_inputs(claims, corpus)
    _, train_truth = graph_inputs(rows_from_archive(archive, "data/claims_train.jsonl"), corpus)
    tokenizer = load_tokenizer(model_path)
    for row in inputs["edges"]:
        row["tokens"] = tokenizer.apply_chat_template([
            {"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt(row)}],
            tokenize=True, add_generation_prompt=True, return_dict=False)
        if not row["tokens"] or len(row["tokens"]) > 8192:
            raise ValueError("Prompt outside declared context budget")
    run.mkdir(parents=True, exist_ok=False)
    for name in ("scifact_reference.py", "SCIFACT_REFERENCE_PROTOCOL.md"):
        shutil.copyfile(Path(__file__).with_name(name), run / name)
    write(run / "inputs.json", inputs)
    write(run / "truth.json", {"labels": truth, "queries": query_answers(inputs, truth),
                               "training_majority": Counter(train_truth).most_common(1)[0][0]})
    write(run / "audit.json", {"claims": len(claims), "edges": len(truth),
          "documents": len({r["document_id"] for r in inputs["edges"]}),
          "label_counts": dict(Counter(truth)),
          "raw_citation_occurrences": sum(len(c["cited_doc_ids"]) for c in claims),
          "duplicate_citations": [{"claim": c["id"], "cited_doc_ids": c["cited_doc_ids"]}
                                  for c in claims if len(c["cited_doc_ids"]) != len(set(c["cited_doc_ids"]))],
          "outdegree_counts": dict(Counter(len(c["cited_doc_ids"]) for c in claims)),
          "token_lengths": [len(r["tokens"]) for r in inputs["edges"]],
          "test_claims_read": False, "archive_sha256": ARCHIVE_SHA})
    write(run / "manifest.json", {"files": {p.name: sha(p) for p in sorted(run.iterdir())},
          "model_files": {p.name: sha(p) for p in sorted(model_path.iterdir()) if p.is_file()},
          "model": "mlx-community/Qwen3-4B-Instruct-2507-4bit",
          "revision": "50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b",
          "prefill_batch_size": 4, "completion_batch_size": 4, "prefill_step_size": 2048})
    return read(run / "audit.json")


def verify(run, model_path=None):
    manifest = read(run / "manifest.json")
    for name, expected in manifest["files"].items():
        if sha(run / name) != expected:
            raise ValueError(f"Frozen file changed: {name}")
    if model_path is not None:
        for name, expected in manifest["model_files"].items():
            if sha(model_path / name) != expected:
                raise ValueError(f"Model file changed: {name}")
    return manifest


def infer(run, model_path):
    import inspect
    from importlib.metadata import version

    import mlx.core as mx
    from mlx_lm import load
    from mlx_lm.generate import BatchGenerator

    manifest = verify(run, model_path)
    inputs = read(run / "inputs.json")  # Gold is hash-verified, never parsed or given to the model.
    began = time.perf_counter()
    base, tokenizer = load(str(model_path))
    token_ids = [tokenizer.encode(s, add_special_tokens=False) for s in "ABC"]
    if any(len(tokens) != 1 for tokens in token_ids):
        raise ValueError("Classification choices must be single tokens")
    choices = [t[0] for t in token_ids]
    for row in inputs["edges"]:
        tokens = tokenizer.apply_chat_template([
            {"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt(row)}],
            tokenize=True, add_generation_prompt=True, return_dict=False)
        if tokens != row["tokens"]:
            raise ValueError("Prompt round-trip mismatch")
    write(run / "environment.json", {"load_and_tokenization_seconds": time.perf_counter()-began,
          "device": mx.device_info(), "python": sys.version,
          "versions": {p: version(p) for p in ("mlx", "mlx-lm", "transformers")},
          "batch_generator_source_sha256": sha(Path(inspect.getfile(BatchGenerator))),
          "choice_token_ids": choices})

    def restrict(tokens, logits):
        vocab = mx.arange(logits.shape[-1])
        allowed = (vocab == choices[0]) | (vocab == choices[1]) | (vocab == choices[2])
        return mx.where(allowed, logits, -float("inf"))

    generator = BatchGenerator(base, max_tokens=1, logits_processors=[restrict],
        **{k: manifest[k] for k in ("prefill_batch_size", "completion_batch_size", "prefill_step_size")})
    uids = generator.insert([r["tokens"] for r in inputs["edges"]], max_tokens=[1]*len(inputs["edges"]))
    positions, output = {uid: i for i, uid in enumerate(uids)}, {}
    folder = run / "predictions"
    folder.mkdir(exist_ok=False)
    mx.reset_peak_memory()
    began = time.perf_counter()
    try:
        while responses := generator.next_generated():
            for response in responses:
                index = positions[response.uid]
                if index in output or response.token not in choices or response.finish_reason != "length":
                    raise ValueError("Unexpected classifier response")
                probabilities = mx.exp(response.logprobs[mx.array(choices)]).tolist()
                output[index] = {"index": index, "label": LABELS[choices.index(response.token)],
                                 "probabilities": probabilities}
                write(folder / f"{index:04d}.json", output[index])
            print(json.dumps({"completed": len(output), "total": len(uids)}), flush=True)
    except Exception:
        write(run / "inference-error.json", {"traceback": traceback.format_exc(), "completed": len(output)})
        raise
    finally:
        generator.close()
    if len(output) != len(uids):
        raise ValueError("Incomplete inference")
    write(run / "inference.json", {"seconds": time.perf_counter()-began,
          "peak_mlx_bytes": mx.get_peak_memory(), "rows": len(output),
          "manifest_sha256": sha(run / "manifest.json")})
    return {"completed": len(output)}


def set_metrics(actual, wanted):
    actual, wanted = set(actual), set(wanted)
    tp = len(actual & wanted)
    precision = tp/len(actual) if actual else float(not wanted)
    recall = tp/len(wanted) if wanted else 1.
    return {"predicted": len(actual), "gold": len(wanted), "true_positive": tp,
            "precision": precision, "recall": recall,
            "f1": 2*tp/(len(actual)+len(wanted)) if actual or wanted else 1.}


def evaluate_labels(inputs, predictions, gold):
    confusion = [[sum(a == x and b == y for a, b in zip(gold, predictions))
                  for y in LABELS] for x in LABELS]
    classes = {label: set_metrics([i for i, p in enumerate(predictions) if p == label],
                                  [i for i, p in enumerate(gold) if p == label]) for label in LABELS}
    answers, wanted = query_answers(inputs, predictions), query_answers(inputs, gold)
    queries = {key: set_metrics([tuple(r) if isinstance(r, list) else r for r in answers[key]],
                               [tuple(r) if isinstance(r, list) else r for r in wanted[key]])
               for key in answers}
    return {"confusion_gold_rows": confusion, "classes": classes, "queries": queries,
            "macro_f1": sum(v["f1"] for v in classes.values())/len(LABELS), "answers": answers}


def evaluate(run):
    verify(run)
    inputs, truth = read(run / "inputs.json"), read(run / "truth.json")
    raw = [read(p) for p in sorted((run / "predictions").glob("*.json"))]
    if [r["index"] for r in raw] != list(range(len(inputs["edges"]))):
        raise ValueError("Incomplete prediction denominator")
    inferred = [r["label"] for r in raw]
    arms = {"qwen3": inferred, "training_majority": [truth["training_majority"]]*len(raw),
            "all_nei": [LABELS[2]]*len(raw)}
    result = {name: evaluate_labels(inputs, predictions, truth["labels"]) for name, predictions in arms.items()}
    model = result["qwen3"]
    result["qualification_passed"] = model["macro_f1"] >= .7 and all(
        r["recall"] >= .5 for r in model["classes"].values())
    result["release_gate_closed"] = False
    write(run / "results.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "infer", "evaluate", "verify"))
    parser.add_argument("run", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--model-path", type=Path)
    args = parser.parse_args()
    if args.command == "freeze":
        output = freeze(args.run, args.archive, args.model_path)
        output = {k: v for k, v in output.items() if k != "token_lengths"}
    elif args.command == "infer":
        output = infer(args.run, args.model_path)
    elif args.command == "evaluate":
        output = evaluate(args.run)
        output = {k: (v["macro_f1"] if isinstance(v, dict) else v) for k, v in output.items()}
    else:
        output = {"verified_files": len(verify(args.run, args.model_path)["files"])}
    print(json.dumps(output, allow_nan=False))
