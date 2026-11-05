# Live analysis: sequence-smoke

analysis script sha256: `f7381986e4034a873dcdb0153ad29a18c638931fdf23b1d2e36e9022d891b45d`
stage gate: **stop**

| cell | status | engine | q1 in/out/cache | q2 in/out/cache | gap s | chunks q1/q2 | tree peak MiB | scheduler-only MiB |
|---|---|---|---|---|---|---|---|---|
| pair-distinct-eval-pool-r1 | incomplete | failed | 2082/32/1 | 2082/32/32 | 0.016190916998311877 | 3/3 | 5820.88 | 4250.93 |

## Contrasts

- eval_pool_per_chunk [2048, 4096, 1024, 32, 2, 'distinct']: repeats [1]/1 -> incomplete

## Hard fidelity failures

- pair-distinct-eval-pool-r1: ["engine outcome 'failed'", 'intervention: request 1: active or unknown live peer HEALTH_CHECK_c3fd281b08d448c1a0c610a213317efa', 'intervention: request 1: active or unknown live peer HEALTH_CHECK_c3fd281b08d448c1a0c610a213317efa', 'intervention: request 1: active or unknown live peer HEALTH_CHECK_c3fd281b08d448c1a0c610a213317efa', "live peers observed: ['HEALTH_CHECK_c3fd281b08d448c1a0c610a213317efa']"]

## Scientific inconclusive

none

no between-request sample implies no manufactured q1 settled plateau; a capped request gives a lower bound only; 27904MiB scheduler cap is configured_not_read_back
