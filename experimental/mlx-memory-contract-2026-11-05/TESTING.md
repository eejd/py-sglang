# Using this evidence to implement and test the memory contract

## Reproduction harness
EngineScope (eejd/py-enginescope PR #35, branch `validation/sglang-causal-replay`, commit `d6b93d4`) holds the sequence replay executor (`src/enginescope/workloads/sequence.py`), the shim telemetry (`resources/sglang_mlx_telemetry_v2`, per-chunk `mx.active/cache/peak`, capacities, release/remove events) and the raw run trees (not copied here; ~49 MB). `evidence/` here has the scenarios (`*.toml`), analysis (`causal_report.py`), fixtures builder (`prepare_replay.py`), stage runner (`run_stage.sh`), results, and every live/offline JSON. Fixtures are deterministic (GuideLLM synthetic generator, seeds 505645418/505645419); the 32768 repeat-1 body1 equals QB #406 request 1 exactly (`FIXTURES_SUMMARY.json`).

## Baselines the implementation must change (current engine, `0.5.22+local02`)
| Scenario | Observed | Source |
|---|---|---|
| 32768 single request, chunk 4096, pool 36864, output 128 | scheduler-only sampled peak ~17.6 GiB; settled active 13463 MiB | `bridge-32k.md` |
| same, eval-pool intervention (versions evaluated per chunk) | 10.4 GiB (pair), settled active 3992 MiB | `bridge-32k.md` |
| 32768 distinct pair, observe, same settings | q2 killed at 27904 MiB cap; active +2048 MiB per chunk | `historical-pair-32k.md` |
| 16384 distinct pair, observe, chunk 4096 | scheduler-only ~14.4 GiB vs ~8.4 GiB eval-pool | `history-16k.md` |
| chunk 2048 vs 4096 (16k, observe pair) | 18.97 vs 14.40 GiB | `history-16k.md` |
| KV bytes per token | 32768 (16 x 8 x 64 x 2 x 2) | `OFFLINE_ANALYSIS.json` source_facts |

## Proposed acceptance tests for the three work items
1. **Token bound on all paths** - with `--max-total-tokens N`, on dense and hybrid, explicit and auto sizing, radix on and off: sum of all KV bytes the backend holds (pool + every private cache at capacity + retained versions) <= `c * N * bytes_per_token` for a stated `c`; assert via runner accounting and via telemetry (`private_cache_tokens_in_use`, `cache_pool_bytes`, `mx.active`). Regression: the 32768 pair above must complete with scheduler footprint under the budget, not be capped.
2. **Pre-allocation / budget** - memory at idle after startup equals weights + budgeted KV + reserve and does not grow with prompt length; a request that does not fit is queued/rejected (vLLM/llama.cpp semantics), never OOMs; second request reuse must not start from a larger-than-budgeted capacity.
3. **Total budget guard** - a configured ceiling (bytes or fraction of the Metal recommended working set) with a hard refusal path; test by lowering the ceiling below the 32k pair's need and expecting a clean rejection/queue, not a kill. Keep the external cap (ES scheduler cap) as an independent backstop.

Keep the within-request growth model as an invariant test: with versions evaluated, `D_j - D_0` (observe minus eval-pool) must go to ~0; any new design should show active memory independent of chunk count.

## Open items needing deeper research (see issue)
Efficient KV caching designs (paged/block KV, quantized KV, rotating/sliding caches, prefix-cache memory accounting) and Apple Silicon architecture considerations (unified memory, wired limit / recommendedMaxWorkingSetSize, MLX allocator cache, Metal buffer limits, memory bandwidth vs capacity, 512 GB configs).
