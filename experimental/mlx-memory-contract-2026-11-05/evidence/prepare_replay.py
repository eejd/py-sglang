"""Materialize deterministic request fixtures for the causal replay (offline; no engine, no network).

Usage: prepare_replay.py FIXTURE_DIR QB_CLIENT_REPORT TOKENIZER_PATH MODEL_NAME

Writes FIXTURE_DIR/p<size>.json (mode 0600) for sizes 2048/16384/32768, each holding repeats 1 and 2 with two
canonical bodies (the first two rows of the installed GuideLLM public synthetic generator).  Output32 variants
change only max_completion_tokens at send time; the stored bodies always carry 128.
"""

import hashlib
import importlib.metadata
import json
import os
import sys
from pathlib import Path
from random import Random

SIZES = (2048, 16384, 32768)
SEEDS = {1: 505645418, 2: 505645419}
OUTPUT_TOKENS = 128


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(obj):
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def body_for(text, model):
    return {
        "model": model,
        "stream": True,
        "stream_options": {"include_usage": True, "continuous_usage_stats": True},
        "max_completion_tokens": OUTPUT_TOKENS,
        "ignore_eos": True,
        "messages": [{"role": "user", "content": [{"type": "text", "text": text}]}],
    }


def first_text(row):
    graph = row["conversation_turns"]
    graph = json.loads(graph) if isinstance(graph, str) else graph
    return graph["turns"][0]["columns"]["text_column"][0]


def generate_rows(size, seed, tok, count):
    from guidellm.data.deserializers.synthetic import SyntheticTextDataset
    from guidellm.schemas.data.deserializers import SyntheticTextDataArgs

    cfg = SyntheticTextDataArgs(prompt_tokens=size, output_tokens=OUTPUT_TOKENS)
    dataset_seed = Random(seed).getrandbits(32)
    rows = iter(
        SyntheticTextDataset(config=cfg, processor=tok, random_seed=dataset_seed)
    )
    return [next(rows) for _ in range(count)], dataset_seed


def token_ids(tok, body):
    text = body["messages"][0]["content"][0]["text"]
    ids = tok.apply_chat_template(
        [{"role": "user", "content": text}], add_generation_prompt=True, tokenize=True
    )
    if isinstance(ids, dict) or hasattr(ids, "input_ids"):
        ids = ids["input_ids"]
    return list(ids)


def common_prefix(a, b):
    n = 0
    for x, y in zip(a, b, strict=False):
        if x != y:
            break
        n += 1
    return n


def main(argv):
    out_dir, qb_report, tokenizer_path, model = (
        Path(argv[1]),
        Path(argv[2]),
        argv[3],
        argv[4],
    )
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(tokenizer_path, local_files_only=True)
    qb = json.loads(qb_report.read_text())
    qb_body = json.loads(
        qb["benchmarks"][0]["requests"]["successful"][0]["request_args"]
    )["body"]
    out_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if out_dir.is_symlink():
        raise SystemExit("refusing symlinked fixture directory")
    tokenizer_files = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(Path(tokenizer_path).iterdir())
        if p.name in ("tokenizer.json", "tokenizer_config.json", "config.json")
    }
    summary = {}
    for size in SIZES:
        fixture = {
            "size": size,
            "model": model,
            "output_tokens_stored": OUTPUT_TOKENS,
            "seeds": {
                str(r): {"static_seed": sd, "dataset_seed": Random(sd).getrandbits(32)}
                for r, sd in SEEDS.items()
            },
            "generator": {
                "guidellm_version": importlib.metadata.version("guidellm"),
                "transformers_version": importlib.metadata.version("transformers"),
                "tokenizer_files_sha256": tokenizer_files,
            },
            "repeats": {},
        }
        for repeat, seed in SEEDS.items():
            rows, dataset_seed = generate_rows(size, seed, tok, 2)
            bodies = [body_for(first_text(r), model) for r in rows]
            ids = [token_ids(tok, b) for b in bodies]
            entry = {
                "static_seed": seed,
                "dataset_seed": dataset_seed,
                "body1": bodies[0],
                "body2": bodies[1],
                "body1_sha256": sha(bodies[0]),
                "body2_sha256": sha(bodies[1]),
                "prompt_only_sha256": [
                    hashlib.sha256(
                        b["messages"][0]["content"][0]["text"].encode("utf-8")
                    ).hexdigest()
                    for b in bodies
                ],
                "token_counts": [len(i) for i in ids],
                "token_ids_sha256": [
                    hashlib.sha256(json.dumps(i).encode()).hexdigest() for i in ids
                ],
                "common_token_prefix": common_prefix(ids[0], ids[1]),
                "bodies_equal": bodies[0] == bodies[1],
            }
            fixture["repeats"][str(repeat)] = entry
        status = {"reconstruction_verified": None, "method": None}
        if size == 32768:
            body1 = fixture["repeats"]["1"]["body1"]
            if body1 == qb_body and sha(body1) == sha(qb_body):
                status = {
                    "reconstruction_verified": True,
                    "method": "direct_generator_matches_recorded_qb_request1",
                }
            else:
                status = {
                    "reconstruction_verified": False,
                    "method": "direct_generator_mismatch",
                    "recorded_qb_body_sha256": sha(qb_body),
                    "direct_body1_sha256": sha(body1),
                }
        fixture["qb_request1_reconstruction"] = status
        path = out_dir / f"p{size}.json"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(canonical(fixture))
        summary[size] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "reconstruction": status,
            "repeats": {
                r: {
                    k: v
                    for k, v in e.items()
                    if k
                    in (
                        "body1_sha256",
                        "body2_sha256",
                        "token_counts",
                        "common_token_prefix",
                        "bodies_equal",
                    )
                }
                for r, e in fixture["repeats"].items()
            },
        }
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
