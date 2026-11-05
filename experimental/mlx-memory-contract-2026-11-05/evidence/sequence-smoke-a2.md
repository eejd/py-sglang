# Live analysis: sequence-smoke-a2

analysis script sha256: `3724bcd6fef385768e81686b4bc9fad4bf8c39a1ffcf9f11dde5bdbc39e8d77e`
stage gate: **pass**

| cell | status | engine | q1 in/out/cache | q2 in/out/cache | gap s | chunks q1/q2 | tree peak MiB | scheduler-only MiB |
|---|---|---|---|---|---|---|---|---|
| pair-distinct-clear-cache-r1 | complete | completed | 2082/32/1 | 2082/32/32 | 0.014119166997261345 | 3/3 | 5749.45 | 4166.32 |
| pair-distinct-eval-pool-r1 | complete | completed | 2082/32/1 | 2082/32/32 | 0.01804370799800381 | 3/3 | 5826.13 | 4241.71 |
| pair-distinct-observe-r1 | complete | completed | 2082/32/1 | 2082/32/32 | 0.015507000032812357 | 3/3 | 6102.16 | 4531.66 |
| pair-identical-observe-r1 | complete | completed | 2082/32/1 | 2082/32/2081 | 0.015160083014052361 | 3/1 | 6210.04 | 4626.97 |

## Disclosed pre-sequence health peers

- pair-distinct-clear-cache-r1: [{"chunk_visibility": [{"chunk": 0, "mono": 319873.569340708, "ordinal": 1, "rid": "es-causal-pair-distinct-clear-cache-r1-q1", "visible": true}, {"chunk": 1, "mono": 319873.6566755, "ordinal": 1, "rid": "es-causal-pair-distinct-clear-cache-r1-q1", "visible": true}, {"chunk": 2, "mono": 319873.677109375, "ordinal": 1, "rid": "es-causal-pair-distinct-clear-cache-r1-q1", "visible": true}, {"chunk": 0, "mono": 319873.910202916, "ordinal": 2, "rid": "es-causal-pair-distinct-clear-cache-r1-q2", "visible": false}, {"chunk": 1, "mono": 319873.999523833, "ordinal": 2, "rid": "es-causal-pair-distinct-clear-cache-r1-q2", "visible": false}, {"chunk": 2, "mono": 319874.009132083, "ordinal": 2, "rid": "es-causal-pair-distinct-clear-cache-r1-q2", "visible": false}], "first_mono": 319872.41271475, "removal_events": [{"ev": "remove_request.enter", "mono": 319873.678469041, "seq": 228, "ts": 1793876024.7675362}, {"ev": "remove_request.exit", "mono": 319873.678489666, "seq": 229, "ts": 1793876024.7675571}, {"ev": "request_state_removed", "mono": 319873.678529083, "seq": 230, "ts": 1793876024.767596}], "req_id": "HEALTH_CHECK_c6ebbca9e8db4feb84615154ac502064"}]
- pair-distinct-eval-pool-r1: [{"chunk_visibility": [{"chunk": 0, "mono": 319812.923154875, "ordinal": 1, "rid": "es-causal-pair-distinct-eval-pool-r1-q1", "visible": true}, {"chunk": 1, "mono": 319813.00754025, "ordinal": 1, "rid": "es-causal-pair-distinct-eval-pool-r1-q1", "visible": true}, {"chunk": 2, "mono": 319813.026342833, "ordinal": 1, "rid": "es-causal-pair-distinct-eval-pool-r1-q1", "visible": true}, {"chunk": 0, "mono": 319813.260259916, "ordinal": 2, "rid": "es-causal-pair-distinct-eval-pool-r1-q2", "visible": false}, {"chunk": 1, "mono": 319813.344356416, "ordinal": 2, "rid": "es-causal-pair-distinct-eval-pool-r1-q2", "visible": false}, {"chunk": 2, "mono": 319813.351254666, "ordinal": 2, "rid": "es-causal-pair-distinct-eval-pool-r1-q2", "visible": false}], "first_mono": 319811.763214958, "removal_events": [{"ev": "remove_request.enter", "mono": 319813.027322416, "seq": 225, "ts": 1793875964.116135}, {"ev": "remove_request.exit", "mono": 319813.02734175, "seq": 226, "ts": 1793875964.116155}, {"ev": "request_state_removed", "mono": 319813.027380875, "seq": 227, "ts": 1793875964.116194}], "req_id": "HEALTH_CHECK_843edfbbe5c64000ba52bfd93d4851fb"}]
- pair-distinct-observe-r1: [{"chunk_visibility": [{"chunk": 0, "mono": 319994.912901208, "ordinal": 1, "rid": "es-causal-pair-distinct-observe-r1-q1", "visible": true}, {"chunk": 1, "mono": 319994.996939375, "ordinal": 1, "rid": "es-causal-pair-distinct-observe-r1-q1", "visible": true}, {"chunk": 2, "mono": 319995.01504125, "ordinal": 1, "rid": "es-causal-pair-distinct-observe-r1-q1", "visible": true}, {"chunk": 0, "mono": 319995.247290916, "ordinal": 2, "rid": "es-causal-pair-distinct-observe-r1-q2", "visible": false}, {"chunk": 1, "mono": 319995.331182875, "ordinal": 2, "rid": "es-causal-pair-distinct-observe-r1-q2", "visible": false}, {"chunk": 2, "mono": 319995.337588708, "ordinal": 2, "rid": "es-causal-pair-distinct-observe-r1-q2", "visible": false}], "first_mono": 319993.754317416, "removal_events": [{"ev": "remove_request.enter", "mono": 319995.01563975, "seq": 221, "ts": 1793876146.105215}, {"ev": "remove_request.exit", "mono": 319995.015660333, "seq": 222, "ts": 1793876146.105236}, {"ev": "request_state_removed", "mono": 319995.015699958, "seq": 223, "ts": 1793876146.105275}], "req_id": "HEALTH_CHECK_ffbbaeb0e84545d9b9d366b4179790bf"}]
- pair-identical-observe-r1: [{"chunk_visibility": [{"chunk": 0, "mono": 319934.290195125, "ordinal": 1, "rid": "es-causal-pair-identical-observe-r1-q1", "visible": true}, {"chunk": 1, "mono": 319934.374143875, "ordinal": 1, "rid": "es-causal-pair-identical-observe-r1-q1", "visible": true}, {"chunk": 2, "mono": 319934.392316625, "ordinal": 1, "rid": "es-causal-pair-identical-observe-r1-q1", "visible": true}, {"chunk": 0, "mono": 319934.551860666, "ordinal": 2, "rid": "es-causal-pair-identical-observe-r1-q2", "visible": false}], "first_mono": 319933.129437625, "removal_events": [{"ev": "remove_request.enter", "mono": 319934.392899541, "seq": 222, "ts": 1793876085.4822211}, {"ev": "remove_request.exit", "mono": 319934.39292, "seq": 223, "ts": 1793876085.482242}, {"ev": "request_state_removed", "mono": 319934.392960208, "seq": 224, "ts": 1793876085.482282}], "req_id": "HEALTH_CHECK_106802b18c774c93bcb06345f1b20885"}]

## Contrasts

- clear_cache_per_chunk [2048, 4096, 1024, 32, 2, 'distinct']: repeats [1]/1 -> computed_descriptive
- eval_pool_per_chunk [2048, 4096, 1024, 32, 2, 'distinct']: repeats [1]/1 -> {'planned_form': 'supported', 'lag_form': 'supported'}

## Hard fidelity failures

none

## Scientific inconclusive

none

no between-request sample implies no manufactured q1 settled plateau; a capped request gives a lower bound only; 27904MiB scheduler cap is configured_not_read_back
