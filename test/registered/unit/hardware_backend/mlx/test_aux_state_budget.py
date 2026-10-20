"""Device-memory bound of the MLX auxiliary-state snapshots (eejd/py-sglang#11).

A hybrid (GDN) model keeps one state snapshot per radix-cached prefix. The pool used
to be sized by request count (up to 16384 slots of ~51 MB each on Qwen3.5-4B) and
never evicted, so the device ran out of memory first.
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
        MlxAuxiliaryStatePool,
        MlxAuxiliaryStateReqToTokenPool,
    )
    from sglang.srt.hardware_backend.mlx.model_runner import MlxModelRunner
    from sglang.srt.mem_cache.allocation import ensure_mamba_capacity
    from sglang.srt.runtime_context import get_context, reset_context


class _Cache:
    """One auxiliary layer's native cache: a 1 MiB state."""

    def __init__(self):
        self.state = [mx.zeros((256, 1024), dtype=mx.float32)]


@unittest.skipUnless(_HAS_MLX, "requires mlx")
class TestAuxiliaryStateBudget(unittest.TestCase):
    def test_pool_shrinks_to_the_slots_the_budget_backs(self):
        pool = MlxAuxiliaryStatePool(size=100, device="cpu")
        live = pool.alloc(1)
        pool.set_memory_budget(10 * 1024 * 1024)  # snapshot size not known yet
        self.assertEqual(pool.size, 100)

        pool.store_cache(live, [_Cache()], [0])  # first snapshot: 1 MiB

        self.assertEqual(pool.size, 10)
        self.assertEqual(pool.available_size(), 9)  # the live slot stays allocated
        self.assertEqual(sorted(pool.free_slots.tolist()), list(range(2, 11)))

    def test_pool_never_shrinks_below_a_slot_in_use(self):
        pool = MlxAuxiliaryStatePool(size=100, device="cpu")
        held = pool.alloc(50)
        pool.free(held[:49])  # slot 50 stays in use, 1..49 go to the back of the list
        pool.set_memory_budget(2 * 1024 * 1024)

        pool.store_cache(held[49:], [_Cache()], [0])

        self.assertEqual(pool.size, 50)
        self.assertEqual(pool.available_size(), 49)

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
class TestKvPoolBudgetSplit(unittest.TestCase):
    def setUp(self):
        reset_context()
        self.addCleanup(reset_context)

    def _runner(self, has_aux: bool, disable_radix_cache: bool = False):
        runner = MlxModelRunner.__new__(MlxModelRunner)
        runner._cache_layout = SimpleNamespace(
            has_auxiliary_state=has_aux,
            num_full_attention_layers=8,
            num_attention_layers=8,
        )
        runner.disable_radix_cache = disable_radix_cache
        runner._mem_fraction_static = 1.0
        runner._get_attn_config = lambda: (4, 256, mx.bfloat16)
        return runner

    def _size(self, runner, ratio=0.9):
        gib = 1024**3
        with mock.patch(
            "sglang.srt.hardware_backend.mlx.model_runner.psutil.virtual_memory",
            return_value=SimpleNamespace(available=100 * gib),
        ), mock.patch(
            "sglang.srt.hardware_backend.mlx.model_runner.mx.device_info",
            return_value={"max_recommended_working_set_size": 50 * gib},
        ), mock.patch(
            "sglang.srt.hardware_backend.mlx.model_runner.mx.get_active_memory",
            return_value=0,
        ), get_context().override_server_args(mamba_full_memory_ratio=ratio):
            return runner._compute_pool_size(None)

    def test_a_hybrid_model_with_the_radix_cache_leaves_a_share_for_snapshots(self):
        plain = self._runner(has_aux=False)
        hybrid = self._runner(has_aux=True)

        plain_slots = self._size(plain)
        hybrid_slots = self._size(hybrid)

        gib = 1024**3
        self.assertIsNone(plain._aux_state_budget_bytes)
        # ratio 0.9: the snapshots get 0.9 / 1.9 of the budget, the KV pool the rest
        self.assertAlmostEqual(hybrid._aux_state_budget_bytes / (50 * gib), 0.9 / 1.9, 3)
        self.assertAlmostEqual(hybrid_slots / plain_slots, 1 / 1.9, 3)

    def test_without_the_radix_cache_the_kv_pool_keeps_the_whole_budget(self):
        runner = self._runner(has_aux=True, disable_radix_cache=True)

        slots = self._size(runner)

        self.assertIsNone(runner._aux_state_budget_bytes)
        self.assertEqual(slots, self._size(self._runner(has_aux=False)))


if __name__ == "__main__":
    unittest.main()
