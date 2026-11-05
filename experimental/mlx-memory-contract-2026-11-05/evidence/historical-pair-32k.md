# Live analysis: historical-pair-32k

analysis script sha256: `3724bcd6fef385768e81686b4bc9fad4bf8c39a1ffcf9f11dde5bdbc39e8d77e`
stage gate: **final_stage_outcome**

| cell | status | engine | q1 in/out/cache | q2 in/out/cache | gap s | chunks q1/q2 | tree peak MiB | scheduler-only MiB |
|---|---|---|---|---|---|---|---|---|
| pair-distinct-observe-c4096-r1 | lower_bound | capped | 32802/128/1 | None/None/None | None | 9/8 | 29367.93 | 27755.44 |

## Disclosed pre-sequence health peers

- pair-distinct-observe-c4096-r1: [{"chunk_visibility": [{"chunk": 0, "mono": 321962.401626083, "ordinal": 1, "rid": "es-causal-pair-distinct-observe-c4096-r1-q1", "visible": true}, {"chunk": 1, "mono": 321962.804049958, "ordinal": 1, "rid": "es-causal-pair-distinct-observe-c4096-r1-q1", "visible": true}, {"chunk": 2, "mono": 321963.277860375, "ordinal": 1, "rid": "es-causal-pair-distinct-observe-c4096-r1-q1", "visible": true}, {"chunk": 3, "mono": 321963.82639175, "ordinal": 1, "rid": "es-causal-pair-distinct-observe-c4096-r1-q1", "visible": true}, {"chunk": 4, "mono": 321964.447331041, "ordinal": 1, "rid": "es-causal-pair-distinct-observe-c4096-r1-q1", "visible": true}, {"chunk": 5, "mono": 321965.138904583, "ordinal": 1, "rid": "es-causal-pair-distinct-observe-c4096-r1-q1", "visible": true}, {"chunk": 6, "mono": 321965.901506, "ordinal": 1, "rid": "es-causal-pair-distinct-observe-c4096-r1-q1", "visible": true}, {"chunk": 7, "mono": 321966.73929125, "ordinal": 1, "rid": "es-causal-pair-distinct-observe-c4096-r1-q1", "visible": true}, {"chunk": 8, "mono": 321966.795708708, "ordinal": 1, "rid": "es-causal-pair-distinct-observe-c4096-r1-q1", "visible": true}, {"chunk": 0, "mono": 321968.12840825, "ordinal": 2, "rid": "es-causal-pair-distinct-observe-c4096-r1-q2", "visible": false}, {"chunk": 1, "mono": 321968.541941, "ordinal": 2, "rid": "es-causal-pair-distinct-observe-c4096-r1-q2", "visible": false}, {"chunk": 2, "mono": 321969.024584208, "ordinal": 2, "rid": "es-causal-pair-distinct-observe-c4096-r1-q2", "visible": false}, {"chunk": 3, "mono": 321969.577529041, "ordinal": 2, "rid": "es-causal-pair-distinct-observe-c4096-r1-q2", "visible": false}, {"chunk": 4, "mono": 321970.203597, "ordinal": 2, "rid": "es-causal-pair-distinct-observe-c4096-r1-q2", "visible": false}, {"chunk": 5, "mono": 321970.904459916, "ordinal": 2, "rid": "es-causal-pair-distinct-observe-c4096-r1-q2", "visible": false}, {"chunk": 6, "mono": 321971.68518275, "ordinal": 2, "rid": "es-causal-pair-distinct-observe-c4096-r1-q2", "visible": false}, {"chunk": 7, "mono": 321972.551416, "ordinal": 2, "rid": "es-causal-pair-distinct-observe-c4096-r1-q2", "visible": false}], "first_mono": 321960.873320833, "removal_events": [{"ev": "remove_request.enter", "mono": 321966.796495166, "seq": 421, "ts": 1793878117.891757}, {"ev": "remove_request.exit", "mono": 321966.79651975, "seq": 422, "ts": 1793878117.891781}, {"ev": "request_state_removed", "mono": 321966.796561666, "seq": 423, "ts": 1793878117.891823}], "req_id": "HEALTH_CHECK_6b02f77b3cc440628df65d828721a60a"}]

## Contrasts

- eval_pool_per_chunk [32768, 36864, 4096, 128, 2, 'distinct']: repeats [1]/2 -> incomplete_missing_repeat

## Hard fidelity failures

- pair-distinct-observe-c4096-r1: ['q2 send ordering or inter-request gap invalid', "engine outcome 'capped'", "request q2 status 'in_progress': None"]

## Scientific inconclusive

none

no between-request sample implies no manufactured q1 settled plateau; a capped request gives a lower bound only; 27904MiB scheduler cap is configured_not_read_back
