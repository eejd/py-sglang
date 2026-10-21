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
    GIB = 1024**3

    def setUp(self):
        reset_context()
        self.addCleanup(reset_context)

    def _runner(self, has_aux=True, disable_radix_cache=False, snapshot=50 * MIB):
        runner = MlxModelRunner.__new__(MlxModelRunner)
        runner._cache_layout = _Layout(has_aux)
        runner.disable_radix_cache = disable_radix_cache
        runner._mem_fraction_static = 1.0
        runner._get_attn_config = lambda: (4, 256, mx.bfloat16)
        # 50 MiB snapshot, 134 MiB of live attention KV: Qwen3.5-4B's measured shape
        runner._measure_request_footprint = lambda: (snapshot, 128 * MIB)
        return runner

    def _size(self, runner, explicit_size=None, **server_args):
        server_args.setdefault("mamba_full_memory_ratio", 0.9)
        with (
            mock.patch(
                "sglang.srt.hardware_backend.mlx.model_runner.psutil.virtual_memory",
                return_value=SimpleNamespace(available=100 * self.GIB),
            ),
            mock.patch(
                "sglang.srt.hardware_backend.mlx.model_runner.mx.device_info",
                return_value={"max_recommended_working_set_size": 50 * self.GIB},
            ),
            mock.patch(
                "sglang.srt.hardware_backend.mlx.model_runner.mx.get_active_memory",
                return_value=0,
            ),
            get_context().override_server_args(**server_args),
        ):
            return runner._compute_pool_size(explicit_size)

    def test_a_hybrid_model_with_the_radix_cache_reserves_live_kv_then_splits(self):
        plain = self._runner(has_aux=False)
        hybrid = self._runner()

        plain_slots = self._size(plain)
        hybrid_slots = self._size(hybrid)

        self.assertIsNone(plain._aux_state_budget_bytes)
        self.assertIsNone(plain.max_live_requests)
        # 10% of the 50 GiB working set is kept for the running requests' KV
        budget = 45 * self.GIB
        self.assertEqual(hybrid._aux_state_budget_bytes, int(budget * 0.9 / 1.9))
        self.assertAlmostEqual(hybrid_slots / plain_slots, 1 / 1.9 * 0.9, 2)
        # 5 GiB / 128 MiB = 40 running requests, 2 snapshot slots each
        self.assertEqual(hybrid.max_live_requests, 40)

    def test_running_requests_are_bounded_by_the_snapshot_slots_too(self):
        runner = self._runner()

        self._size(runner, max_mamba_cache_size=16)

        # an explicit slot count replaces the ratio split: 16 slots, 2 per request
        self.assertEqual(runner._aux_state_budget_bytes, 16 * 50 * MIB)
        self.assertEqual(runner.max_live_requests, 8)

    def test_an_explicit_kv_pool_size_still_budgets_the_snapshots(self):
        runner = self._runner()

        slots = self._size(runner, explicit_size=1234)

        self.assertEqual(slots, 1234)
        self.assertIsNotNone(runner._aux_state_budget_bytes)
        self.assertEqual(runner.max_live_requests, 40)

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
