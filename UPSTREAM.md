# Upstream and adopted work (`local` branch)

Primary upstream: `sgl-project/sglang` (GitHub fork parent). Secondary upstreams tracked: none.

`main` mirrors `sgl-project/sglang` `main` (fast-forward only, never edited). `local` is `main`
plus the `topic/*` branches below, merged with `--no-ff`. Port `py-sglang-devel` in
`eejd/macports-ports-local` builds `main` pinned by commit (no local patches); a `py-sglang-local`
port would build the tags `v<base>-local<NN>` on `local`, `<base>` being the last upstream release
`main` contains (`v0.5.21`), so the first tag is `v0.5.21-local01` (ADR-0008). No tag exists yet.

## Adopted from other repos

None.

## Topic branches

Topics are opened as draft PRs into `local` and carried here once reviewed and merged. Nothing is
posted to `sgl-project/sglang` before the quantbench + agentbench soak (ADR-0008).

| Topic | Upstream PR | Status |
|---|---|---|
| `topic/mlx-hybrid-radix-auto-no-buffer` | none yet | draft PR eejd/py-sglang#7 (eejd/py-sglang#3); stacked on `topic/mlx-non-overlap-relay-device` (#8): merge #8 first. Starts hybrid models with the radix cache; sustained serving needs `topic/mlx-hybrid-aux-state-budget` (#12, eejd/py-sglang#11) |
| `topic/mlx-non-overlap-relay-device` | none yet | draft PR eejd/py-sglang#8 (eejd/py-sglang#5) |
| `topic/tools-block-as-sent` | none yet | draft PR eejd/py-sglang#9 (eejd/py-sglang#4) |
| `topic/mlx-grammar-requires-sampling` | none yet | draft PR eejd/py-sglang#10 (eejd/py-sglang#6) |
| `topic/mlx-hybrid-aux-state-budget` | none yet | draft PR eejd/py-sglang#12 (eejd/py-sglang#11): snapshots keep their ratio share (402 slots), the rest of the mem_fraction_static budget bounds running requests (24) and live tokens (131738) for Qwen3.5-4B on a 64 GB M5 Pro; stacked on `topic/mlx-hybrid-radix-auto-no-buffer` (#7) |
| `topic/mlx-hybrid-prefix-hit` | none yet | draft PR eejd/py-sglang#14 (eejd/py-sglang#13): the MLX worker performs the scheduler's deferred copy-on-write of a radix-matched auxiliary state, so a prefix hit restores its state and runs only its suffix; stacked on `topic/mlx-hybrid-aux-state-budget` (#12). Open limit: eejd/py-sglang#15 |
