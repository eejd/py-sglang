# SGLang causal replay: results

Contract: `PREREG.md` (two review rounds + Amendment 1; owner authorization recorded on QB #419/#452/#454). Diagnostic ES evidence: one model (Llama-3.2-1B-Instruct-4bit, pinned revision), one host (Mac17,16, 64 GiB), one SGLang build, observe-first containment, streams 1, no synthetic warmup, no capture. Not a QuantBench calibration point or benchmark. Accepted records (including the 32k H4 SUPPORTED) are unchanged. **65536 was not run.** Machine outputs: `OFFLINE_ANALYSIS.*`, `sequence-smoke-a2.*`, `history-16k.*`, `bridge-32k.*`, `historical-pair-32k.*`; raw digests in `logs/*.raw-sha256.txt`.

## Run ledger

| Run | Cells | Outcome |
|---|---|---|
| `sequence-smoke` (attempt 1) | 1 of 4 ran | Stopped by the preregistered hard rule: SGLang's own `HEALTH_CHECK` request (fired by the readiness probe) lingered as a live peer through q1. Cells 2-4 `not_run`. Preserved, never merged. |
| `sequence-smoke-a2` (after Amendment 1, rule H) | 4/4 complete | gate pass |
| `history-16k` | 14/14 complete | gate pass |
| (admission refusal, `logs/refused-bridge-32k-attempt0/`) | 0 ran | host admission refused (non-owned CPU >= 25 % for three intervals) before any engine started; no run directory; retried under the same name once the host was idle |
| `bridge-32k` | 12/12 complete | gate pass |
| `historical-pair-32k` | repeat 1 ran, repeat 2 `not_run` | **capped** in q2 (`exit_classification.kind = capped`, "scheduler exited with kernel footprint-cap reason"); cleanup confirmed, swap 0, nothing left running. Stage status `incomplete_single_repeat_lower_bound`. |

31 of the planned 32 cells ran in the accepted attempts (4 + 14 + 12 + 1; the failed first smoke attempt's 1 cell is additional and separately recorded); the stage-4 repeat-2 cell is `not_run` by rule. No extra cells were added. No retries, deadline raises or cap raises.

## Reconstruction fidelity

32768 repeat-1 body1 equals the recorded QB #406 request 1 body exactly (canonical SHA equality). Request 2's body was never recorded, so body2 is a same-seed reconstruction of unknown fidelity: this is a **controlled historical-shaped reconstruction**, not an exact reproduction. Bodies share only the 32-token template prefix. Achieved q1-terminal-to-q2-send gap was 14-25 ms (not the historical ~2 ms; it includes the safety fence).

## Main finding: the second request starts from the first request's final cache capacity

In every two-request cell, q2's first chunk uses the capacity q1 ended with, and the retained-version growth then restarts at that large capacity:

| size / chunk | q1 chunk capacities (first -> last) | q2 first capacity | q1 capacity sum x 32 KiB | q2 capacity sum x 32 KiB |
|---|---|---|---|---|
| 16384 / 4096 | 8192 -> 32768 | 32768 | 3328 MiB | 5120 MiB |
| 32768 / 4096 | 8192 -> 65536 | **65536** | 9472 MiB | 18432 MiB (eval-pool arm, completes) |

At 32768 each q2 chunk at capacity 65536 realizes a new 2048 MiB version (65536 x 32 KiB). In the stage-4 observe pair q2 active memory rose 2048 MiB per chunk (3992, 6040, 8088, ... 18328 MiB over eight chunks) while the scheduler's sampled footprint reached 27755 MiB, and the engine was killed by the 27904 MiB scheduler footprint cap during q2 chunk 8. q1 in the same cell peaked at 15565 MiB footprint (active 11416). This is a **lower bound** for the historical-shaped pair: the q2 request did not finish, its usage is null, and no settled q2 value exists. Tree peak 29368 MiB (scheduler-only 27755; role lifetime maxima summed 29585 MiB are not simultaneous). The same pair with the eval-pool intervention (stage 3, `pair-distinct-eval-pool`) completes at a scheduler-only peak of 10372 MiB, i.e. the stage-4 q2 growth is the observe arm's pinned versions (matching the within-request model below), not q2 work volume.

Supported by the data: **parked/private KV reuse (q2 inherits q1's final capacity) combined with lazy-scatter version pinning explains the second-request growth in this reconstruction.** Not established: that #406's request 2 used the same body, or that nothing else contributes (the cap stopped the observation).

## Preregistered contrasts

| Hypothesis (by mechanism) | Result | Evidence |
|---|---|---|
| Lazy-scatter growth within a request, **planned form** (sum over k=1..j, 160 MiB) | **contradicted** at 16k and 32k (q1; passes by coincidence for some q2) | `history-16k.json`, `bridge-32k.json` aggregates; matches the offline-predicted legacy failure |
| Same, **lag form** (sum over k=0..j-1) | **supported** in every completed pair (16k distinct, 16k identical, 32k identical; both repeats) | residuals <= 10 MiB offline; same here |
| Allocator retention (clear-cache) | per-chunk clear freed 5-4238 MiB of cache with 0.00 MiB active change at all 20 chunk boundaries (both repeats, both requests); the selective criterion (cache drop >= 64 MiB, |active change| <= 16 MiB) holds in 17 of 20, the three misses being small-cache boundaries (5-62 MiB freed); footprint change 0 to -498 MiB; descriptive | decode/release growth not isolated |
| Pool size (bridge cells 1 vs 3) | scheduler-only peak 17555 vs 17622 MiB (+67 MiB for +2048 tokens: nominal 64 MiB) | single observe, matched |
| Output depth (cells 2 vs 3) | 17609 vs 17622 MiB (+13 MiB for +96 tokens) | decode/history effect, not specifically logits |
| Chunk geometry (16k observe pair c2048 vs c4096) | scheduler-only 18971 vs 14396 MiB; q1/q2 capacity sums 4736/9216 vs 3328/5120 MiB | observe only; no chunk-by-intervention claim |
| Prefix replay (identical pair) | q2 executes one chunk (cached 16417 of 16418 / 32801 of 32802 tokens), capacity sum 1024 / 2048 MiB; the pair still pins q1+q2 versions in observe | executed work differs from distinct; not an equal-work comparison |
| Logits / in-flight pinning / non-MLX overhead | `not_identifiable` | no allocation-level instrumentation; needs_logits=false is intent only |

Stage-3 `pair-distinct-eval-pool` has no observe partner until stage 4; the stage-4 pairing is `incomplete_missing_repeat` (capped repeat 1, repeat 2 not_run), so there is **no completed distinct 32k observe-vs-eval-pool contrast**.

## Disclosed condition (Amendment 1)

A pre-sequence `HEALTH_CHECK` peer, removed lazily during q1, was visible in q1 chunks (never q2) in every cell and arm; its parked cache is part of every cell's measured q1 condition. It would be absent on engines that have no such probe; cross-engine comparisons should record whether readiness traffic exists.

## Explicit unknowns

- #406's actual request 2 body and token counts; whether a different body would reach the same capacity.
- The completed q2 settled gap at 32k (capped); allocation-level residency of the 128 MiB small-cache term.
- Whether the 27904 MiB cap is enforced as configured: it stays `configured_not_read_back`, scheduler-role proof only.
- Timing sensitivity (gap 14-25 ms vs 2 ms).

## Cross-links

QB #419, #452, #454 (`eejd/py-quantbench`, cross-linked, not closed); py-sglang #25 (lazy pool scatter retains KV versions), #24 (auto pool/private-cache accounting), #15 (private caches outside the token bound), #26 (wired limit; no footprint effect here). All issues stay open and PR #35 stays draft. Promotion of any calibration point, an engine patch, and 65536 each need a separate plan; a cross-engine tuning round is a separate later plan.
