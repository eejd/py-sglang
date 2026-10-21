"""Device-memory bound of the MLX auxiliary-state snapshots and running requests
(eejd/py-sglang#11).

A hybrid (GDN) model keeps one state snapshot per radix-cached prefix and every
running request holds its own preallocated attention KV. The pool used to be sized
by request count (up to 16384 slots of ~51 MB each on Qwen3.5-4B), never evicted,
and the running requests were not counted at all, so the device ran out of memory.
"""

from __future__ import annotations

import importlib.util
import unittest
from types import SimpleNamespace
from unittest import mock

from sglang.srt.mem_cache.base_prefix_cache import EvictParams
from sglang.test.ci.ci_register import register_mlx_ci

register_mlx_ci(est_time=1, suite="stage-a-unit-test-mlx")

_HAS_MLX = importlib.util.find_spec("mlx") is not None

if _HAS_MLX:
    import mlx.core as mx

    from sglang.srt.hardware_backend.mlx.kv_cache import (
        MlxAttentionKVPool,
        MlxAuxiliaryStatePool,
        MlxAuxiliaryStateReqToTokenPool,
    )
    from sglang.srt.hardware_backend.mlx.kv_cache.auxiliary_state import (
        MIN_AUX_STATE_SLOTS,
        cache_state_nbytes,
    )
    from sglang.srt.hardware_backend.mlx.model_runner import MlxModelRunner
    from sglang.srt.hardware_backend.mlx.model_runner_stub import MlxModelRunnerStub
    from sglang.srt.mem_cache.allocation import ensure_mamba_capacity
    from sglang.srt.runtime_context import get_context, reset_context

MIB = 1024 * 1024
GIB = 1024**3


class _Cache:
    """One auxiliary layer's native cache: a 1 MiB state."""

    def __init__(self):
        self.state = [mx.zeros((256, 1024), dtype=mx.float32)]


@unittest.skipUnless(_HAS_MLX, "requires mlx")
class TestAuxiliaryStatePoolBudget(unittest.TestCase):
    def test_pool_shrinks_to_the_slots_the_budget_backs(self):
        pool = MlxAuxiliaryStatePool(size=100, device="cpu")
        live = pool.alloc(1)

        pool.set_memory_budget(10 * MIB, snapshot_bytes=MIB)

        self.assertEqual(pool.size, 10)
        self.assertEqual(pool.available_size(), 9)  # the live slot stays allocated
        self.assertEqual(sorted(pool.free_slots.tolist()), list(range(2, 11)))
        self.assertEqual(live.tolist(), [1])

    def test_pool_never_shrinks_below_a_slot_in_use(self):
        pool = MlxAuxiliaryStatePool(size=100, device="cpu")
        held = pool.alloc(50)
        pool.free(held[:49])  # slot 50 stays in use

        pool.set_memory_budget(2 * MIB, snapshot_bytes=MIB)

        self.assertEqual(pool.size, 50)
        self.assertEqual(pool.available_size(), 49)

    def test_pool_keeps_a_floor_of_slots_when_the_budget_backs_fewer(self):
        pool = MlxAuxiliaryStatePool(size=100, device="cpu")

        pool.set_memory_budget(2 * MIB, snapshot_bytes=MIB)

        self.assertEqual(pool.size, MIN_AUX_STATE_SLOTS)

    def test_cache_state_nbytes_counts_the_state_of_the_chosen_layers(self):
        cache = [_Cache(), _Cache(), _Cache()]

        self.assertEqual(cache_state_nbytes(cache, [0, 2]), 2 * MIB)

    def test_radix_held_snapshots_are_evicted_before_the_request_binds_its_slot(self):
        pool = MlxAuxiliaryStateReqToTokenPool(
            size=4,
            max_context_len=8,
            device="cpu",
            enable_memory_saver=False,
            auxiliary_state_size=3,
        )
        radix_held = pool.auxiliary_state_pool.alloc(3)  # the tree owns every slot
        evicted = []

        def evict_for_alloc(params: EvictParams):
            evicted.append(params.mamba_num)
            pool.auxiliary_state_pool.free(radix_held[: params.mamba_num])

        tree = SimpleNamespace(
            supports_mamba=lambda: True, evict_for_alloc=evict_for_alloc
        )
        req = SimpleNamespace(
            kv=SimpleNamespace(holds_mamba=False, mamba_ping_pong_track_buffer=None)
        )

        ok = ensure_mamba_capacity(pool, [req], tree)

        self.assertTrue(ok)
        # the live slot and the tracked-snapshot slot of the request
        self.assertEqual(evicted, [2])
        self.assertEqual(pool.auxiliary_state_pool.available_size(), 2)


@unittest.skipUnless(_HAS_MLX, "requires mlx")
class TestSnapshotsFreeTheirMemoryWithoutTheCollector(unittest.TestCase):
    """Evicting a snapshot has to free its device memory at once. The cyclic
    garbage collector does not see device memory, so state kept alive by a Python
    reference cycle piled up between its runs: a burst of long requests ran the
    device out of memory with nearly all of the snapshots evicted
    (eejd/py-sglang#15)."""

    def setUp(self):
        import gc

        self._gc = gc
        gc.collect()
        gc.disable()
        self.addCleanup(gc.enable)

    def test_taking_a_snapshot_leaves_no_cyclic_garbage(self):
        pool = MlxAuxiliaryStatePool(size=4, device="cpu")
        slot = pool.alloc(1)
        self._gc.collect()

        for _ in range(20):
            pool.store_cache(slot[0], [_Cache()], [0])

        self.assertEqual(self._gc.collect(), 0)

    def test_an_evicted_snapshot_gives_its_device_memory_back_at_once(self):
        pool = MlxAuxiliaryStatePool(size=4, device="cpu")
        slot = pool.alloc(1)
        cache = [_Cache()]
        mx.eval(cache[0].state)
        before = mx.get_active_memory()

        pool.store_cache(slot[0], cache, [0])
        held = mx.get_active_memory()
        pool.free(slot)

        self.assertGreater(held - before, MIB // 2)
        self.assertLess(mx.get_active_memory() - before, MIB // 2)

    def test_cache_state_nbytes_leaves_no_cyclic_garbage(self):
        cache = [_Cache(), _Cache()]
        self._gc.collect()

        for _ in range(20):
            cache_state_nbytes(cache, [0, 1])

        self.assertEqual(self._gc.collect(), 0)

    def test_arrays_in_tree_finds_every_array_of_a_nested_state_in_order(self):
        from sglang.srt.hardware_backend.mlx.kv_cache.auxiliary_state import (
            _arrays_in_tree,
        )

        a, b, c, d = (mx.array([i]) for i in range(4))

        found = _arrays_in_tree(([a, (b, 3)], {"k": c, "j": [d]}, "text", None))

        self.assertEqual([x.item() for x in found], [0, 1, 2, 3])


class _Layout:
    """The layout fields the sizing and the init wiring read."""

    def __init__(self, has_aux: bool):
        self.has_auxiliary_state = has_aux
        self.num_full_attention_layers = 8
        self.num_attention_layers = 8
        self.has_sliding_window_layers = False
        self.swa_attention_layer_indices = ()
        self.auxiliary_layer_indices = (0,)
        self.full_attention_layer_indices = (0,)


@unittest.skipUnless(_HAS_MLX, "requires mlx")
class TestRunnerBudget(unittest.TestCase):
    def setUp(self):
        reset_context()
        self.addCleanup(reset_context)

    def _runner(self, has_aux=True, disable_radix_cache=False, snapshot=50 * MIB):
        runner = MlxModelRunner.__new__(MlxModelRunner)
        runner._cache_layout = _Layout(has_aux)
        runner.disable_radix_cache = disable_radix_cache
        runner._mem_fraction_static = 0.8
        runner._max_seq_len = 4096
        runner._get_attn_config = lambda: (4, 256, mx.bfloat16)
        # 50 MiB snapshot, 128 MiB of live attention KV per request
        runner._measure_request_footprint = lambda: (snapshot, 128 * MIB)
        return runner

    def _size(self, runner, explicit_size=None, limit=50 * GIB, **server_args):
        server_args.setdefault("mamba_full_memory_ratio", 0.9)
        with (
            mock.patch(
                "sglang.srt.hardware_backend.mlx.model_runner.psutil.virtual_memory",
                return_value=SimpleNamespace(available=100 * GIB),
            ),
            mock.patch(
                "sglang.srt.hardware_backend.mlx.model_runner.mx.device_info",
                return_value={"max_recommended_working_set_size": limit},
            ),
            mock.patch(
                "sglang.srt.hardware_backend.mlx.model_runner.mx.get_active_memory",
                return_value=0,
            ),
            get_context().override_server_args(**server_args),
        ):
            return runner._compute_pool_size(explicit_size)

    def _expected(self, runner, snapshot=50 * MIB, limit=50 * GIB, ratio=0.9):
        """The sizing arithmetic, written out: (aux budget, free, requests, tokens)."""
        budget = int(limit * runner._mem_fraction_static)
        aux = int(budget * ratio / (1 + ratio))
        free = budget - aux
        per_request = int((snapshot + 128 * MIB) * 1.25)
        requests = max(1, min((free // 4) // per_request, max(aux // snapshot, 8) // 2))
        return aux, free, requests, (free * 3 // 4) // (4 * 32768)

    def test_the_budget_beside_the_snapshots_bounds_requests_and_live_tokens(self):
        plain = self._runner(has_aux=False)
        hybrid = self._runner()

        plain_slots = self._size(plain)
        hybrid_slots = self._size(hybrid)

        aux, free, requests, tokens = self._expected(hybrid)
        self.assertIsNone(plain._aux_state_budget_bytes)
        self.assertIsNone(plain.max_live_requests)
        self.assertEqual(hybrid._aux_state_budget_bytes, aux)
        # a quarter of what is beside the snapshots backs the per-request footprint
        # ((50 + 128) MiB x 1.25 = 222.5 MiB), three quarters the live tokens, each
        # counted once in the pool and up to three times in a growing cache
        self.assertEqual(hybrid.max_live_requests, requests)
        self.assertEqual(hybrid_slots, tokens)
        self.assertLess(hybrid_slots, plain_slots)
        # the snapshots keep their share: nothing the token bound leaves is given
        # to them (a snapshot-dense tree filling a bigger pool killed the engine)
        self.assertEqual(hybrid.aux_state_slots, aux // (50 * MIB))

    def test_a_lower_mem_fraction_static_means_fewer_requests_and_tokens(self):
        low = self._runner()
        low._mem_fraction_static = 0.5
        default = self._runner()

        low_tokens = self._size(low)
        default_tokens = self._size(default)

        self.assertLess(low.max_live_requests, default.max_live_requests)
        self.assertLess(low_tokens, default_tokens)

    LOGGER = "sglang.srt.hardware_backend.mlx.model_runner"

    def _warns(self, runner, **kwargs):
        """The tokens the sizing returns and its 'budget is small' warning lines."""
        with self.assertLogs(self.LOGGER, level="INFO") as logs:
            tokens = self._size(runner, **kwargs)
        warned = [
            line
            for line in logs.output
            if "beside the snapshots" in line and "WARNING" in line
        ]
        return tokens, warned

    def test_few_requests_and_few_tokens_warn(self):
        runner = self._runner(snapshot=400 * MIB)
        runner._mem_fraction_static = 0.3

        tokens, warned = self._warns(runner)

        self.assertLess(runner.max_live_requests, 8)
        self.assertLess(tokens, 65536)
        self.assertEqual(len(warned), 1)
        self.assertIn("--mem-fraction-static", warned[0])

    def test_few_running_requests_alone_warn(self):
        # a big snapshot keeps the token bound high but allows 7 requests
        runner = self._runner(snapshot=450 * MIB)

        tokens, warned = self._warns(runner)

        self.assertEqual(runner.max_live_requests, 7)
        self.assertGreaterEqual(tokens, 65536)
        self.assertEqual(len(warned), 1)

    def test_the_request_threshold_is_eight(self):
        runner = self._runner(snapshot=400 * MIB)

        tokens, warned = self._warns(runner)

        self.assertEqual(runner.max_live_requests, 8)
        self.assertEqual(warned, [])

    def test_few_live_tokens_alone_warn(self):
        runner = self._runner(snapshot=1 * MIB)
        runner._mem_fraction_static = 0.35

        tokens, warned = self._warns(runner)

        self.assertGreaterEqual(runner.max_live_requests, 8)
        self.assertLess(tokens, 65536)
        self.assertEqual(len(warned), 1)

    def test_the_token_threshold_is_65536(self):
        # a working set of 21761167632 B gives exactly 65536 tokens (65535 one byte less)
        runner = self._runner(snapshot=1 * MIB)
        runner._mem_fraction_static = 1.0

        tokens, warned = self._warns(runner, limit=21761167632)

        self.assertEqual(tokens, 65536)
        self.assertEqual(warned, [])

    def test_one_token_below_the_token_threshold_warns(self):
        runner = self._runner(snapshot=1 * MIB)
        runner._mem_fraction_static = 1.0

        tokens, warned = self._warns(runner, limit=21761167631)

        self.assertEqual(tokens, 65535)
        self.assertEqual(len(warned), 1)

    def test_a_roomy_budget_does_not_warn(self):
        runner = self._runner()

        _, warned = self._warns(runner)

        self.assertEqual(warned, [])

    def test_the_log_line_reports_the_final_kv_pool(self):
        runner = self._runner()

        with self.assertLogs(self.LOGGER, level="INFO") as logs:
            slots = self._size(runner)

        line = next(line for line in logs.output if "Auto-sized" in line)
        self.assertIn(f"pool_size={slots}", line)
        self.assertIn(f"kv_pool={slots * 32768 / GIB:.2f} GiB", line)

    def test_running_requests_are_bounded_by_the_snapshot_slots_too(self):
        runner = self._runner()

        self._size(runner, max_mamba_cache_size=16)

        # an explicit slot count replaces the ratio split: 16 slots, 2 per request
        self.assertEqual(runner._snapshot_bytes, 50 * MIB)
        self.assertEqual(runner._aux_state_budget_bytes, 16 * 50 * MIB)
        self.assertEqual(runner.max_live_requests, 8)

    def test_an_explicit_kv_pool_size_still_budgets_the_snapshots(self):
        runner = self._runner()

        with self.assertLogs(self.LOGGER, level="WARNING") as logs:
            slots = self._size(runner, explicit_size=10_000_000)

        self.assertEqual(slots, 10_000_000)
        self.assertEqual(runner._aux_state_budget_bytes, self._expected(runner)[0])
        self.assertEqual(runner.max_live_requests, self._expected(runner)[2])
        self.assertIn("live tokens the device budget backs", logs.output[0])

    def test_an_explicit_snapshot_count_the_device_cannot_hold_is_refused(self):
        runner = self._runner()

        with self.assertRaisesRegex(ValueError, "--max-mamba-cache-size"):
            self._size(runner, max_mamba_cache_size=100_000)

    def test_the_slot_floor_is_kept_with_a_warning_when_the_budget_backs_fewer(self):
        runner = self._runner(snapshot=12 * GIB)

        with self.assertLogs(self.LOGGER, level="WARNING") as logs:
            self._size(runner)

        self.assertTrue(
            any(f"keeps {MIN_AUX_STATE_SLOTS} slots" in line for line in logs.output)
        )
        self.assertEqual(runner.aux_state_slots, MIN_AUX_STATE_SLOTS)
        self.assertEqual(runner.max_live_requests, 1)

    def test_without_the_radix_cache_the_kv_pool_keeps_the_whole_budget(self):
        runner = self._runner(disable_radix_cache=True)

        slots = self._size(runner)

        self.assertIsNone(runner._aux_state_budget_bytes)
        self.assertIsNone(runner.max_live_requests)
        self.assertEqual(slots, self._size(self._runner(has_aux=False)))

    def test_init_cache_pools_hands_the_budget_to_the_auxiliary_pool(self):
        runner = self._runner()
        self._size(runner)
        pool = MlxAuxiliaryStateReqToTokenPool(
            size=4,
            max_context_len=8,
            device="cpu",
            enable_memory_saver=False,
            auxiliary_state_size=100_000,
        )
        runner._pool_size = 16
        runner._attention_kv_pool = None

        with mock.patch.object(MlxAttentionKVPool, "__init__", return_value=None):
            runner.init_cache_pools(pool)

        slots = runner._aux_state_budget_bytes // runner._snapshot_bytes
        self.assertEqual(pool.auxiliary_state_pool.size, slots)
        self.assertLess(slots, 100_000)

    def _sync(self, has_aux: bool):
        runner = self._runner(has_aux=has_aux)
        runner._attention_kv_pool = MlxAttentionKVPool(
            pool_size=16, num_layers=1, n_kv_heads=1, head_dim=2, dtype=mx.float32
        )

        class _Attn:
            keys = mx.ones((1, 1, 8, 2))
            values = mx.ones((1, 1, 8, 2))

        with mock.patch(
            "sglang.srt.hardware_backend.mlx.model_runner.mx.eval"
        ) as evaluate:
            runner._sync_new_kv_to_pool([_Attn()], 0, [3, 4])
        evaluated = [a for call in evaluate.call_args_list for a in call.args]
        return runner._attention_kv_pool.all_buffers(), evaluated

    def test_scatters_into_the_pool_are_materialised_for_a_hybrid_model(self):
        buffers, evaluated = self._sync(has_aux=True)

        self.assertEqual(len(evaluated), len(buffers))
        for buffer in buffers:
            self.assertTrue(any(buffer is a for a in evaluated))

    def test_a_dense_model_keeps_its_lazy_scatters(self):
        _, evaluated = self._sync(has_aux=False)

        self.assertEqual(evaluated, [])


@unittest.skipUnless(_HAS_MLX, "requires mlx")
class TestWorkerHandsTheBudgetToTheStub(unittest.TestCase):
    def test_the_stub_gets_the_runner_budget(self):
        from sglang.srt.hardware_backend.mlx.tp_worker import MlxTpModelWorker

        runner = SimpleNamespace(
            pool_size=1234, max_live_requests=7, aux_state_slots=99
        )
        stub_class = mock.Mock()
        stub_class.validate_startup_weight_load_mode = mock.Mock()
        worker = MlxTpModelWorker.__new__(MlxTpModelWorker)
        worker.model_config = SimpleNamespace()
        worker.gpu_id = 0
        worker.nccl_port = 0
        worker.server_args = SimpleNamespace()
        worker.is_draft_worker = False
        worker.req_to_token_pool = None
        worker.token_to_kv_pool_allocator = None
        worker.memory_pool_config = None
        with (
            mock.patch(
                "sglang.srt.hardware_backend.mlx.model_runner_stub.MlxModelRunnerStub",
                stub_class,
            ),
            mock.patch(
                "sglang.srt.hardware_backend.mlx.model_runner.MlxModelRunner",
                return_value=runner,
            ),
            get_context().override_server_args(
                model_path="dummy",
                trust_remote_code=False,
                disable_radix_cache=False,
                mem_fraction_static=0.8,
                quantization=None,
                revision=None,
                mlx_enable_sampling=False,
                random_seed=0,
                enable_deterministic_inference=False,
                max_total_tokens=None,
            ),
        ):
            worker._init_model_runner()

        kwargs = stub_class.call_args.kwargs
        self.assertEqual(kwargs["mlx_pool_size"], 1234)
        self.assertEqual(kwargs["mlx_max_live_requests"], 7)
        self.assertEqual(kwargs["mlx_aux_state_slots"], 99)


@unittest.skipUnless(_HAS_MLX, "requires mlx")
class TestStubClampsRunningRequests(unittest.TestCase):
    def setUp(self):
        reset_context()
        self.addCleanup(reset_context)

    def _resolve(self, live_limit, requested=None):
        stub = MlxModelRunnerStub.__new__(MlxModelRunnerStub)
        stub.model_config = SimpleNamespace()
        stub.max_total_num_tokens = 1_000_000
        stub._mlx_max_live_requests = live_limit
        with (
            mock.patch(
                "sglang.srt.hardware_backend.mlx.model_runner_stub.mambaish_config",
                return_value=object(),
            ),
            get_context().override_server_args(
                tp_size=1,
                attn_dp_size=1,
                max_running_requests=requested,
                max_mamba_cache_size=None,
                disable_radix_cache=False,
            ),
        ):
            return stub._resolve_max_running_requests()

    def test_the_default_cap_is_bounded_by_the_memory_budget(self):
        self.assertEqual(self._resolve(live_limit=40), 40)

    def test_an_explicit_request_above_the_budget_is_reduced(self):
        self.assertEqual(self._resolve(live_limit=40, requested=1000), 40)

    def test_a_lower_request_is_kept(self):
        self.assertEqual(self._resolve(live_limit=40, requested=7), 7)

    def test_no_budget_leaves_the_default(self):
        self.assertEqual(self._resolve(live_limit=None), 4096)


if __name__ == "__main__":
    unittest.main()
