"""Request/phase-resolved SGLang memory accounting; never imports the engine or MLX.

Usage:
  causal_report.py offline --es-evidence-root DIR --qb-raw DIR --out PREFIX
  causal_report.py live --run RUN_DIR --inventory SHA256_FILE --out PREFIX

Historical analysis scripts are read-only arithmetic references; nothing here edits them.
Derived outputs contain no timestamps, so identical input bytes give identical output bytes.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

MIB = 1024 * 1024
GIB = 1024**3
KV_BYTES_PER_TOKEN = 32768  # 16 layers x 8 kv heads x 64 dim x 2 (k,v) x 2 bytes (fp16)
VERDICTS = (
    "supported",
    "contradicted",
    "consistent_but_not_isolated",
    "not_identifiable",
)
QB_STEM = "L3-p32768-pass1"
QB_FILES = {
    "server_argv": f"{QB_STEM}.server_argv.json",
    "client_argv": f"{QB_STEM}.calibration-single-p32768-x0-o128-c1.argv.json",
    "client_report": f"{QB_STEM}.calibration-single-p32768-x0-o128-c1.json",
    "server_rss": f"{QB_STEM}.server_rss.jsonl",
    "engine_log": f"{QB_STEM}.engine.log",
}
SELF = Path(__file__).resolve()


class IntegrityError(Exception):
    pass


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def mib(value):
    return round(value / MIB, 2) if isinstance(value, (int, float)) else None


def gib(value):
    return round(value / GIB, 3) if isinstance(value, (int, float)) else None


def jsonl(path):
    rows = []
    for number, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise IntegrityError(f"{path}:{number}: malformed JSONL: {exc}") from exc
        if not isinstance(row, dict):
            raise IntegrityError(f"{path}:{number}: expected object")
        rows.append(row)
    return rows


def load_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise IntegrityError(f"{path}: {exc}") from exc


def read_inventory(path):
    """`sha256  relative/path` lines -> {relpath: sha}."""
    inventory = {}
    for line in Path(path).read_text().splitlines():
        if line.strip():
            sha, rel = line.split(None, 1)
            inventory[rel.strip()] = sha
    return inventory


class Manifest:
    """Sorted record of every consumed input with its verified digest."""

    def __init__(self):
        self.entries = {}

    def add(self, key, path, expected=None):
        digest = sha256_file(path)
        if expected is not None and digest != expected:
            raise IntegrityError(f"{key}: sha256 {digest} != recorded {expected}")
        self.entries[key] = {
            "sha256": digest,
            "verified_against_inventory": expected is not None,
        }
        return digest

    def as_list(self):
        return [{"path": k, **v} for k, v in sorted(self.entries.items())]


# ---------------------------------------------------------------------------------------------
# shim ledger


def mem(snapshot):
    if not isinstance(snapshot, dict):
        return None
    mx = snapshot.get("mx") if isinstance(snapshot.get("mx"), dict) else {}
    return {
        "footprint": snapshot.get("footprint"),
        "footprint_interval_max": snapshot.get("footprint_interval_max"),
        "active": mx.get("active"),
        "peak": mx.get("peak"),
        "cache": mx.get("cache"),
    }


def compact_sizes(sizes):
    if not isinstance(sizes, dict):
        return None
    keep = (
        "pool_size",
        "decode_step_ct",
        "pool_bytes",
        "req_caches",
        "req_caches_by_id",
        "req_caches_bytes",
        "prefill_caches",
        "prefill_caches_by_id",
        "prefill_caches_bytes",
        "cache_pool_len",
        "cache_pool_bytes",
        "private_cache_tokens_in_use",
    )
    return {k: sizes.get(k) for k in keep if k in sizes}


def request_ids(event):
    value = event.get("req_id", event.get("req_ids"))
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    return []


def build_ledger(events):
    """Per-request ledger from raw shim events, preserving raw order via `seq`."""
    ledger = {}
    order = []

    def entry(rid):
        if rid not in ledger:
            ledger[rid] = {
                "req_id": rid,
                "first_seq": None,
                "first_ts": None,
                "first_mono": None,
                "last_ts": None,
                "chunks": [],
                "interventions": [],
                "decode_steps": 0,
                "decode_ts": [],
                "first_decode_seq": None,
                "after_finish_seen": 0,
                "request_finish": None,
                "request_end": None,
                "request_state_removed": None,
                "acquire_seq": [],
                "release": [],
                "remove": [],
                "events_in_order": [],
            }
            order.append(rid)
        return ledger[rid]

    for seq, event in enumerate(events):
        name = event.get("ev")
        for rid in request_ids(event):
            row = entry(rid)
            if row["first_seq"] is None:
                row.update(
                    first_seq=seq,
                    first_ts=event.get("ts"),
                    first_mono=event.get("mono"),
                )
            row["last_ts"] = event.get("ts")
            row["events_in_order"].append(
                {
                    "seq": seq,
                    "ev": name,
                    "mono": event.get("mono"),
                    "ts": event.get("ts"),
                }
            )
            if name == "chunk":
                row["chunks"].append(
                    {
                        "seq": seq,
                        "chunk": event.get("chunk"),
                        "kind": event.get("kind"),
                        "new_tokens": event.get("new_tokens"),
                        "prefix_len": event.get("prefix_len"),
                        "ctx_tokens_after": event.get("ctx_tokens_after"),
                        "needs_logits": event.get("needs_logits"),
                        "cache_capacity_tokens": event.get("cache_capacity_tokens"),
                        "other_live_requests": event.get("other_live_requests"),
                        "other_live_ids": event.get("other_live_ids"),
                        "before": mem(event.get("before")),
                        "after": mem(event.get("after")),
                        "sizes_before": compact_sizes(event.get("sizes_before")),
                        "sizes": compact_sizes(event.get("sizes")),
                        "ts": event.get("ts"),
                        "mono": event.get("mono"),
                    }
                )
            elif name == "intervention_applied":
                row["interventions"].append(
                    {
                        "seq": seq,
                        "name": event.get("name"),
                        "n": event.get("n"),
                        "where": event.get("where"),
                        "chunk": event.get("chunk"),
                        "before": mem(event.get("before")),
                        "after": mem(event.get("after")),
                        "max_during": event.get("max_during"),
                        "ts": event.get("ts"),
                        "mono": event.get("mono"),
                    }
                )
            elif name == "decode_step":
                if row["first_decode_seq"] is None:
                    row["first_decode_seq"] = seq
                steps = event.get("steps") or {}
                row["decode_steps"] = max(row["decode_steps"], steps.get(rid, 0) or 0)
                row["decode_ts"].append(event.get("ts"))
                if rid in (event.get("after_finish") or []):
                    row["after_finish_seen"] += 1
            elif name == "request_finish":
                row["request_finish"] = {
                    "seq": seq,
                    "chunks": event.get("chunks"),
                    "decode_steps": event.get("decode_steps"),
                    "ctx_tokens": event.get("ctx_tokens"),
                    "owned_len": event.get("owned_len"),
                    "sizes": compact_sizes(event.get("sizes")),
                    "mem": mem(event),
                    "ts": event.get("ts"),
                }
            elif name == "request_end":
                row["request_end"] = {
                    "seq": seq,
                    "detected_by": event.get("detected_by"),
                    "decode_steps": event.get("decode_steps"),
                    "sizes": compact_sizes(event.get("sizes")),
                    "mem": mem(event),
                    "ts": event.get("ts"),
                }
            elif name == "request_state_removed":
                row["request_state_removed"] = {
                    "seq": seq,
                    "request_end_seen": event.get("request_end_seen"),
                    "sizes": compact_sizes(event.get("sizes")),
                    "mem": mem(event),
                    "ts": event.get("ts"),
                }
            elif name in ("_acquire_cache.exit",):
                row["acquire_seq"].append(
                    {
                        "seq": seq,
                        "mem": mem(event),
                        "cache_pool_len": event.get("cache_pool_len"),
                        "req_caches": event.get("req_caches"),
                    }
                )
            elif name in ("release_request_row.exit", "release_request_row.enter"):
                row["release"].append({"seq": seq, "ev": name, "mem": mem(event)})
            elif name in ("remove_request.exit", "remove_request.enter"):
                row["remove"].append(
                    {
                        "seq": seq,
                        "ev": name,
                        "mem": mem(event),
                        "cache_pool_len": event.get("cache_pool_len"),
                    }
                )
    result = []
    for rid in order:
        row = ledger[rid]
        chunks = row["chunks"]
        row["sum_new_tokens"] = (
            sum(c["new_tokens"] or 0 for c in chunks) if chunks else None
        )
        prefixes = [c["prefix_len"] for c in chunks if c["prefix_len"] is not None]
        row["measured_prefix_len"] = prefixes[0] if prefixes else None
        row["capacity_sum_tokens"] = sum(
            c["cache_capacity_tokens"] or 0 for c in chunks
        )
        row["capacity_x32KiB_mib"] = mib(
            row["capacity_sum_tokens"] * KV_BYTES_PER_TOKEN
        )
        result.append(row)
    return result


def non_ledger_events(events):
    names = (
        "runner_init",
        "init_cache_pools.exit",
        "_materialize_pool_backed_attention.exit",
        "set_wired_limit",
    )
    out = []
    for seq, e in enumerate(events):
        if e.get("ev") in names:
            out.append(
                {
                    "seq": seq,
                    "ev": e["ev"],
                    "ts": e.get("ts"),
                    "pool_size": e.get("pool_size"),
                    "disable_radix_cache": e.get("disable_radix_cache"),
                    "initial_cache_capacity_tokens": e.get(
                        "initial_cache_capacity_tokens"
                    ),
                    "cache_pool_len": e.get("cache_pool_len"),
                    "req_caches": e.get("req_caches"),
                    "mem": mem(e),
                }
            )
    return out


# ---------------------------------------------------------------------------------------------
# process tree


def registrations(cell):
    roles = {}
    reg = cell / "safety" / "registrations"
    if reg.is_dir():
        for p in sorted(reg.glob("register-*.json")):
            m = re.fullmatch(r"register-(.+)-(\d+)-(\d+)\.json", p.name)
            if m:
                roles[int(m.group(2))] = m.group(1)  # uniqueid -> role
    return roles


def tree_summary(cell, window_mono=None):
    rows = jsonl(cell / "processes.jsonl")
    roles = registrations(cell)
    parser_rows = [r for r in rows if r.get("invocation") == "parser"]
    engine_rows = [r for r in rows if r.get("invocation") != "parser"]
    totals = []
    sched = []
    for r in engine_rows:
        samples = r.get("samples") or []
        if r.get("errors") or not samples:
            continue
        total = sum(s.get("phys_footprint") or 0 for s in samples)
        s_only = sum(
            s.get("phys_footprint") or 0
            for s in samples
            if roles.get(s.get("uniqueid")) == "scheduler"
        )
        totals.append((total, r["monotonic"], len(samples)))
        sched.append((s_only, r["monotonic"]))
    lifetime = {}
    for r in engine_rows:
        for s in r.get("samples") or []:
            key = s.get("uniqueid")
            lifetime[key] = max(
                lifetime.get(key, 0), s.get("lifetime_max_phys_footprint") or 0
            )
    by_role = {}
    for uid, value in lifetime.items():
        role = roles.get(uid, f"unregistered-{uid}")
        by_role[role] = max(by_role.get(role, 0), value)
    peak = max(totals) if totals else None
    window_peak = None
    if window_mono and totals:
        inside = [t for t in totals if window_mono[0] <= t[1] <= window_mono[1]]
        window_peak = max(inside) if inside else None
    spk = max(sched) if sched else None
    return {
        "engine_tree_samples": len(totals),
        "engine_tree_peak_sampled_mib": mib(peak[0]) if peak else None,
        "engine_tree_peak_processes": peak[2] if peak else None,
        "engine_tree_peak_monotonic": peak[1] if peak else None,
        "engine_tree_peak_in_measured_window_mib": mib(window_peak[0])
        if window_peak
        else None,
        "scheduler_only_peak_sampled_mib": mib(spk[0]) if spk else None,
        "role_lifetime_max_mib": {k: mib(v) for k, v in sorted(by_role.items())},
        "sum_of_role_lifetime_maxima_mib_NOT_a_simultaneous_peak": mib(
            sum(by_role.values())
        ),
        "parser_discovery_samples": len(parser_rows),
        "parser_discovery_gap_samples": sum(
            1 for r in parser_rows if r.get("errors") or not r.get("samples")
        ),
        "engine_rows_with_errors_or_empty": sum(
            1 for r in engine_rows if r.get("errors") or not r.get("samples")
        ),
    }


# ---------------------------------------------------------------------------------------------
# client reports


def client_requests(report_path):
    d = load_json(report_path)
    out = []
    for b in d.get("benchmarks") or []:
        reqs = b.get("requests") or {}
        for status in ("successful", "errored", "incomplete"):
            for r in reqs.get(status) or []:
                im = r.get("input_metrics") or {}
                om = r.get("output_metrics") or {}
                info = r.get("info") or {}
                t = (info.get("timings") if isinstance(info, dict) else None) or {}
                out.append(
                    {
                        "status": status,
                        "request_id": r.get("request_id"),
                        "response_id": r.get("response_id"),
                        "input_tokens": im.get("text_tokens"),
                        "client_cached_tokens": im.get("cached_tokens"),
                        "output_tokens": om.get("text_tokens"),
                        "start": r.get("request_start_time"),
                        "end": r.get("request_end_time"),
                        "first_token_iteration": t.get("first_token_iteration"),
                        "last_token_iteration": t.get("last_token_iteration"),
                        "has_request_args": bool(r.get("request_args")),
                    }
                )
    return sorted(out, key=lambda r: (r["start"] is None, r["start"] or 0))


def attribute(ledger, windows):
    """Join shim requests to client windows by wall-clock containment of the first event."""
    for row in ledger:
        row["phase"] = "outside_client_windows"
        ts = row["first_ts"]
        for name, (lo, hi) in windows.items():
            if lo is not None and hi is not None and lo - 0.5 <= ts <= hi + 0.5:
                row["phase"] = name
                break


# ---------------------------------------------------------------------------------------------
# ES cell analysis


def cell_analysis(cell, manifest, inventory, run_rel):
    def consume(rel):
        path = cell / rel
        if not path.exists():
            return None
        key = f"{run_rel}/{rel}"
        manifest.add(key, path, inventory.get(f"cells/{cell.name}/{rel}"))
        return path

    shim = consume("shim-telemetry.jsonl")
    proc = consume("processes.jsonl")
    for p in (
        sorted((cell / "safety" / "registrations").glob("register-*.json"))
        if (cell / "safety").is_dir()
        else []
    ):
        consume(f"safety/registrations/{p.name}")
    consume("outcome.json")
    consume("manifest.json")
    diag_path = consume("diagnostic.json")
    windows = {}
    clients = {}
    for name in ("warmup", "capture"):
        p = consume(f"workload/{name}.json")
        if p is not None:
            try:
                reqs = client_requests(p)
            except IntegrityError as exc:
                clients[name] = {"error": str(exc)}
                continue
            clients[name] = reqs
            if reqs:
                windows["measured" if name == "capture" else "warmup"] = (
                    reqs[0]["start"],
                    reqs[-1]["end"],
                )
    events = jsonl(shim) if shim else []
    ledger = build_ledger(events)
    for ledger_row in ledger:
        ledger_row.pop(
            "events_in_order"
        )  # live analysis only; keeps the offline report compact
    attribute(ledger, windows)
    # wall->mono map from shim events for tree window
    mono_window = None
    pairs = [(e["ts"], e["mono"]) for e in events if "ts" in e and "mono" in e]
    if pairs and "measured" in windows:
        ts0, m0 = pairs[0]
        lo, hi = windows["measured"]
        mono_window = (m0 + (lo - ts0), m0 + (hi - ts0))
    tree = tree_summary(cell, mono_window) if proc else None
    settled = settled_sample(events, diag_path)
    outcome = (
        load_json(cell / "outcome.json") if (cell / "outcome.json").exists() else {}
    )
    measured = [r for r in ledger if r["phase"] == "measured"]
    client = clients.get("capture") or []
    client = client if isinstance(client, list) else []
    snaps = [
        s for r in ledger for c in r["chunks"] for s in (c["before"], c["after"]) if s
    ]
    snaps += [
        s
        for r in ledger
        for iv in r["interventions"]
        for s in (iv["before"], iv["after"])
        if s
    ]
    summary_peak = {
        "scheduler_sampled_footprint_peak_mib": mib(
            max(
                (s["footprint_interval_max"] or s["footprint"] or 0 for s in snaps),
                default=None,
            )
        ),
        "scheduler_mx_peak_mib": mib(
            max((s["peak"] or 0 for s in snaps), default=None)
        ),
        "scheduler_mx_active_max_mib": mib(
            max((s["active"] or 0 for s in snaps), default=None)
        ),
        "domain": "scheduler process only, from chunk/intervention snapshots; not a tree peak",
    }
    return {
        "cell": cell.name,
        "engine": outcome.get("engine"),
        "cleanup": outcome.get("cleanup"),
        "client": clients,
        "requests": ledger,
        "measured_request_ids": [r["req_id"] for r in measured],
        "pool_events": non_ledger_events(events),
        "tree": tree,
        "scheduler_event_peaks": summary_peak,
        "settled": settled,
        "token_equation": [
            token_equation(r, client[0] if client else None) for r in measured
        ],
    }


def settled_sample(events, diag_path):
    """Last scheduler sample inside [measurement_end, settle_end] (the recorded intervention window); None when absent."""
    if diag_path is None:
        return None
    diag = load_json(diag_path)
    window = ((diag.get("diagnostic") or {}).get("intervention") or {}).get("window")
    if not (
        isinstance(window, list)
        and len(window) == 3
        and all(isinstance(x, (int, float)) for x in window)
    ):
        window = (diag.get("intervention") or {}).get("window")
    if not (
        isinstance(window, list)
        and len(window) == 3
        and all(isinstance(x, (int, float)) for x in window)
    ):
        return {"status": "no_recorded_window"}
    sched_pids = {
        e.get("pid") for e in events if e.get("ev") in ("runner_init", "chunk")
    }
    inside = [
        e
        for e in events
        if e.get("ev") == "sample"
        and e.get("pid") in sched_pids
        and isinstance(e.get("mono"), (int, float))
        and window[1] <= e["mono"] <= window[2]
    ]
    if not inside:
        return {"status": "no_sample_in_settle_window", "window": window}
    last = max(inside, key=lambda e: e["mono"])
    m = mem(last)
    return {
        "status": "sampled",
        "window": window,
        "active_mib": mib(m["active"]),
        "cache_mib": mib(m["cache"]),
        "footprint_mib": mib(m["footprint"]),
        "residual_proxy_mib_footprint_minus_active_minus_cache": mib(
            m["footprint"] - m["active"] - m["cache"]
        )
        if None not in (m["footprint"], m["active"], m["cache"])
        else None,
        "proxy_note": "diagnostic proxy across incompatible accounting domains, not a measured component",
    }


def token_equation(row, client):
    s = row["sum_new_tokens"]
    prefix = row["measured_prefix_len"]
    observed = client["input_tokens"] if client else None
    return {
        "req_id": row["req_id"],
        "client_observed_input": observed,
        "measured_prefix_len": prefix,
        "sum_new_tokens": s,
        "equation_holds": (observed == prefix + s)
        if None not in (observed, prefix, s)
        else None,
        "client_cached_tokens_reported": client["client_cached_tokens"]
        if client
        else None,
        "note": "null client cache counts are unknown, not zero",
    }


def runs_in(es_root, manifest):
    out = []
    for evidence in sorted(Path(es_root).glob("sglang-*")):
        if (
            evidence.name.startswith("sglang-causal-replay")
            or not (evidence / "runs").is_dir()
        ):
            continue
        for run in sorted((evidence / "runs").iterdir()):
            inv_path = evidence / "logs" / f"{run.name}.raw-sha256.txt"
            if not inv_path.exists() or not (run / "cells").is_dir():
                continue
            out.append((evidence, run, inv_path))
    return out


# ---------------------------------------------------------------------------------------------
# QB reconstruction


def qb_analysis(raw, manifest):
    paths = {k: Path(raw) / v for k, v in QB_FILES.items()}
    missing = [str(p) for p in paths.values() if not p.exists()]
    if missing:
        return {
            "status": "unavailable",
            "reason": f"missing original inputs: {missing}",
        }
    for p in paths.values():
        manifest.add(f"qb:{p.name}", p)
    rss = jsonl(paths["server_rss"])
    report = load_json(paths["client_report"])
    bench = report["benchmarks"][0]
    reqs = client_requests(paths["client_report"])
    log = paths["engine_log"].read_text()
    pool_line = re.search(r"MlxAttentionKVPool: .*", log)
    baseline_line = re.search(r"Memory baseline taken\. mem usage=([\d.]+) GB", log)
    ok = [r for r in reqs if r["status"] == "successful"]
    err = [r for r in reqs if r["status"] == "errored"]
    samples = [(r["ts"], r["footprint_bytes"], r["peak_bytes"]) for r in rss]
    t_req1_end = ok[0]["end"] if ok else None
    t_req2_start = err[0]["start"] if err else None
    between = [
        s
        for s in samples
        if t_req1_end is not None
        and t_req2_start is not None
        and t_req1_end <= s[0] <= t_req2_start
    ]
    before_req1 = [s for s in samples if s[0] < reqs[0]["start"]]
    f0 = before_req1[-1] if before_req1 else None
    max_fp = max(samples, key=lambda s: s[1])
    max_peak = max(samples, key=lambda s: s[2])
    args_raw = bench["requests"]["successful"][0].get("request_args")
    body_sha = None
    if isinstance(args_raw, str):
        body = json.loads(args_raw).get("body")
        body_sha = hashlib.sha256(
            json.dumps(
                body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
        ).hexdigest()
    pool_mib = None
    if pool_line:
        m = re.search(r"~([\d.]+) MB", pool_line.group(0))
        pool_mib = float(m.group(1)) if m else None
    return {
        "status": "available",
        "server_argv": load_json(paths["server_argv"]),
        "requests": reqs,
        "request1_body_canonical_sha256": body_sha,
        "request1_body_recorded": body_sha is not None,
        "request2_body_recorded": bool(err and err[0]["has_request_args"]),
        "operands": {
            "F0_last_sample_before_request1_gib": gib(f0[1]) if f0 else None,
            "F0_definition": "last server_rss sample before request1 start (after-load/after-warmup plateau); the engine log's own `Memory baseline taken` reads "
            + (baseline_line.group(1) + " GB" if baseline_line else "n/a")
            + " and is a different domain",
            "pool_bytes_from_log_mib": pool_mib,
            "max_sampled_tree_footprint_gib": gib(max_fp[1]),
            "max_sampled_tree_footprint_offset_from_request1_start_s": round(
                max_fp[0] - reqs[0]["start"], 3
            ),
            "max_sampled_peak_bytes_gib": gib(max_peak[2]),
            "max_peak_note": "peak_bytes is the kernel lifetime maximum reported with each sample; it need not coincide with a sampled footprint; "
            "the issue's >=33.412GiB is this lifetime-maximum quantity",
            "samples_total": len(samples),
            "samples_between_request1_end_and_request2_start": len(between),
            "request1_end_to_request2_start_s": round(t_req2_start - t_req1_end, 6)
            if t_req1_end and t_req2_start
            else None,
        },
        "request1": ok[0] if ok else None,
        "request2": err[0] if err else None,
        "timeline_offsets_from_request1_start": [
            {
                "t_s": round(s[0] - reqs[0]["start"], 2),
                "footprint_gib": gib(s[1]),
                "peak_gib": gib(s[2]),
            }
            for s in samples
            if s[0] >= reqs[0]["start"] - 1.0
        ],
        "engine_log_corroboration": {
            "resolution": "second-resolution; not a unique request join",
            "prefill_batch_lines": log.count("Prefill batch"),
            "decode_batch_lines": log.count("Decode batch"),
            "headless_trunk_mentions": len(re.findall(r"headless|trunk", log)),
        },
        "qualifications": [
            "request2 prompt count 32768 is the client's expected count, not confirmed server usage; its cached_tokens is null",
            "prefix32 and an exact request2 new-token count are inference, not ground truth",
            "the issue's '32960' wording is a different quantity from raw observed request1 input 32802",
            "no footprint sample lies between request1 completion and request2 growth"
            if not between
            else "samples exist between requests",
            "QB footprint is a whole-engine sum in the QB probe's domain; ES scheduler-only and tree sums use different baselines",
        ],
    }


# ---------------------------------------------------------------------------------------------
# mechanisms


def ordered_applications(request, name):
    chunks = request["chunks"]
    apps = [
        iv
        for iv in request["interventions"]
        if iv["name"] == name
        and (iv["where"] == "chunk" or name == "QB_DIAG_CLEAR_CACHE_PER_CHUNK")
    ]
    if len(apps) != len(chunks):
        return None
    if name == "QB_DIAG_EVAL_POOL_PER_CHUNK":
        apps = [
            next((iv for iv in apps if iv["chunk"] == c["chunk"]), None) for c in chunks
        ]
        if None in apps or len({id(iv) for iv in apps}) != len(apps):
            return None
    for i, (chunk, iv) in enumerate(zip(chunks, apps, strict=True)):
        seq = chunk.get("seq")
        end = (
            chunks[i + 1].get("seq")
            if i + 1 < len(chunks)
            else request.get("first_decode_seq")
        )
        if (
            seq is None
            or iv.get("seq") is None
            or end is None
            or not seq < iv["seq"] < end
        ):
            return None
    return apps


def active_series(request, intervention_name):
    """(chunk index, post-chunk active) for one request: observe uses chunk.after, eval-pool the intervention's after."""
    if intervention_name is None:
        return [
            (c["chunk"], (c["after"] or {}).get("active")) for c in request["chunks"]
        ]
    apps = ordered_applications(request, intervention_name)
    if apps is None:
        return [(c["chunk"], None) for c in request["chunks"]]
    return [
        (c["chunk"], (iv["after"] or {}).get("active"))
        for c, iv in zip(request["chunks"], apps, strict=True)
    ]


def lazy_scatter_pairing(observe_req, eval_req, name="QB_DIAG_EVAL_POOL_PER_CHUNK"):
    obs = active_series(observe_req, None)
    ev = active_series(eval_req, name)
    if len(obs) != len(ev) or len(obs) < 2:
        return {
            "status": "non_isolated",
            "reason": f"chunk counts differ or <2 (observe {len(obs)}, eval {len(ev)})",
        }
    cap_obs = [c["cache_capacity_tokens"] for c in observe_req["chunks"]]
    cap_ev = [c["cache_capacity_tokens"] for c in eval_req["chunks"]]
    if any(c is None for c in cap_obs + cap_ev):
        return {"status": "incomplete", "reason": "missing cache capacity"}
    geometry_ok = [
        (c["new_tokens"], c["prefix_len"]) for c in observe_req["chunks"]
    ] == [(c["new_tokens"], c["prefix_len"]) for c in eval_req["chunks"]]
    if cap_obs != cap_ev or not geometry_ok:
        return {
            "status": "non_isolated",
            "reason": "per-chunk geometry/capacity differ",
        }
    if any(
        a is None or b is None
        for a, b in zip((x for _, x in obs), (x for _, x in ev), strict=True)
    ):
        return {
            "status": "incomplete",
            "reason": "missing or duplicated intervention application",
        }
    d = [a - b for (_, a), (_, b) in zip(obs, ev, strict=True)]
    rows = []
    cum = 0
    cum_lag = 0
    for j in range(1, len(d)):
        cum += cap_obs[j] * KV_BYTES_PER_TOKEN
        cum_lag += cap_obs[j - 1] * KV_BYTES_PER_TOKEN
        growth = d[j] - d[0]
        rows.append(
            {
                "j": j,
                "D_j_minus_D_0_mib": mib(growth),
                "preregistered_primary_predicted_cumulative_mib_k1_to_j": mib(cum),
                "abs_residual_mib": mib(abs(growth - cum)),
                "within_160MiB": abs(growth - cum) <= 160 * MIB,
                "lag_form_predicted_cumulative_mib_k0_to_jminus1": mib(cum_lag),
                "lag_form_abs_residual_mib": mib(abs(growth - cum_lag)),
                "lag_form_within_160MiB": abs(growth - cum_lag) <= 160 * MIB,
            }
        )
    return {
        "status": "computed",
        "D_0_mib": mib(d[0]),
        "final_D_mib": mib(d[-1]),
        "rows": rows,
        "all_within_160MiB": all(r["within_160MiB"] for r in rows),
        "lag_form_all_within_160MiB": all(r["lag_form_within_160MiB"] for r in rows),
        "caveat": "retrospective on legacy data: legacy cells used chunk2048 with warmup traffic, so this is descriptive, not a preregistered verdict",
    }


def measured_pairs(cells):
    """Pair measured requests of observe/eval-pool cells of the same evidence run by size/repeat tag."""
    by_name = {c["cell"]: c for c in cells}
    pairs = []
    for name, c in by_name.items():
        m = re.fullmatch(r"(p\d+)-observe-(r\d+)", name)
        if not m:
            continue
        other = by_name.get(f"{m.group(1)}-eval-pool-{m.group(2)}")
        if other and c["measured_request_ids"] and other["measured_request_ids"]:
            ro = next(
                r for r in c["requests"] if r["req_id"] == c["measured_request_ids"][0]
            )
            re_ = next(
                r
                for r in other["requests"]
                if r["req_id"] == other["measured_request_ids"][0]
            )
            so, se = c.get("settled") or {}, other.get("settled") or {}
            gap = (
                round(so["active_mib"] - se["active_mib"], 2)
                if None not in (so.get("active_mib"), se.get("active_mib"))
                else None
            )
            predicted = round(
                min(ro["capacity_sum_tokens"], re_["capacity_sum_tokens"])
                * KV_BYTES_PER_TOKEN
                / MIB,
                2,
            )
            pairs.append(
                {
                    "observe": name,
                    "eval_pool": other["cell"],
                    "settled_active_gap_mib": gap,
                    "capacity_sum_x32KiB_mib": predicted,
                    "gap_minus_capacity_sum_mib": round(gap - predicted, 2)
                    if gap is not None
                    else None,
                    **lazy_scatter_pairing(ro, re_),
                }
            )
    return pairs


def source_facts(model_path, engine_site):
    facts = {}
    cfg = Path(model_path) / "config.json" if model_path else None
    if cfg and cfg.exists():
        c = json.loads(cfg.read_text())
        per_token = (
            c["num_hidden_layers"] * c["num_key_value_heads"] * c["head_dim"] * 2 * 2
        )
        facts["model_config"] = {
            "layers": c["num_hidden_layers"],
            "kv_heads": c["num_key_value_heads"],
            "head_dim": c["head_dim"],
            "kv_bytes_per_token_fp16": per_token,
            "agrees_with_32KiB": per_token == KV_BYTES_PER_TOKEN,
            "vocab_size": c.get("vocab_size"),
        }
        v = c.get("vocab_size")
        if v:
            facts["logits_row_bytes_bound"] = {
                "fp16": v * 2,
                "fp32": v * 4,
                "final_chunk_4096_fp32_mib_upper_bound_if_full_chunk_head": mib(
                    4096 * v * 4
                ),
                "last_token_only_fp32_kib": round(v * 4 / 1024, 1),
            }
    runner = (
        Path(engine_site) / "sglang/srt/hardware_backend/mlx/model_runner.py"
        if engine_site
        else None
    )
    if runner and runner.exists():
        text = runner.read_text()
        facts["installed_model_runner"] = {
            "sha256": sha256_file(runner),
            "lines_matching": {
                pat: [
                    i + 1
                    for i, line in enumerate(text.splitlines())
                    if re.search(pat, line)
                ][:12]
                for pat in (r"_trunk_forward", r"_forward_lazy_token", r"needs_logits")
            },
        }
    return facts


def hypotheses(qb, cells, pairs):
    gaps = []
    for p in pairs:
        gaps.append(p)
    return [
        {
            "mechanism": "lazy-scatter / version pinning (WP1 H4; diagnosis H1)",
            "verdict": "consistent_but_not_isolated",
            "evidence": "ES accepted records give matched observe-minus-eval-pool gaps for a single measured request (pre-existing SUPPORTED verdict, unchanged); "
            "chunk-resolved D_j pairing computed above is retrospective. The historical two-request (#406) growth lacks any between-request sample, "
            "so q2 carryover is not identifiable offline.",
            "missing": "per-request q2 pairing with matched eval-pool, planned live",
        },
        {
            "mechanism": "allocator retention (WP1 H1; diagnosis H2)",
            "verdict": "consistent_but_not_isolated",
            "evidence": "mx.cache counters before/after per-chunk clear are reported per intervention; cache counters are not a unique resident-footprint partition.",
            "missing": "clear-cache vs observe pairs at matched chunks (live 16k stage)",
        },
        {
            "mechanism": "parked / private KV cache (WP1 H3; diagnosis H6) and pool realization (diagnosis H3)",
            "verdict": "not_identifiable",
            "evidence": "req_caches_by_id/cache_pool_len traces are reported; metadata bytes alias active bytes and are never added; no-radix has no shared pool; "
            "whether the small 128MiB term is a retained small cache is tested only through the trace, not proven.",
            "missing": "allocation-level residency evidence",
        },
        {
            "mechanism": "logits / final-chunk transients (WP1 H2; diagnosis H4)",
            "verdict": "not_identifiable",
            "evidence": "needs_logits=false is intent; _forward_lazy_token falls back to full forward when _trunk_forward returns None (see source line hits); "
            "peak-minus-active is not a logits allocation measurement.",
            "missing": "branch/allocation instrumentation",
        },
        {
            "mechanism": "in-flight / chained decode pinning (WP1 H7)",
            "verdict": "not_identifiable",
            "evidence": "interval maxima, post-finish decode steps and release windows bound a transient versus retention only.",
            "missing": "scheduling/synchronization intervention",
        },
        {
            "mechanism": "non-MLX process overhead (diagnosis H7)",
            "verdict": "not_identifiable",
            "evidence": "role contributions from synchronized tree samples; footprint-active-cache is a diagnostic proxy across incompatible domains.",
            "missing": "per-allocation attribution",
        },
    ]


# ---------------------------------------------------------------------------------------------
# entry points


def write_outputs(prefix, doc, markdown):
    prefix = Path(prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix(".json").write_text(
        json.dumps(doc, indent=1, sort_keys=True) + "\n"
    )
    prefix.with_suffix(".md").write_text(markdown)


def offline(args):
    manifest = Manifest()
    self_sha = sha256_file(SELF)
    doc = {"analysis_script_sha256": self_sha, "integrity": []}
    qb = qb_analysis(args.qb_raw, manifest)
    doc["qb_two_request_timeline"] = qb
    runs = []
    all_pairs = []
    model_path = None
    for evidence, run, inv_path in runs_in(args.es_evidence_root, manifest):
        run_rel = f"{evidence.name}/runs/{run.name}"
        manifest.add(f"{evidence.name}/logs/{run.name}.raw-sha256.txt", inv_path)
        inventory = read_inventory(inv_path)
        cells = []
        failures = []
        for cell in sorted((run / "cells").iterdir()):
            if not cell.is_dir():
                continue
            try:
                cells.append(cell_analysis(cell, manifest, inventory, run_rel))
            except IntegrityError as exc:
                failures.append({"cell": cell.name, "integrity_failure": str(exc)})
        pairs = measured_pairs(cells)
        all_pairs.extend({"run": run_rel, **p} for p in pairs)
        runs.append(
            {
                "run": run_rel,
                "cells": cells,
                "integrity_failures": failures,
                "lazy_scatter_pairs": pairs,
            }
        )
        if model_path is None:
            for t in sorted(evidence.glob("*.toml")):
                m = re.search(r'model_path = "([^"]+)"', t.read_text())
                if m:
                    model_path = m.group(1)
                    break
    doc["es_runs"] = runs
    doc["source_facts"] = source_facts(
        model_path,
        "/opt/local/Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/site-packages",
    )
    doc["hypotheses"] = hypotheses(qb, [c for r in runs for c in r["cells"]], all_pairs)
    doc["corrections_of_prior_assertions"] = [
        "needs_logits=false is source intent only; _forward_lazy_token falls back to a full forward when _trunk_forward returns None",
        "no-radix has no shared pool: never subtract the nominal pool from its accounting",
        "prefix32 for #406 request2 is inferred; request2 cached_tokens and body are null/unrecorded",
        "the 21917MiB figure is a scheduler sampled peak, not a whole-tree peak; compare tree sums only with tree sums",
        "per-role lifetime maxima summed together are not a simultaneous sampled tree peak",
        "historical hypothesis numbers are not interchangeable: diagnosis H1=WP1 H4 lazy-scatter, H2=WP1 H1 allocator retention, H4=WP1 H2 logits, "
        "H6=WP1 H3 parked cache, H3 shared-pool realization, H7 non-MLX process memory (not WP1 H7 in-flight pinning)",
    ]
    doc["growth_formula_finding"] = (
        "The PLANNED form is the primary prospective verdict; the lag form is a secondary additional prediction. "
        "Legacy pairs fit the lag form within 160MiB, while the planned form fails at multi-doubling sizes. "
        "A one-chunk realization lag is a hypothesis explaining this pattern, not a measured fact."
    )
    doc["inputs"] = manifest.as_list()
    write_outputs(args.out, doc, render_offline(doc))
    Path(str(args.out) + ".inputs.sha256.txt").write_text(
        "".join(f"{e['sha256']}  {e['path']}\n" for e in doc["inputs"])
    )
    return 0


def render_offline(doc):
    lines = [
        "# Offline causal analysis",
        "",
        f"analysis script sha256: `{doc['analysis_script_sha256']}`",
        "",
    ]
    qb = doc["qb_two_request_timeline"]
    lines += ["## QB #406 two-request timeline", ""]
    if qb.get("status") != "available":
        lines += [f"unavailable: {qb.get('reason')}", ""]
    else:
        op = qb["operands"]
        lines += ["| quantity | value |", "|---|---|"]
        for k, v in op.items():
            lines.append(f"| {k} | {v} |")
        lines += [
            "",
            f"request1: {json.dumps({k: qb['request1'][k] for k in ('input_tokens', 'client_cached_tokens', 'output_tokens', 'start', 'end')})}",
            "",
            f"request2: {json.dumps({k: qb['request2'][k] for k in ('status', 'input_tokens', 'client_cached_tokens', 'output_tokens', 'start', 'end')})}",
            "",
        ]
        lines += [f"- {q}" for q in qb["qualifications"]] + [""]
    lines += [
        "## ES evidence per-cell summary",
        "",
        "| run | cell | measured req | chunks | capacity sum x32KiB MiB | tree peak MiB | scheduler-only peak MiB | sum of role lifetime maxima MiB (not simultaneous) | parser gaps |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in doc["es_runs"]:
        for c in r["cells"]:
            m = next((x for x in c["requests"] if x["phase"] == "measured"), None)
            t = c["tree"] or {}
            lines.append(
                f"| {r['run'].split('/')[-1]} | {c['cell']} | {m['req_id'][:8] if m else '-'} | {len(m['chunks']) if m else '-'} | "
                f"{m['capacity_x32KiB_mib'] if m else '-'} | {t.get('engine_tree_peak_sampled_mib')} | {t.get('scheduler_only_peak_sampled_mib')} | "
                f"{t.get('sum_of_role_lifetime_maxima_mib_NOT_a_simultaneous_peak')} | {t.get('parser_discovery_gap_samples')} |"
            )
    lines += [
        "",
        "## Matched observe / eval-pool chunk-resolved pairs (retrospective)",
        "",
    ]
    for r in doc["es_runs"]:
        for p in r["lazy_scatter_pairs"]:
            lines.append(
                f"- {r['run'].split('/')[-1]} {p['observe']} vs {p['eval_pool']}: settled active gap {p['settled_active_gap_mib']} MiB vs capacity sum x32KiB {p['capacity_sum_x32KiB_mib']} MiB (diff {p['gap_minus_capacity_sum_mib']}); chunk-resolved: {p['status']}"
                + (
                    f"; D_0={p.get('D_0_mib')} final D={p.get('final_D_mib')} MiB; all within 160MiB={p.get('all_within_160MiB')}; lag form (k=0..j-1) all within={p.get('lag_form_all_within_160MiB')}"
                    if p["status"] == "computed"
                    else f" ({p.get('reason')})"
                )
            )
    lines += ["", "## Hypotheses", ""]
    for h in doc["hypotheses"]:
        lines += [
            f"### {h['mechanism']}",
            f"verdict: **{h['verdict']}**",
            "",
            h["evidence"],
            "",
            f"missing: {h['missing']}",
            "",
        ]
    lines += ["## Growth-formula finding", "", doc["growth_formula_finding"], ""]
    lines += ["## Corrections of prior assertions", ""] + [
        f"- {c}" for c in doc["corrections_of_prior_assertions"]
    ]
    lines += [
        "",
        f"Consumed inputs: {len(doc['inputs'])} (full sorted list with digests in the JSON).",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------
# live (sequence) analysis

HARD = "hard_fidelity_failures"
SCI = "scientific_inconclusive"
TOLERANCE_MIB = 160
CACHE_DROP_MIB = 64
ACTIVE_CHANGE_MIB = 16


def verify_run_inventory(run, inventory, manifest, run_rel):
    """Every harvested file must be listed with a matching digest; captures are excluded from harvested copies."""
    on_disk = {
        p.relative_to(run).as_posix(): p for p in sorted(run.rglob("*")) if p.is_file()
    }
    for rel, path in on_disk.items():
        expected = inventory.get(rel)
        if expected is None:
            raise IntegrityError(f"{rel}: not in inventory")
        manifest.add(f"{run_rel}/{rel}", path, expected)
    listed_missing = [
        r for r in inventory if "/captures/" not in r and r not in on_disk
    ]
    if listed_missing:
        raise IntegrityError(
            f"inventory lists files absent from the harvested run: {listed_missing[:3]}"
        )


def match_requests(ledger, worker_requests):
    """Attribute shim requests to worker requests by exact RID or the response ID; never by order or chunk discovery."""
    matched = {}
    for wr in worker_requests:
        rid, response_id = wr.get("rid"), wr.get("response_id")
        hits = [
            (row, how)
            for row in ledger
            for how, ok in (
                ("exact_rid", row["req_id"] == rid),
                (
                    "response_id",
                    bool(response_id)
                    and (
                        response_id == row["req_id"]
                        or str(response_id).endswith(str(row["req_id"]))
                    ),
                ),
            )
            if ok
        ]
        distinct = {row["req_id"] for row, _ in hits}
        matched[wr["ordinal"]] = {
            "rid": rid,
            "shim_req_id": next(iter(distinct)) if len(distinct) == 1 else None,
            "how": hits[0][1] if len(distinct) == 1 else None,
            "ambiguous": len(distinct) > 1,
        }
    return matched


def live_cell(cell, manifest, run_rel, fixtures=None):
    outcome = load_json(cell / "outcome.json")
    man = load_json(cell / "manifest.json")
    variant = man.get("variant") or {}
    workload = (man.get("scenario") or {}).get("workload") or {}
    eff = {**workload, **variant}
    events = (
        jsonl(cell / "shim-telemetry.jsonl")
        if (cell / "shim-telemetry.jsonl").exists()
        else []
    )
    report = (
        load_json(cell / "workload" / "capture.json")
        if (cell / "workload" / "capture.json").exists()
        else {}
    )
    wreqs = report.get("requests") or []
    ledger = build_ledger(events)
    match = match_requests(ledger, wreqs)
    by_id = {r["req_id"]: r for r in ledger}
    hard, sci = [], []
    init = [e for e in events if e.get("ev") == "runner_init"]
    if not init or any(
        e.get("pool_size") != variant.get("max_total_tokens") for e in init
    ):
        hard.append("runner_init pool_size missing or differs from variant")
    for event in events:
        if event.get("ev") == "chunk" and (
            not isinstance(event.get("new_tokens"), int)
            or not isinstance(variant.get("chunked_prefill_size"), int)
            or event["new_tokens"] > variant["chunked_prefill_size"]
        ):
            hard.append("chunk exceeds configured prefill size or has missing size")
    if len(wreqs) >= 2:
        terminal, send, gap = (
            wreqs[0].get("monotonic_terminal"),
            wreqs[1].get("monotonic_send"),
            report.get("inter_request_gap_s"),
        )
        if (
            not isinstance(terminal, (int, float))
            or not isinstance(send, (int, float))
            or send <= terminal
            or not isinstance(gap, (int, float))
            or gap < 0
        ):
            hard.append("q2 send ordering or inter-request gap invalid")
    if outcome.get("engine") != "completed":
        hard.append(f"engine outcome {outcome.get('engine')!r}")
    if outcome.get("cleanup") != "confirmed":
        hard.append(f"cleanup {outcome.get('cleanup')!r}")
    expected_n = eff.get("requests")
    if len(wreqs) != expected_n:
        hard.append(f"worker reported {len(wreqs)} of {expected_n} requests")
    diag = (
        load_json(cell / "diagnostic.json")
        if (cell / "diagnostic.json").exists()
        else {}
    )
    intervention = (
        (diag.get("diagnostic") or {}).get("intervention")
        or diag.get("intervention")
        or {}
    )
    requests = []
    for wr in wreqs:
        if fixtures is not None and eff.get("output_tokens") == 128:
            repeat = re.search(r"-r(\d+)$", cell.name)
            fixture = (
                fixtures.get(str(eff.get("prompt_tokens")), {})
                .get("repeats", {})
                .get(repeat.group(1) if repeat else "", {})
            )
            body = (
                1
                if wr["ordinal"] == 1 or eff.get("request_relation") == "identical"
                else 2
            )
            if (
                not fixture.get(f"body{body}_sha256")
                or wr.get("body_sha256") != fixture[f"body{body}_sha256"]
            ):
                hard.append(f"request q{wr['ordinal']}: fixture body hash mismatch")
        m = match[wr["ordinal"]]
        row = by_id.get(m["shim_req_id"])
        if wr.get("status") != "completed":
            hard.append(
                f"request q{wr['ordinal']} status {wr.get('status')!r}: {wr.get('failure')}"
            )
        if row is None:
            hard.append(
                f"request q{wr['ordinal']}: no shim request with exact RID/response ID (ambiguous={m['ambiguous']})"
            )
        elif row["request_finish"] is None and wr.get("status") == "completed":
            hard.append(f"request q{wr['ordinal']}: no request_finish")
        entry = {
            "ordinal": wr["ordinal"],
            "rid": wr.get("rid"),
            "response_id": wr.get("response_id"),
            "status": wr.get("status"),
            "failure": wr.get("failure"),
            "body_sha256": wr.get("body_sha256"),
            "transmitted_sha256": wr.get("transmitted_sha256"),
            "observed_input_tokens": wr.get("observed_input_tokens"),
            "observed_output_tokens": wr.get("observed_output_tokens"),
            "client_cached_tokens": wr.get("cached_tokens"),
            "monotonic_send": wr.get("monotonic_send"),
            "monotonic_first_token": wr.get("monotonic_first_token"),
            "monotonic_terminal": wr.get("monotonic_terminal"),
            "attribution": m,
            "shim": row,
        }
        if row is not None:
            s, prefix, observed = (
                row["sum_new_tokens"],
                row["measured_prefix_len"],
                wr.get("observed_input_tokens"),
            )
            entry["token_equation"] = {
                "observed_input": observed,
                "measured_prefix_len": prefix,
                "sum_new_tokens": s,
                "holds": (observed == prefix + s)
                if None not in (observed, prefix, s)
                else None,
            }
            if entry["token_equation"]["holds"] is False:
                hard.append(f"request q{wr['ordinal']}: token equation fails")
            if (
                not row["chunks"]
                and wr["ordinal"] == 2
                and eff.get("request_relation") == "identical"
            ):
                entry["zero_chunk_full_prefix_hit"] = (
                    observed is not None
                    and observed > 0
                    and wr.get("cached_tokens") == observed
                )
                if not entry["zero_chunk_full_prefix_hit"]:
                    hard.append(
                        "identical q2 zero-chunk full-prefix accounting missing"
                    )
            if (
                wr["ordinal"] == 2
                and eff.get("request_relation") == "distinct"
                and len(row["chunks"]) < 2
            ):
                sci.append("distinct q2 executed fewer than two chunks: non_isolated")
        requests.append(entry)
    # Only a pre-sequence health request with removal-only later activity is disclosed.
    attributed = {m["shim_req_id"] for m in match.values() if m["shim_req_id"]}
    sends = [
        wr["monotonic_send"] for wr in wreqs if wr.get("monotonic_send") is not None
    ]
    q1_send = wreqs[0].get("monotonic_send") if wreqs else None
    terminals = [
        wr["monotonic_terminal"]
        for wr in wreqs
        if wr.get("monotonic_terminal") is not None
    ]
    window_end = max(terminals + sends) if (terminals or sends) else None
    stray = [row["req_id"] for row in ledger if row["req_id"] not in attributed]
    disclosed = []
    for row in ledger:
        if row["req_id"] in attributed:
            continue
        first = row["first_mono"]
        if not (
            re.fullmatch(r"HEALTH_CHECK_[0-9a-f]+", row["req_id"])
            and isinstance(q1_send, (int, float))
            and isinstance(first, (int, float))
            and first < q1_send
        ):
            continue
        allowed = (
            "remove_request.enter",
            "remove_request.exit",
            "release_request_row.enter",
            "release_request_row.exit",
            "request_state_removed",
            "request_finish",
            "request_end",
        )
        if any(
            not isinstance(event["mono"], (int, float))
            or (event["mono"] >= q1_send and event["ev"] not in allowed)
            for event in row["events_in_order"]
        ):
            continue
        disclosed.append(
            {
                "req_id": row["req_id"],
                "first_mono": first,
                "removal_events": [
                    event for event in row["events_in_order"] if event["ev"] in allowed
                ],
                "chunk_visibility": [
                    {
                        "ordinal": request["ordinal"],
                        "rid": request["rid"],
                        "chunk": chunk["chunk"],
                        "mono": chunk["mono"],
                        "visible": row["req_id"] in (chunk["other_live_ids"] or []),
                    }
                    for request in requests
                    if request["shim"]
                    for chunk in request["shim"]["chunks"]
                ],
            }
        )
    disclosed_ids = {peer["req_id"] for peer in disclosed}
    disclosed_diagnostic_problems = []
    for problem in intervention.get("problems") or []:
        match_peer = (
            re.fullmatch(
                r"request \d+: active or unknown live peer (HEALTH_CHECK_[0-9a-f]+)",
                problem,
            )
            if isinstance(problem, str)
            else None
        )
        if match_peer and match_peer.group(1) in disclosed_ids:
            disclosed_diagnostic_problems.append(problem)
        else:
            hard.append(f"intervention: {problem}")
    for row in ledger:
        if row["req_id"] not in attributed and row["first_mono"] is None:
            hard.append(
                f"unattributed request {row['req_id']} has unknown monotonic time"
            )
    for row in ledger:
        if (
            row["req_id"] not in attributed
            and q1_send is not None
            and row["first_mono"] is not None
            and q1_send <= row["first_mono"] <= window_end
        ):
            hard.append(
                f"unattributed request {row['req_id']} inside the measured sequence window (unknown peer or health traffic)"
            )
        elif row["req_id"] not in attributed and row["req_id"] not in disclosed_ids:
            if any(
                (
                    not isinstance(event["mono"], (int, float))
                    or (
                        q1_send is not None
                        and event["mono"] >= q1_send
                        and (
                            re.fullmatch(r"HEALTH_CHECK_[0-9a-f]+", row["req_id"])
                            or (window_end is not None and event["mono"] <= window_end)
                        )
                    )
                )
                for event in row["events_in_order"]
            ):
                hard.append(
                    f"unattributed request {row['req_id']} has activity inside the measured sequence window"
                )
    other_live = sorted(
        {
            rid
            for e in requests
            if e["shim"]
            for c in e["shim"]["chunks"]
            for rid in (c["other_live_ids"] or [])
            if rid
        }
    )
    unsafe_live = sorted(set(other_live) - disclosed_ids)
    if unsafe_live:
        hard.append(f"live peers observed: {unsafe_live}")
    # lower-bound classification: confirmed cap with a measured trajectory, never inferred from timeouts
    status = "complete"
    if hard:
        status = (
            "lower_bound"
            if (
                outcome.get("engine") == "capped"
                and any(e["shim"] and e["shim"]["chunks"] for e in requests)
            )
            else "incomplete"
        )
    gap = report.get("inter_request_gap_s")
    q1_release = None
    if (
        len(requests) == 2
        and requests[0]["shim"]
        and requests[1]["monotonic_send"] is not None
    ):
        r1 = requests[0]["shim"]
        q1_release = {
            "request_end_ts": (r1["request_end"] or {}).get("ts"),
            "request_state_removed_ts": (r1["request_state_removed"] or {}).get("ts"),
        }
    return {
        "cell": cell.name,
        "variant": variant,
        "run": run_rel,
        "effective": {
            k: eff.get(k)
            for k in ("prompt_tokens", "output_tokens", "requests", "request_relation")
        },
        "outcome": {
            "engine": outcome.get("engine"),
            "cleanup": outcome.get("cleanup"),
            "abort_sweep": outcome.get("abort_sweep"),
            "exit_classification": outcome.get("exit_classification"),
        },
        "status": status,
        HARD: hard,
        SCI: sorted(set(sci)),
        "inter_request_gap_s_q1_terminal_to_q2_send": gap,
        "q1_release_observed": q1_release,
        "unattributed_shim_requests_before_after": stray,
        "disclosed_health_peers": disclosed,
        "disclosed_health_peer_diagnostic_problems": disclosed_diagnostic_problems,
        "other_live_ids_seen_by_attributed_chunks": other_live,
        "requests": requests,
        "pool_events": non_ledger_events(events),
        "tree": tree_summary(cell, None)
        if (cell / "processes.jsonl").exists()
        else None,
        "settled": settled_sample(events, cell / "diagnostic.json")
        if (cell / "diagnostic.json").exists()
        else None,
    }


def clear_cache_effect(request):
    rows = []
    for iv in (request.get("shim") or {}).get("interventions") or []:
        if iv.get("name") != "QB_DIAG_CLEAR_CACHE_PER_CHUNK":
            continue
        b, a = iv.get("before") or {}, iv.get("after") or {}
        if None in (b.get("cache"), a.get("cache"), b.get("active"), a.get("active")):
            continue
        drop, dact = mib(b["cache"] - a["cache"]), mib(a["active"] - b["active"])
        rows.append(
            {
                "chunk": iv.get("chunk"),
                "cache_freed_mib": drop,
                "active_change_mib": dact,
                "footprint_change_mib": mib(
                    (a.get("footprint") or 0) - (b.get("footprint") or 0)
                )
                if None not in (a.get("footprint"), b.get("footprint"))
                else None,
                "selective": drop >= CACHE_DROP_MIB and abs(dact) <= ACTIVE_CHANGE_MIB,
            }
        )
    return rows


def pair_key(cell):
    e, v = cell["effective"], cell["variant"]
    repeat = int(re.search(r"-r(\d+)$", cell["cell"]).group(1))
    return (
        repeat,
        e["prompt_tokens"],
        v.get("max_total_tokens"),
        v.get("chunked_prefill_size"),
        e["output_tokens"],
        e["requests"],
        e["request_relation"],
    )


def arm(cell):
    return cell["variant"].get("diagnostic_mode") or "observe"


def request_sequences(request):
    shim = request["shim"] or {}
    return [
        (c["new_tokens"], c["prefix_len"], c["cache_capacity_tokens"])
        for c in shim.get("chunks", [])
    ]


def contrast(obs, other, mode):
    """Matched same-repeat contrast of an observe cell against an eval-pool/clear-cache cell."""
    name = {
        "eval_pool_per_chunk": "QB_DIAG_EVAL_POOL_PER_CHUNK",
        "clear_cache_per_chunk": "QB_DIAG_CLEAR_CACHE_PER_CHUNK",
    }[mode]
    out = {
        "observe": obs["cell"],
        "other": other["cell"],
        "mode": mode,
        "per_request": [],
    }

    def peer_sequence(cell, request):
        ids = {
            r.get("rid"): f"q{r['ordinal']}"
            for r in cell["requests"]
            if isinstance(r.get("rid"), str)
        }
        result = []
        for chunk in request["shim"]["chunks"]:
            peers = chunk.get("other_live_ids")
            count = chunk.get("other_live_requests")
            if not isinstance(peers, list) or not isinstance(count, int):
                return None
            if any(not isinstance(peer, str) for peer in peers):
                return None
            normalized = [
                "HEALTH"
                if re.fullmatch(r"HEALTH_CHECK_[0-9a-f]+", peer)
                else ids.get(peer, peer)
                for peer in peers
            ]
            result.append((count, tuple(sorted(normalized))))
        return result

    for ro, rx in zip(obs["requests"], other["requests"], strict=False):
        item = {"ordinal": ro["ordinal"]}
        same_input = ro["body_sha256"] == rx["body_sha256"]
        same_work = (
            ro["observed_input_tokens"] == rx["observed_input_tokens"]
            and ro["observed_output_tokens"] == rx["observed_output_tokens"]
            and request_sequences(ro) == request_sequences(rx)
        )
        if not ro["shim"] or not rx["shim"]:
            item.update(status="incomplete", reason="missing request attribution")
        elif any(
            c["cache_capacity_tokens"] is None
            for r in (ro, rx)
            for c in r["shim"]["chunks"]
        ):
            item.update(status="incomplete", reason="missing cache capacity")
        elif ordered_applications(rx["shim"], name) is None:
            item.update(
                status="incomplete",
                reason="missing, duplicated or out-of-order intervention",
            )
        elif peer_sequence(obs, ro) is None or peer_sequence(other, rx) is None:
            item.update(status="incomplete", reason="missing per-chunk live-peer data")
        elif peer_sequence(obs, ro) != peer_sequence(other, rx):
            item.update(
                status="non_isolated",
                reason="per-chunk live-peer counts or identities differ",
            )
        elif not (same_input and same_work):
            item["status"] = "non_isolated"
            item["reason"] = (
                "canonical input hash, observed counts or per-chunk new_tokens/prefix/capacity sequence differ"
            )
        elif (
            ro["ordinal"] == 2
            and obs["effective"]["request_relation"] == "identical"
            and len(ro["shim"]["chunks"]) < 2
        ):
            item["status"] = "not_applicable"
        elif mode == "eval_pool_per_chunk":
            item.update(lazy_scatter_pairing(ro["shim"], rx["shim"], name))
            item["capacity_sum_x32KiB_mib"] = ro["shim"]["capacity_x32KiB_mib"]
            if ro["shim"]["chunks"] and rx["shim"]["chunks"]:
                obs_a = active_series(ro["shim"], None)
                ev_a = active_series(rx["shim"], name)
                if (
                    obs_a
                    and ev_a
                    and None not in (obs_a[0][1], ev_a[0][1], obs_a[-1][1], ev_a[-1][1])
                ):
                    item["D_0_mib"] = mib(obs_a[0][1] - ev_a[0][1])
                    item["final_active_gap_mib"] = mib(obs_a[-1][1] - ev_a[-1][1])
        else:
            if not rx["shim"]["chunks"] or len(clear_cache_effect(rx)) != len(
                rx["shim"]["chunks"]
            ):
                item.update(
                    status="incomplete",
                    reason="missing clear-cache applications or snapshots",
                )
                out["per_request"].append(item)
                continue
            item["status"] = "computed"
            item["observe_chunks"] = clear_cache_effect(ro)
            item["clear_cache_chunks"] = clear_cache_effect(rx)
            item["any_selective_effect"] = any(
                r["selective"] for r in item["clear_cache_chunks"]
            )
            item["note"] = (
                "decode/release growth is not isolated by a per-prefill intervention"
            )
        out["per_request"].append(item)
    reqs = out["per_request"]
    if len(reqs) == 2 and all("D_0_mib" in r for r in reqs):
        out["carryover_descriptive_no_tolerance"] = {
            "D_0_q2_minus_D_0_q1_mib": round(
                reqs[1]["D_0_mib"] - reqs[0]["D_0_mib"], 2
            ),
            "final_q2_active_gap_mib": reqs[1].get("final_active_gap_mib"),
            "q1_capacity_sum_x32KiB_mib": reqs[0].get("capacity_sum_x32KiB_mib"),
            "q2_capacity_sum_x32KiB_mib": reqs[1].get("capacity_sum_x32KiB_mib"),
            "q1_plus_q2_capacity_mib": round(
                reqs[0].get("capacity_sum_x32KiB_mib", 0)
                + reqs[1].get("capacity_sum_x32KiB_mib", 0),
                2,
            ),
            "q1_settled_gap": "unavailable: no sample between q1 release and q2 send unless one lies in the recorded gap",
        }
    return out


def aggregate(contrasts, planned_repeats=2):
    """A positive complete contrast needs every planned repeat, every request computed and within tolerance."""
    groups = {}
    for c in contrasts:
        key = (c["mode"], tuple(c["group"]))
        groups.setdefault(key, []).append(c)
    out = []
    for (mode, group_key), items in sorted(groups.items(), key=lambda kv: str(kv[0])):
        group = list(group_key)
        repeats = sorted({c["repeat"] for c in items})
        entry = {
            "mode": mode,
            "group": group,
            "repeats_present": repeats,
            "planned_repeats": planned_repeats,
        }
        computed = [
            r for c in items for r in c["per_request"] if r.get("status") == "computed"
        ]
        non_iso = [
            r
            for c in items
            for r in c["per_request"]
            if r.get("status") == "non_isolated"
        ]
        if mode == "eval_pool_per_chunk":
            entry["planned_form_all_within_160MiB"] = [
                r.get("all_within_160MiB") for r in computed
            ]
            entry["lag_form_all_within_160MiB"] = [
                r.get("lag_form_all_within_160MiB") for r in computed
            ]
        entry["non_isolated_or_incomplete_requests"] = len(non_iso)
        incomplete = [
            r
            for c in items
            for r in c["per_request"]
            if r.get("status") in ("incomplete", "unpaired_pending_cross_run")
        ]
        if len(repeats) < planned_repeats:
            entry["verdict"] = "incomplete_missing_repeat"
        elif incomplete:
            entry["verdict"] = (
                "unpaired_pending_cross_run"
                if all(r["status"] == "unpaired_pending_cross_run" for r in incomplete)
                else "incomplete"
            )
        elif non_iso:
            entry["verdict"] = "non_isolated"
        elif mode == "eval_pool_per_chunk":
            planned = all(entry["planned_form_all_within_160MiB"])
            lag = all(entry["lag_form_all_within_160MiB"])
            entry["verdict"] = {
                "planned_form": "supported" if planned else "contradicted",
                "lag_form": "supported" if lag else "contradicted",
            }
        else:
            entry["verdict"] = "computed_descriptive"
        out.append(entry)
    return out


def live_main(args):
    run = Path(args.run)
    manifest = Manifest()
    inventory = read_inventory(args.inventory)
    run_rel = run.name
    manifest.add(f"logs/{Path(args.inventory).name}", args.inventory)
    manifest.add(f"plan/{Path(args.plan).name}", args.plan)
    plan = load_json(args.plan)
    planned = plan.get("cells") or []
    if not planned or any(
        not c.get("cell_id") or not isinstance(c.get("repeat"), int) for c in planned
    ):
        raise IntegrityError("plan has no valid cells")
    expected = {c["cell_id"] for c in planned}
    if len(expected) != len(planned):
        raise IntegrityError("duplicate planned cell ids")
    fixtures = load_json(args.fixtures_summary) if args.fixtures_summary else None
    if args.fixtures_summary:
        manifest.add(
            f"fixtures/{Path(args.fixtures_summary).name}", args.fixtures_summary
        )
    if not (run / "cells").is_dir() or not any(
        p.is_dir() for p in (run / "cells").iterdir()
    ):
        raise IntegrityError("run has no cells")
    verify_run_inventory(run, inventory, manifest, run_rel)
    cells = []
    summary = load_json(run / "summary.json") if (run / "summary.json").exists() else {}
    for cell_dir in sorted((run / "cells").iterdir()):
        if cell_dir.is_dir():
            cells.append(live_cell(cell_dir, manifest, run_rel, fixtures))
    for spec_text in args.also or []:
        try:
            extra_run, extra_inventory = (Path(p) for p in spec_text.rsplit(":", 1))
        except ValueError as exc:
            raise IntegrityError("invalid --also RUN:INVENTORY") from exc
        manifest.add(f"logs/{extra_inventory.name}", extra_inventory)
        verify_run_inventory(
            extra_run, read_inventory(extra_inventory), manifest, extra_run.name
        )
        for cell_dir in sorted((extra_run / "cells").iterdir()):
            if cell_dir.is_dir():
                cells.append(live_cell(cell_dir, manifest, extra_run.name, fixtures))
    contrasts = []
    by_key = {}
    for c in cells:
        by_key.setdefault((pair_key(c), arm(c)), c)
    for (key, mode), other in sorted(by_key.items(), key=lambda kv: str(kv[0])):
        if mode == "observe":
            continue
        obs = by_key.get((key, "observe"))
        if run_rel not in ((obs or {}).get("run"), other["run"]):
            continue
        if obs is None or other["status"] != "complete" or obs["status"] != "complete":
            contrasts.append(
                {
                    "mode": mode,
                    "group": list(key[1:]),
                    "repeat": key[0],
                    "per_request": [
                        {
                            "status": "unpaired_pending_cross_run"
                            if obs is None and other["status"] == "complete"
                            else "incomplete",
                            "reason": "cell missing or not complete",
                        }
                    ],
                }
            )
            continue
        item = contrast(obs, other, mode)
        item.update(group=list(key[1:]), repeat=key[0])
        contrasts.append(item)
    cells = [c for c in cells if c["run"] == run_rel]
    hard = {c["cell"]: c[HARD] for c in cells if c[HARD]}
    statuses = {c["cell"]: c["status"] for c in cells}
    statuses.update({name: "not_run" for name in expected - statuses.keys()})
    valid = (
        summary.get("exit_code") == 0
        and set(c["cell"] for c in cells) == expected
        and not hard
        and not summary.get("abort_sweep")
        and not any(c["outcome"].get("abort_sweep") for c in cells)
    )
    gate = "pass" if valid else ("final_stage_outcome" if args.final_stage else "stop")
    repeat_status = {c["repeat"]: statuses[c["cell_id"]] for c in planned}
    stage_status = (
        "complete"
        if valid and all(s == "complete" for s in statuses.values())
        else (
            "incomplete_single_repeat_lower_bound"
            if args.final_stage
            and repeat_status.get(1) == "lower_bound"
            and repeat_status.get(2) == "not_run"
            else "incomplete"
        )
    )
    doc = {
        "analysis_script_sha256": sha256_file(SELF),
        "run": run_rel,
        "run_exit_code": summary.get("exit_code"),
        "run_reason": summary.get("reason"),
        "cells": cells,
        "contrasts": contrasts,
        "aggregate": aggregate(contrasts, max(c["repeat"] for c in planned)),
        "stage_gate": {
            "status": gate,
            HARD: hard,
            SCI: {c["cell"]: c[SCI] for c in cells if c[SCI]},
        },
        "cell_status": statuses,
        "stage_status": stage_status,
        "inputs": manifest.as_list(),
        "scope_note": "no between-request sample implies no manufactured q1 settled plateau; a capped request gives a lower bound only; "
        "27904MiB scheduler cap is configured_not_read_back",
    }
    write_outputs(args.out, doc, render_live(doc))
    return 0 if gate == "pass" else 5


def render_live(doc):
    lines = [
        f"# Live analysis: {doc['run']}",
        "",
        f"analysis script sha256: `{doc['analysis_script_sha256']}`",
        f"stage gate: **{doc['stage_gate']['status']}**",
        "",
    ]
    lines += [
        "| cell | status | engine | q1 in/out/cache | q2 in/out/cache | gap s | chunks q1/q2 | tree peak MiB | scheduler-only MiB |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for c in doc["cells"]:

        def rq(i, c=c):
            if i >= len(c["requests"]):
                return "-"
            r = c["requests"][i]
            return f"{r['observed_input_tokens']}/{r['observed_output_tokens']}/{r['client_cached_tokens']}"

        def ch(i, c=c):
            return (
                len(c["requests"][i]["shim"]["chunks"])
                if i < len(c["requests"]) and c["requests"][i]["shim"]
                else "-"
            )

        t = c["tree"] or {}
        lines.append(
            f"| {c['cell']} | {c['status']} | {c['outcome']['engine']} | {rq(0)} | {rq(1)} | {c['inter_request_gap_s_q1_terminal_to_q2_send']} | {ch(0)}/{ch(1)} | "
            f"{t.get('engine_tree_peak_sampled_mib')} | {t.get('scheduler_only_peak_sampled_mib')} |"
        )
    lines += ["", "## Disclosed pre-sequence health peers", ""]
    lines += [
        f"- {c['cell']}: {json.dumps(c.get('disclosed_health_peers', []), sort_keys=True)}"
        for c in doc["cells"]
    ] or ["none"]
    lines += ["", "## Contrasts", ""]
    for a in doc["aggregate"]:
        lines.append(
            f"- {a['mode']} {a['group']}: repeats {a['repeats_present']}/{a['planned_repeats']} -> {a['verdict']}"
        )
    lines += ["", "## Hard fidelity failures", ""]
    lines += [f"- {k}: {v}" for k, v in doc["stage_gate"][HARD].items()] or ["none"]
    lines += ["", "## Scientific inconclusive", ""]
    lines += [f"- {k}: {v}" for k, v in doc["stage_gate"][SCI].items()] or ["none"]
    lines += ["", doc["scope_note"], ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    off = sub.add_parser("offline")
    off.add_argument("--es-evidence-root", required=True)
    off.add_argument("--qb-raw", required=True)
    off.add_argument("--out", required=True)
    live = sub.add_parser("live")
    live.add_argument("--run", required=True)
    live.add_argument("--inventory", required=True)
    live.add_argument("--out", required=True)
    live.add_argument("--plan", required=True)
    live.add_argument("--fixtures-summary")
    live.add_argument("--final-stage", action="store_true")
    live.add_argument(
        "--also",
        action="append",
        help="RUN_DIR:INVENTORY of another verified run, for cross-run pairing only",
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "offline":
            return offline(args)
        return live_main(args)
    except IntegrityError as exc:
        print(f"integrity failure: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
