# Observed MLX KV memory growth vs documented/designed behavior

Date: 2026-11-05. Evidence base: ES causal replay (`../evidence/`, ES PR eejd/py-enginescope#35) on `mlx-community/Llama-3.2-1B-Instruct-4bit`, SGLang `0.5.22+local02`, MLX `0.32.4+local03`, Mac17,16 (64 GiB), radix cache on, explicit `--max-total-tokens`.

## Observed (this evidence)

- KV bytes/token = 32 KiB (16 layers x 8 kv heads x 64 x 2 x fp16).
- Each prefill chunk's lazy pool scatter pins a full version of the request's contiguous cache: within-request growth `D_j - D_0 = sum(cap_k x 32 KiB, k = 0..j-1)` within 160 MiB (largest residual 9.95 MiB; the form `k = 1..j` fails by up to ~1.9 GiB). A one-chunk lag is a hypothesis for the offset.
- Contiguous caches double (`cap = max(4096, next_pow2(pos))`) and are reused through `reset()` keeping capacity, so request 2 starts at request 1's final capacity: 65536 at a 32802-token prompt, i.e. 2048 MiB per prefill chunk.
- 32k prompt, chunk 4096, pool 36864 tokens (1152 MiB): request 1 reaches 15.6 GiB scheduler footprint (~10.7 GiB active above weights = ~2.6x the documented 4 x tokens x 32 KiB model of ~4.1 GiB); in the matched two-request observe pair request 2 reached 18328 MiB active / 27755 MiB footprint (~4.3x and rising) and the engine was killed at the 27904 MiB scheduler cap during request 2 chunk 8 of 9. The same pair with the eval-pool intervention completes at 10.4 GiB scheduler-only.
- `--max-total-tokens 36864` did not bound any of it. The retained versions are released at the next pool read (request 2 chunk 0 active returns to the eval-pool baseline 3992 MiB), so memory is flat across short requests but not within one long request.

## What the documentation promises

- `--max-total-tokens`: "maximum number of tokens in the memory pool" (`docs/docs/advanced_features/server_arguments.mdx:458-462`). `--mem-fraction-static`: fraction for "model weights and KV cache memory pool" (`:440-446`).
- Tuning guide: total memory = weights + KV pool + graph buffers + activations; insufficient headroom can OOM (`hyperparameter_tuning.mdx:33-65`).
- `docs/docs/hardware-platforms/apple_metal.mdx`: install, launch, quantization, benchmarking; **no memory contract**; only `SGLANG_MLX_CLEAR_CACHE_STEPS`.
- Core admission (`PrefillBudget`, `schedule_policy.py`) counts allocator tokens only. No written requirement was found that a backend keep all allocations within the pool, and none permitting it to exceed the pool (see `core-contract.md`).

## What the MLX code documents (installed `hardware_backend/mlx/`)

- `kv_cache/attention_kv_cache.py`: `ContiguousAttentionKVCache` starts at `max_seq_len` and doubles; `reset()` "keeping allocated buffers".
- `model_runner.py:_acquire_cache` reuses pooled caches for dense models.
- `model_runner.py:_sync_new_kv_to_pool` (~1015-1056): scatters are lazy and chain on previous buffer versions; evaluated only for auxiliary-state models; dense models "are spared the eval, which costs prefill latency"; "flat memory over 500 distinct requests" (short requests).
- Sizing docstring (~723-770): per live token, pool once plus up to 3x in a private cache ("capacity below twice its tokens, 1.5x while growing") => 4x; "NOT covered here: many concurrent requests that reuse a cached prefix (py-sglang#15)". `private_cache_budget_tokens` is derived on the hybrid-radix path; non-hybrid explicit pool sizes return early (`explicit_size is not None and not hybrid_radix`).
- `kv_cache/private_cache_admission.py`: private-cache admission bound; a lone request is always admitted.

## Evaluation

| Behavior | Documented / designed? | Verdict |
|---|---|---|
| Doubling caches reused with retained capacity | Designed (comments); no stated goal for the policy | design choice without rationale; conflicts with predictable budgets |
| Lazy pool scatter, no eval on dense | Designed, rationale = prefill latency, validated on short requests | contradicted at long context: pins O(capacity x chunks); the same comment's own hybrid rationale ("keeps every request's cache alive") applies within a request |
| Memory flat across requests | Claimed | holds across requests, fails within a long request |
| `--max-total-tokens` bounds memory | Never promised as process memory; reads like a memory knob | documentation/contract gap; no bound exists on any path with an explicit pool |
| Private caches outside the token pool | Acknowledged (#15), bounded only on the hybrid budget path | design gap; lone request always admitted |
| No total-memory guard | Not specified either way | missing guard; upstream roadmap #19137 / issue #21443 list UMA management as unfinished |

There is no spec that defines unbounded growth. The documents are silent about a whole-process bound; they define only a logical token pool. Physical memory is always bounded, so the missing piece is an explicit budget that the engine enforces before the hardware does (the engine here was killed by an external cap, not by any SGLang bound).

## Comparison to other engines (see `other-engines.md`)

mlx_lm: contiguous KV grows on demand in 256-token steps, evaluates cache state at prefill boundaries, optional rotating cache; retained prompt-cache cap does not bound active KV. llama.cpp: context-sized KV preallocated; `--fit` adjusts unset params against device memory. vLLM: startup-budgeted block pool, preemption/recompute, `max_model_len` check at startup. vllm-metal: documented memory guard (startup profiling, fixed KV pool, capped MLX buffer cache, waits for pages). No evidence found that those engines retain a full cache version per prefill chunk. Closest fit for one-to-few chats with a large model on a large unified-memory Mac: a startup-budgeted pool with admission (vllm-metal), or llama.cpp-style explicit context-sized reservation.

## Limits

Upstream and other-engine claims come from research-agent readings of the cited sources, not independently re-verified here. The py-sglang checkout differs from the installed build (the installed build has the private-cache admission code). One model, one host, one capped repeat for the 32k pair; request-2 body is a same-seed reconstruction of unknown fidelity vs #406; logits/in-flight pinning/non-MLX overhead not isolated.
