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
