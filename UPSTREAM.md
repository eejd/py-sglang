# Upstream and adopted work (`local` branch)

Primary upstream: `sgl-project/sglang` (GitHub fork parent). Secondary upstreams tracked: none.

`main` mirrors `sgl-project/sglang` `main` (fast-forward only, never edited). `local` is `main`
plus the `topic/*` branches below, merged with `--no-ff`. Port `py-sglang-devel` in
`eejd/macports-ports-local` builds `main` pinned by commit (no local patches); port
`py-sglang-local` builds the tags `v<base>-local<NN>` on `local`, `<base>` being the last upstream
release `local` contains (ADR-0008). That is `v0.5.22` (published 2026-10-19): upstream cuts a
release from a release branch, so no release tag is an ancestor of `main`; `local` contains
v0.5.22 by content: the branch point (`684fea8af3`, `main` of 2026-10-13) is an ancestor of
`main`, and the two cherry-picks on the release branch are on `main` (`git cherry`: `7ca4cbfcef`,
`ff8d964cf5`). `local` is 485 commits past that branch point (`f0b6590722`, `main` of
2026-10-20). v0.5.22 already carries the MLX start-up fix (sgl-project/sglang#41314) that v0.5.21
lacked.

## Tags

| Tag | Commit | Contains |
|---|---|---|
| `v0.5.22-local01` | `7b8608d8a3` (`local` after the merge of eejd/py-sglang#17, 2026-10-21) | upstream `main` `f0b6590722` (v0.5.22 content, see above) + all eight topics below (eejd/py-sglang#7, #8, #9, #10, #12, #14, #17, #18). **Does not start any MLX model** (eejd/py-sglang#20: upstream sgl-project/sglang#44913 made `BaseRunner.model_context()` read `model.shared_experts_config`, which the stub's dummy model lacked); fixed in `v0.5.22-local02` |
| `v0.5.22-local02` | `d5672f7971` (`local` after the merge of eejd/py-sglang#21, 2026-10-21) | `v0.5.22-local01` + `topic/mlx-stub-model-context` (eejd/py-sglang#21, fixes #20): MLX models start again. Differs from local01 by the stub fix, its test and `UPSTREAM.md` only (`git diff v0.5.22-local01 v0.5.22-local02 --stat`). The `UPSTREAM.md` inside this tag predates this row and the merged status of #21. The port `py-sglang-local` takes `0.5.22-local02`; do not use local01 |
| `v0.5.23-local01` | `fd119bee30` (`local` after the merge of eejd/py-sglang#28, 2026-11-15) | upstream `v0.5.23` merged into `local` (see "Merge of upstream v0.5.23") + the topics below up to eejd/py-sglang#23 |
| `v0.5.23-local02` | `edbb80e06f` (`local` after the merge of eejd/py-sglang#30, 2026-11-15) | `v0.5.23-local01` + `topic/gloo-loopback` (eejd/py-sglang#30: single-process MLX defaults gloo to loopback) |
| `v0.5.23-local03` | `local` after the merge of eejd/py-sglang#37 (the `UPSTREAM.md` update that adds this row) | `v0.5.23-local02` + the six tranche topics below (eejd/py-sglang#31, #32, #33, #34, #35, #36): dense KV-pool scatter evaluated with its chunk (#25), dense private-cache budget (#24), `SGLANG_MLX_WIRED_LIMIT_GB` (#26), grammars enforced without `--mlx-enable-sampling` (#6), LFM2 loads, speculative decoding refused on MLX (#1). The `UPSTREAM.md` inside this tag is this one |


## Merge of upstream v0.5.23 (2026-11-14)

`local` now contains upstream `v0.5.23` (published 2026-11-02) by a merge commit (branch `merge/upstream-v0.5.23`, history preserved, no force-push). Three conflicts, all resolved in favour of keeping the topic behaviour on top of upstream's new structure:
- `model_runner_stub.py`: same code both sides (`shared_experts_config`); upstream wording kept (upstream #45419).
- `serving_chat.py`: `Tool.to_template_dict()` (`topic/tools-block-as-sent`) kept together with upstream's muse `_template_tools` override.
- `overlap_utils.py`: upstream's relay-bonus branch kept; its `else` still copies the bonus tokens with a dtype-only cast, so the device move of `topic/mlx-non-overlap-relay-device` is re-applied there (upstream PRs #43099 and #39222 for the same defect are open).
Checked: the unit tests under `test/registered/unit/hardware_backend/mlx`, `entrypoints/openai/test_protocol.py` and the topic test files passed on this tree (see the PR). No tag is cut here; the next tag would be `v0.5.23-local01`.

## Adopted from other repos

None.

## Topic branches

Topics are opened as draft PRs into `local` and carried here once reviewed and merged. Nothing is
posted to `sgl-project/sglang` before the quantbench + agentbench soak (ADR-0008).

| Topic | Upstream PR | Status |
|---|---|---|
| `topic/mlx-hybrid-radix-auto-no-buffer` | none yet | merged into `local` as eejd/py-sglang#7 (`5c67965e10`; eejd/py-sglang#3); stacked on `topic/mlx-non-overlap-relay-device` (#8). Starts hybrid models with the radix cache; sustained serving needs `topic/mlx-hybrid-aux-state-budget` (#12, eejd/py-sglang#11) |
| `topic/mlx-non-overlap-relay-device` | none yet | merged into `local` as eejd/py-sglang#8 (`dc59641d8a`; eejd/py-sglang#5) |
| `topic/tools-block-as-sent` | none yet | merged into `local` as eejd/py-sglang#9 (`bd3fedaac1`; eejd/py-sglang#4) |
| `topic/mlx-grammar-requires-sampling` | none yet | merged into `local` as eejd/py-sglang#10 (`8a6c06cfb8`; eejd/py-sglang#6). **Superseded** by `topic/mlx-grammar-greedy-mask` (eejd/py-sglang#32): grammars are enforced with or without the flag, the refusal is gone |
| `topic/mlx-hybrid-aux-state-budget` | none yet | merged into `local` as eejd/py-sglang#12 (`def3066a4a`; eejd/py-sglang#11): snapshots keep their ratio share (402 slots), the rest of the mem_fraction_static budget bounds running requests (24) and live tokens (131738) for Qwen3.5-4B on a 64 GB M5 Pro; stacked on `topic/mlx-hybrid-radix-auto-no-buffer` (#7); also replaces the self-referencing array collectors of `auxiliary_state.py` and `model_runner.py` (reference cycles kept snapshots and request caches allocated, eejd/py-sglang#15) |
| `topic/mlx-hybrid-prefix-hit` | none yet | merged into `local` as eejd/py-sglang#14 (`404f02a785`; eejd/py-sglang#13): the MLX worker performs the scheduler's deferred copy-on-write of a radix-matched auxiliary state, so a prefix hit restores its state and runs only its suffix; stacked on `topic/mlx-hybrid-aux-state-budget` (#12). Concurrent hits are bounded by `topic/mlx-private-cache-admission` (#18) |
| `topic/mlx-private-cache-admission` | none yet | merged into `local` as eejd/py-sglang#18 (`39fee03b27`; eejd/py-sglang#15): the running requests' private attention caches are bounded at admission (2 x the live-token bound; a finished request's state is freed at every launch); stacked on `topic/mlx-hybrid-prefix-hit` (#14) |
| `topic/mlx-logprob-requires-sampling` | none yet | merged into `local` as eejd/py-sglang#17 (`7b8608d8a3`; eejd/py-sglang#16): `logprobs` without `--mlx-enable-sampling` is refused with HTTP 400 instead of killing the scheduler |
| `topic/mlx-stub-model-context` | none yet | merged into `local` as eejd/py-sglang#21 (`d5672f7971`; eejd/py-sglang#20): the MLX stub's dummy model carries `shared_experts_config = SharedExpertsConfig()` (the layout `BaseRunner.model_context()` reads on every launch since upstream sgl-project/sglang#44913), so the engine starts again on `local`; regression test warms an `EagerRunner` up on the stub model. Based on `local`, not on a topic |. **Upstream has the same fix** since sgl-project/sglang#45419 (merged 2026-10-21, contained in v0.5.23); on the v0.5.23 merge the stub block takes upstream wording, so this topic is carried only until a tag drops it
| `topic/mlx-stub-model-context-test` | none yet | merged into `local` as eejd/py-sglang#23 (`59af245904`; review of #21): the stub model's shared-experts layout test compares the whole default `SharedExpertsConfig()` (the `use_waterfill=True` mutant survived the two-field test); test only, no code change. **Not in `v0.5.22-local02`** (that tag predates it); it ships with the next tag |
| `topic/mlx-dense-pool-eval` | none yet | merged into `local` as eejd/py-sglang#35 (`0c98dbe099`; eejd/py-sglang#25): a dense model's KV-pool scatter is evaluated in the eval of the chunk that wrote it (`take_pool_eval_arrays`) instead of staying lazy and pinning a version of the request's contiguous cache; scheduler peak footprint 10.3 vs 12.9 GB on Llama-3.2-1B, two 16k prompts (ratio 0.80) |
| `topic/mlx-dense-private-cache-budget` | none yet | merged into `local` as eejd/py-sglang#36 (`d64fe353c9`; eejd/py-sglang#24, #27 item 1): every model with the radix cache on gets `max_live_requests` and the private-cache token bound, dense ones included (snapshots stay hybrid-only); Llama-3.2-1B KV pool 2.85 GiB instead of 14.34 GiB, 24 running requests |
| `topic/mlx-wired-limit-env` | none yet | merged into `local` as eejd/py-sglang#31 (`5111c317b8`; eejd/py-sglang#26): `SGLANG_MLX_WIRED_LIMIT_GB` (unset: wire the recommended working set as upstream; 0: no wired limit; N: N GiB capped at the recommended size) |
| `topic/mlx-grammar-greedy-mask` | none yet | merged into `local` as eejd/py-sglang#32 (`92e4efccb4`; eejd/py-sglang#6): grammar vocab masks apply on the greedy path, grammar batches launch unchained without the flag, `GrammarManager` no longer refuses or skips grammars on MLX |
| `topic/mlx-lfm2-attention` | none yet | merged into `local` as eejd/py-sglang#33 (`69f9878815`; eejd/py-sglang#1): LFM2 loads (`out_proj`, `q_layernorm`/`k_layernorm`, `embedding_norm`, tied head); greedy output equals mlx-lm up to a bf16 logit tie |
| `topic/mlx-refuse-speculative` | none yet | merged into `local` as eejd/py-sglang#34 (`ae278e1eda`; eejd/py-sglang#1): `--speculative-algorithm` on MLX is refused at argument resolution with an explicit message |
