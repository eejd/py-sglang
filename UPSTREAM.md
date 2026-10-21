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
| `v0.5.22-local01` | `7b8608d8a3` (`local` after the merge of eejd/py-sglang#17, 2026-10-21) | upstream `main` `f0b6590722` (v0.5.22 content, see above) + all eight topics below (eejd/py-sglang#7, #8, #9, #10, #12, #14, #17, #18) |

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
| `topic/mlx-grammar-requires-sampling` | none yet | merged into `local` as eejd/py-sglang#10 (`8a6c06cfb8`; eejd/py-sglang#6) |
| `topic/mlx-hybrid-aux-state-budget` | none yet | merged into `local` as eejd/py-sglang#12 (`def3066a4a`; eejd/py-sglang#11): snapshots keep their ratio share (402 slots), the rest of the mem_fraction_static budget bounds running requests (24) and live tokens (131738) for Qwen3.5-4B on a 64 GB M5 Pro; stacked on `topic/mlx-hybrid-radix-auto-no-buffer` (#7); also replaces the self-referencing array collectors of `auxiliary_state.py` and `model_runner.py` (reference cycles kept snapshots and request caches allocated, eejd/py-sglang#15) |
| `topic/mlx-hybrid-prefix-hit` | none yet | merged into `local` as eejd/py-sglang#14 (`404f02a785`; eejd/py-sglang#13): the MLX worker performs the scheduler's deferred copy-on-write of a radix-matched auxiliary state, so a prefix hit restores its state and runs only its suffix; stacked on `topic/mlx-hybrid-aux-state-budget` (#12). Concurrent hits are bounded by `topic/mlx-private-cache-admission` (#18) |
| `topic/mlx-private-cache-admission` | none yet | merged into `local` as eejd/py-sglang#18 (`39fee03b27`; eejd/py-sglang#15): the running requests' private attention caches are bounded at admission (2 x the live-token bound; a finished request's state is freed at every launch); stacked on `topic/mlx-hybrid-prefix-hit` (#14) |
| `topic/mlx-logprob-requires-sampling` | none yet | merged into `local` as eejd/py-sglang#17 (`7b8608d8a3`; eejd/py-sglang#16): `logprobs` without `--mlx-enable-sampling` is refused with HTTP 400 instead of killing the scheduler |
