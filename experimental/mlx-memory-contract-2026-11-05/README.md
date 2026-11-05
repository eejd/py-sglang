# MLX backend memory contract: research and evidence (2026-11-05)

Index for eejd/py-sglang issue (see repo issues, "MLX backend memory contract"). Contents:
- `research/evaluation.md` - observed behavior vs documented/designed behavior, verdict table.
- `research/core-contract.md` - what SGLang core/front-end docs and scheduler promise (and do not).
- `research/upstream-evidence.md` - sgl-project/sglang issues/PRs on MLX/UMA memory (#19137, #21443, #21509, #29439, #41209, #29949, #39675, #41264, #28160, #20169).
- `research/other-engines.md` - mlx_lm, llama.cpp, vLLM, vllm-metal, Ollama, LM Studio.
- `evidence/` - ES causal replay results: `RESULTS.md`, `PREREG.md`, offline + live analyses (JSON/MD), scenarios, analysis and fixture scripts.
- `TESTING.md` - baselines and proposed acceptance tests.

Provenance: ES PR eejd/py-enginescope#35 (commit d6b93d4); upstream/other-engine findings are research-agent readings of cited sources (not independently re-verified); local checks are marked in `evaluation.md`.
