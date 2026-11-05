# Offline causal analysis

analysis script sha256: `3724bcd6fef385768e81686b4bc9fad4bf8c39a1ffcf9f11dde5bdbc39e8d77e`

## QB #406 two-request timeline

| quantity | value |
|---|---|
| F0_last_sample_before_request1_gib | 6.308 |
| F0_definition | last server_rss sample before request1 start (after-load/after-warmup plateau); the engine log's own `Memory baseline taken` reads 0.00 GB and is a different domain |
| pool_bytes_from_log_mib | 1152.0 |
| max_sampled_tree_footprint_gib | 33.362 |
| max_sampled_tree_footprint_offset_from_request1_start_s | 11.1 |
| max_sampled_peak_bytes_gib | 33.412 |
| max_peak_note | peak_bytes is the kernel lifetime maximum reported with each sample; it need not coincide with a sampled footprint; the issue's >=33.412GiB is this lifetime-maximum quantity |
| samples_total | 64 |
| samples_between_request1_end_and_request2_start | 0 |
| request1_end_to_request2_start_s | 0.001999 |

request1: {"input_tokens": 32802, "client_cached_tokens": 1, "output_tokens": 128, "start": 1793110840.189672, "end": 1793110845.995268}

request2: {"status": "errored", "input_tokens": 32768, "client_cached_tokens": null, "output_tokens": null, "start": 1793110845.997267, "end": 1793110851.4385102}

- request2 prompt count 32768 is the client's expected count, not confirmed server usage; its cached_tokens is null
- prefix32 and an exact request2 new-token count are inference, not ground truth
- the issue's '32960' wording is a different quantity from raw observed request1 input 32802
- no footprint sample lies between request1 completion and request2 growth
- QB footprint is a whole-engine sum in the QB probe's domain; ES scheduler-only and tree sums use different baselines

## ES evidence per-cell summary

| run | cell | measured req | chunks | capacity sum x32KiB MiB | tree peak MiB | scheduler-only peak MiB | sum of role lifetime maxima MiB (not simultaneous) | parser gaps |
|---|---|---|---|---|---|---|---|---|
| containment-breach | chunk4096-p512-r1 | - | - | - | 2304.38 | 759.06 | 2315.57 | 0 |
| containment-smoke-r3 | chunk4096-p512-r1 | c84ae80b | 1 | 128.0 | 6222.73 | 4651.25 | 6223.01 | 0 |
| mechanism-small | clear-cache-r1 | - | - | - | 1998.13 | 552.77 | 2079.54 | 0 |
| mechanism-small | eval-pool-r1 | 00faae4b | 2 | 256.0 | 6208.82 | 4626.07 | 6209.12 | 0 |
| mechanism-small | observe-before-r1 | 68bfc2c9 | 2 | 256.0 | 6314.59 | 4743.82 | 6314.87 | 0 |
| mechanism-small-r2 | clear-cache-r1 | 99a2d667 | 2 | 256.0 | 5533.02 | 3961.94 | 6000.79 | 0 |
| mechanism-small-r2 | eval-pool-r1 | a46af262 | 2 | 256.0 | 6196.98 | 4614.49 | 6197.27 | 0 |
| mechanism-small-r2 | eval-pool-r2 | - | - | - | None | None | 0.0 | 0 |
| mechanism-small-r2 | no-radix-r1 | 43d30d5a | 3 | 384.0 | 5874.04 | 4290.08 | 5874.29 | 0 |
| mechanism-small-r2 | observe-after-r1 | cb7de628 | 2 | 256.0 | 6334.05 | 4750.07 | 6334.34 | 1 |
| mechanism-small-r2 | observe-before-r1 | 01716125 | 2 | 256.0 | 6328.27 | 4744.46 | 6328.57 | 0 |
| mechanism-small-r2 | observe-before-r2 | b9bd0be0 | 2 | 256.0 | 6318.52 | 4748.08 | 6318.82 | 0 |
| mechanism-small-r3 | clear-cache-r1 | 2dc9c88e | 2 | 256.0 | 5523.37 | 3953.58 | 6000.99 | 0 |
| mechanism-small-r3 | clear-cache-r2 | a848f117 | 2 | 256.0 | 6005.49 | 4435.03 | 6005.8 | 0 |
| mechanism-small-r3 | eval-pool-r1 | 5eb133eb | 2 | 256.0 | 6214.91 | 4630.89 | 6215.2 | 0 |
| mechanism-small-r3 | eval-pool-r2 | 00d30318 | 2 | 256.0 | 6202.27 | 4618.33 | 6202.57 | 0 |
| mechanism-small-r3 | no-radix-r1 | 308363b2 | 3 | 384.0 | 5872.01 | 4301.35 | 5872.29 | 0 |
| mechanism-small-r3 | no-radix-r2 | 0dd3a97c | 3 | 384.0 | 5884.41 | 4300.61 | 5884.71 | 0 |
| mechanism-small-r3 | observe-after-r1 | 0b40abdf | 2 | 256.0 | 6331.6 | 4747.44 | 6331.87 | 0 |
| mechanism-small-r3 | observe-after-r2 | 9bb91dc9 | 2 | 256.0 | 6324.04 | 4739.82 | 6324.32 | 0 |
| mechanism-small-r3 | observe-before-r1 | b2ff86e3 | 2 | 256.0 | 6325.18 | 4741.32 | 6325.46 | 0 |
| mechanism-small-r3 | observe-before-r2 | 0e185911 | 2 | 256.0 | 6322.27 | 4738.83 | 6322.55 | 0 |
| small-baseline | chunk1024-p2048-r1 | 9e8d2f62 | 2 | 256.0 | 6344.1 | 4759.57 | 6344.38 | 0 |
| small-baseline | chunk1024-p512-r1 | 9d01202e | 1 | 128.0 | 6231.99 | 4661.07 | 6232.27 | 1 |
| small-baseline | chunk4096-p2048-r1 | 6ba6f05e | 1 | 128.0 | 6849.12 | 5277.89 | 6849.38 | 0 |
| small-baseline | chunk4096-p512-r1 | 25c0042f | 1 | 128.0 | 6227.93 | 4656.61 | 6228.23 | 0 |
| small-baseline-r2 | chunk1024-p2048-r1 | 70c6e5e0 | 2 | 256.0 | 6325.74 | 4753.89 | 6326.02 | 0 |
| small-baseline-r2 | chunk1024-p512-r1 | 3768dee1 | 1 | 128.0 | 6222.48 | 4638.21 | 6222.76 | 0 |
| small-baseline-r2 | chunk4096-p2048-r1 | ae3f9875 | 1 | 128.0 | 6840.55 | 5268.64 | 6840.84 | 0 |
| small-baseline-r2 | chunk4096-p512-r1 | c668a989 | 1 | 128.0 | 6230.34 | 4646.35 | 6230.62 | 0 |
| small-baseline-r2 | chunk4096-p512-r2 | - | - | - | 540.85 | 0.0 | 608.42 | 0 |
| small-baseline-r3 | chunk1024-p512-r1 | - | - | - | None | None | 0.0 | 0 |
| small-baseline-r3 | chunk4096-p512-r1 | fd34ae1d | 1 | 128.0 | 6243.32 | 4658.77 | 6243.6 | 0 |
| small-baseline-r4 | chunk1024-p2048-r1 | 5e4aa889 | 2 | 256.0 | 6330.85 | 4759.47 | 6331.13 | 0 |
| small-baseline-r4 | chunk1024-p512-r1 | 066ebf56 | 1 | 128.0 | 6214.7 | 4643.13 | 6214.98 | 0 |
| small-baseline-r4 | chunk1024-p512-r2 | 45cffe51 | 1 | 128.0 | 6236.26 | 4652.22 | 6236.55 | 0 |
| small-baseline-r4 | chunk4096-p2048-r1 | 64f8bd13 | 1 | 128.0 | 6856.91 | 5272.44 | 6857.2 | 0 |
| small-baseline-r4 | chunk4096-p2048-r2 | - | - | - | 2053.32 | 553.16 | 2094.11 | 0 |
| small-baseline-r4 | chunk4096-p512-r1 | 52bdbbe7 | 1 | 128.0 | 6243.84 | 4659.72 | 6244.13 | 0 |
| small-baseline-r4 | chunk4096-p512-r2 | 298a6205 | 1 | 128.0 | 6226.82 | 4656.61 | 6227.1 | 1 |
| small-baseline-r5 | chunk1024-p2048-r1 | 662318d9 | 2 | 256.0 | 6327.02 | 4755.22 | 6327.3 | 0 |
| small-baseline-r5 | chunk1024-p2048-r2 | ba207740 | 2 | 256.0 | 6338.74 | 4755.24 | 6339.02 | 0 |
| small-baseline-r5 | chunk1024-p512-r1 | 214219a7 | 1 | 128.0 | 6223.07 | 4652.36 | 6223.35 | 0 |
| small-baseline-r5 | chunk1024-p512-r2 | 1861daa8 | 1 | 128.0 | 6238.16 | 4653.93 | 6238.43 | 0 |
| small-baseline-r5 | chunk4096-p2048-r1 | b33c4622 | 1 | 128.0 | 6842.79 | 5271.75 | 6843.07 | 0 |
| small-baseline-r5 | chunk4096-p2048-r2 | 897b985d | 1 | 128.0 | 6852.2 | 5281.3 | 6852.48 | 0 |
| small-baseline-r5 | chunk4096-p512-r1 | 01afa556 | 1 | 128.0 | 6207.38 | 4649.19 | 6207.68 | 0 |
| small-baseline-r5 | chunk4096-p512-r2 | 6c1f4654 | 1 | 128.0 | 6226.82 | 4656.16 | 6227.1 | 0 |
| small-profiled | chunk4096-p512-r1 | 0631862b | 1 | 128.0 | 6209.29 | 4639.25 | 6210.05 | 0 |
| small-profiled-clhive | chunk4096-p512-r1 | a2aaf112 | 1 | 128.0 | 6221.59 | 4651.24 | 6221.87 | 0 |
| small-profiled-clhive-r2 | chunk1024-p2048-r1 | 50a3fe8a | 2 | 256.0 | 6319.99 | 4749.58 | 6320.24 | 0 |
| small-profiled-clhive-r2 | chunk1024-p2048-r2 | 24e8518c | 2 | 256.0 | 6328.7 | 4746.33 | 6328.95 | 0 |
| small-profiled-clhive-r2 | chunk1024-p512-r1 | 9c6d9245 | 1 | 128.0 | 6228.05 | 4657.88 | 6228.32 | 0 |
| small-profiled-clhive-r2 | chunk1024-p512-r2 | 67b12f7b | 1 | 128.0 | 6227.13 | 4644.38 | 6227.4 | 1 |
| small-profiled-clhive-r2 | chunk4096-p2048-r1 | 7a8a7ee9 | 1 | 128.0 | 6863.18 | 5279.22 | 6863.43 | 0 |
| small-profiled-clhive-r2 | chunk4096-p2048-r2 | 9f40be9c | 1 | 128.0 | 6836.13 | 5279.13 | 6836.4 | 0 |
| small-profiled-clhive-r2 | chunk4096-p512-r1 | c2f4cd48 | 1 | 128.0 | 6219.02 | 4635.24 | 6219.29 | 0 |
| small-profiled-clhive-r2 | chunk4096-p512-r2 | 00efcc38 | 1 | 128.0 | 6226.18 | 4643.41 | 6226.45 | 0 |
| h4-32k | p16384-eval-pool-r1 | 70fe121b | 8 | 3712.0 | 10357.91 | 8750.63 | 10415.71 | 0 |
| h4-32k | p16384-eval-pool-r2 | b4b39355 | 8 | 3712.0 | 10381.63 | 8772.65 | 10437.98 | 0 |
| h4-32k | p16384-observe-r1 | 8470fdb9 | 8 | 3712.0 | 13281.74 | 11671.41 | 13336.76 | 0 |
| h4-32k | p16384-observe-r2 | ff8a00a8 | 8 | 3712.0 | 13275.84 | 11667.8 | 13332.51 | 0 |
| h4-32k | p32768-eval-pool-r1 | 2c7461b4 | 16 | 12928.0 | 12483.77 | 10875.11 | 12539.31 | 0 |
| h4-32k | p32768-eval-pool-r2 | d2f40f75 | 16 | 12928.0 | 12454.07 | 10842.88 | 12508.12 | 0 |
| h4-32k | p32768-no-radix-r1 | 24f7f951 | 17 | 13056.0 | 10782.88 | 9172.38 | 10837.57 | 0 |
| h4-32k | p32768-no-radix-r2 | 56cd9dde | 17 | 13056.0 | 10797.15 | 9199.52 | 10851.54 | 0 |
| h4-32k | p32768-observe-r1 | 936d0eca | 16 | 12928.0 | 23512.37 | 21901.13 | 23566.57 | 0 |
| h4-32k | p32768-observe-r2 | 5119bfec | 16 | 12928.0 | 23528.18 | 21917.38 | 23583.02 | 0 |
| h4-32k-smoke | p32768-eval-pool-r1 | f048b919 | 16 | 12928.0 | 12497.76 | 10885.3 | 12550.9 | 0 |
| h4-larger-prompts | p16384-clear-cache-r1 | c64c74f2 | 8 | 3712.0 | 11076.07 | 9482.36 | 11133.1 | 0 |
| h4-larger-prompts | p16384-clear-cache-r2 | 27395a06 | 8 | 3712.0 | 11093.65 | 9498.6 | 11150.18 | 0 |
| h4-larger-prompts | p16384-eval-pool-r1 | 0b71bdb3 | 8 | 3712.0 | 9972.52 | 8378.55 | 10031.07 | 0 |
| h4-larger-prompts | p16384-eval-pool-r2 | 175a4c0b | 8 | 3712.0 | 9969.01 | 8360.6 | 10025.9 | 0 |
| h4-larger-prompts | p16384-no-radix-r1 | 904b7b04 | 9 | 3840.0 | 8556.29 | 6946.43 | 8611.35 | 0 |
| h4-larger-prompts | p16384-no-radix-r2 | 32781909 | 9 | 3840.0 | 8559.51 | 6951.68 | 8617.02 | 0 |
| h4-larger-prompts | p16384-observe-r1 | bd9daed9 | 8 | 3712.0 | 12826.29 | 11245.36 | 12883.13 | 0 |
| h4-larger-prompts | p16384-observe-r2 | 5b074a9e | 8 | 3712.0 | 12825.16 | 11212.46 | 12882.66 | 0 |
| h4-larger-prompts | p2048-clear-cache-r1 | 8d406ad7 | 2 | 256.0 | 7268.76 | 5685.05 | 7544.96 | 0 |
| h4-larger-prompts | p2048-clear-cache-r2 | e9bfa868 | 2 | 256.0 | 7031.85 | 5449.29 | 7544.56 | 0 |
| h4-larger-prompts | p2048-eval-pool-r1 | ed5161f2 | 2 | 256.0 | 7712.29 | 6140.77 | 7712.56 | 0 |
| h4-larger-prompts | p2048-eval-pool-r2 | b12b6268 | 2 | 256.0 | 7716.73 | 6146.27 | 7716.99 | 0 |
| h4-larger-prompts | p2048-no-radix-r1 | 62a824eb | 3 | 384.0 | 6886.77 | 5328.94 | 6887.06 | 0 |
| h4-larger-prompts | p2048-no-radix-r2 | 3dbecb54 | 3 | 384.0 | 6904.49 | 5334.47 | 6904.77 | 1 |
| h4-larger-prompts | p2048-observe-r1 | 713cf5b8 | 2 | 256.0 | 7814.56 | 6231.49 | 7814.82 | 0 |
| h4-larger-prompts | p2048-observe-r2 | 97142bea | 2 | 256.0 | 7807.29 | 6235.79 | 7807.57 | 0 |
| h4-larger-prompts | p8192-clear-cache-r1 | 537451df | 4 | 1152.0 | 8444.4 | 6839.99 | 8693.76 | 0 |
| h4-larger-prompts | p8192-clear-cache-r2 | de2c26ec | 4 | 1152.0 | 8217.99 | 6612.46 | 8688.91 | 0 |
| h4-larger-prompts | p8192-eval-pool-r1 | 5a48cbcc | 4 | 1152.0 | 9257.54 | 7652.0 | 9316.29 | 0 |
| h4-larger-prompts | p8192-eval-pool-r2 | 214f6aa9 | 4 | 1152.0 | 9274.99 | 7682.11 | 9333.13 | 0 |
| h4-larger-prompts | p8192-no-radix-r1 | 2a75ab9a | 5 | 1280.0 | 8096.85 | 6504.29 | 8154.51 | 0 |
| h4-larger-prompts | p8192-no-radix-r2 | 5208fedd | 5 | 1280.0 | 8107.98 | 6511.43 | 8167.24 | 0 |
| h4-larger-prompts | p8192-observe-r1 | 3d759041 | 4 | 1152.0 | 10068.76 | 8476.38 | 10126.57 | 1 |
| h4-larger-prompts | p8192-observe-r2 | 2556f420 | 4 | 1152.0 | 10078.71 | 8482.29 | 10137.27 | 0 |
| h4-smoke | p2048-observe-r1 | 4b082bf5 | 2 | 256.0 | 7812.79 | 6228.79 | 7813.06 | 0 |
| h4-smoke | p8192-observe-r1 | 9017c873 | 4 | 1152.0 | 10089.91 | 8485.18 | 10148.71 | 0 |

## Matched observe / eval-pool chunk-resolved pairs (retrospective)

- h4-32k p16384-observe-r1 vs p16384-eval-pool-r1: settled active gap 3712.06 MiB vs capacity sum x32KiB 3712.0 MiB (diff 0.06); chunk-resolved: computed; D_0=-6.0 final D=2684.06 MiB; all within 160MiB=False; lag form (k=0..j-1) all within=True
- h4-32k p16384-observe-r2 vs p16384-eval-pool-r2: settled active gap 3712.06 MiB vs capacity sum x32KiB 3712.0 MiB (diff 0.06); chunk-resolved: computed; D_0=0.01 final D=2688.06 MiB; all within 160MiB=False; lag form (k=0..j-1) all within=True
- h4-32k p32768-observe-r1 vs p32768-eval-pool-r1: settled active gap 12928.12 MiB vs capacity sum x32KiB 12928.0 MiB (diff 0.12); chunk-resolved: computed; D_0=0.01 final D=10876.12 MiB; all within 160MiB=False; lag form (k=0..j-1) all within=True
- h4-32k p32768-observe-r2 vs p32768-eval-pool-r2: settled active gap 12928.12 MiB vs capacity sum x32KiB 12928.0 MiB (diff 0.12); chunk-resolved: computed; D_0=0.01 final D=10880.13 MiB; all within 160MiB=False; lag form (k=0..j-1) all within=True
- h4-larger-prompts p16384-observe-r1 vs p16384-eval-pool-r1: settled active gap 3712.06 MiB vs capacity sum x32KiB 3712.0 MiB (diff 0.06); chunk-resolved: computed; D_0=0.01 final D=2678.06 MiB; all within 160MiB=False; lag form (k=0..j-1) all within=True
- h4-larger-prompts p16384-observe-r2 vs p16384-eval-pool-r2: settled active gap 3712.06 MiB vs capacity sum x32KiB 3712.0 MiB (diff 0.06); chunk-resolved: computed; D_0=0.01 final D=2678.06 MiB; all within 160MiB=False; lag form (k=0..j-1) all within=True
- h4-larger-prompts p2048-observe-r1 vs p2048-eval-pool-r1: settled active gap 256.01 MiB vs capacity sum x32KiB 256.0 MiB (diff 0.01); chunk-resolved: computed; D_0=0.0 final D=124.0 MiB; all within 160MiB=True; lag form (k=0..j-1) all within=True
- h4-larger-prompts p2048-observe-r2 vs p2048-eval-pool-r2: settled active gap 256.01 MiB vs capacity sum x32KiB 256.0 MiB (diff 0.01); chunk-resolved: computed; D_0=0.0 final D=128.01 MiB; all within 160MiB=True; lag form (k=0..j-1) all within=True
- h4-larger-prompts p8192-observe-r1 vs p8192-eval-pool-r1: settled active gap 1152.03 MiB vs capacity sum x32KiB 1152.0 MiB (diff 0.03); chunk-resolved: computed; D_0=-2.0 final D=640.03 MiB; all within 160MiB=False; lag form (k=0..j-1) all within=True
- h4-larger-prompts p8192-observe-r2 vs p8192-eval-pool-r2: settled active gap 1152.03 MiB vs capacity sum x32KiB 1152.0 MiB (diff 0.03); chunk-resolved: computed; D_0=-2.0 final D=640.03 MiB; all within 160MiB=False; lag form (k=0..j-1) all within=True

## Hypotheses

### lazy-scatter / version pinning (WP1 H4; diagnosis H1)
verdict: **consistent_but_not_isolated**

ES accepted records give matched observe-minus-eval-pool gaps for a single measured request (pre-existing SUPPORTED verdict, unchanged); chunk-resolved D_j pairing computed above is retrospective. The historical two-request (#406) growth lacks any between-request sample, so q2 carryover is not identifiable offline.

missing: per-request q2 pairing with matched eval-pool, planned live

### allocator retention (WP1 H1; diagnosis H2)
verdict: **consistent_but_not_isolated**

mx.cache counters before/after per-chunk clear are reported per intervention; cache counters are not a unique resident-footprint partition.

missing: clear-cache vs observe pairs at matched chunks (live 16k stage)

### parked / private KV cache (WP1 H3; diagnosis H6) and pool realization (diagnosis H3)
verdict: **not_identifiable**

req_caches_by_id/cache_pool_len traces are reported; metadata bytes alias active bytes and are never added; no-radix has no shared pool; whether the small 128MiB term is a retained small cache is tested only through the trace, not proven.

missing: allocation-level residency evidence

### logits / final-chunk transients (WP1 H2; diagnosis H4)
verdict: **not_identifiable**

needs_logits=false is intent; _forward_lazy_token falls back to full forward when _trunk_forward returns None (see source line hits); peak-minus-active is not a logits allocation measurement.

missing: branch/allocation instrumentation

### in-flight / chained decode pinning (WP1 H7)
verdict: **not_identifiable**

interval maxima, post-finish decode steps and release windows bound a transient versus retention only.

missing: scheduling/synchronization intervention

### non-MLX process overhead (diagnosis H7)
verdict: **not_identifiable**

role contributions from synchronized tree samples; footprint-active-cache is a diagnostic proxy across incompatible domains.

missing: per-allocation attribution

## Growth-formula finding

The PLANNED form is the primary prospective verdict; the lag form is a secondary additional prediction. Legacy pairs fit the lag form within 160MiB, while the planned form fails at multi-doubling sizes. A one-chunk realization lag is a hypothesis explaining this pattern, not a measured fact.

## Corrections of prior assertions

- needs_logits=false is source intent only; _forward_lazy_token falls back to a full forward when _trunk_forward returns None
- no-radix has no shared pool: never subtract the nominal pool from its accounting
- prefix32 for #406 request2 is inferred; request2 cached_tokens and body are null/unrecorded
- the 21917MiB figure is a scheduler sampled peak, not a whole-tree peak; compare tree sums only with tree sums
- per-role lifetime maxima summed together are not a simultaneous sampled tree peak
- historical hypothesis numbers are not interchangeable: diagnosis H1=WP1 H4 lazy-scatter, H2=WP1 H1 allocator retention, H4=WP1 H2 logits, H6=WP1 H3 parked cache, H3 shared-pool realization, H7 non-MLX process memory (not WP1 H7 in-flight pinning)

Consumed inputs: 509 (full sorted list with digests in the JSON).
