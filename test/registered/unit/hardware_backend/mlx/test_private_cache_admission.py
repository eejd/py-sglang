"""Admission bound on the running requests' private attention caches (py-sglang#15).

N requests that share a cached P-token prefix cost the shared pool P tokens once but
hold N private caches of capacity(P): without a bound 24 x 32k hits and 8 x 131k hits
killed a snapshot-saturated engine. The allocator's budget keeps the new request queued.
"""

from __future__ import annotations

import importlib.util
import unittest
from types import SimpleNamespace

from sglang.test.ci.ci_register import register_mlx_ci

register_mlx_ci(est_time=1, suite="stage-a-unit-test-mlx")

_HAS_MLX = importlib.util.find_spec("mlx") is not None

if _HAS_MLX:
    import mlx.core as mx
    import torch

    from sglang.srt.hardware_backend.mlx.kv_cache.attention_kv_cache import (
        ContiguousAttentionKVCache,
    )
    from sglang.srt.hardware_backend.mlx.kv_cache.private_cache_admission import (
        MlxPrefillBudget,
        MlxTokenToKVPoolAllocator,
        private_cache_capacity,
    )
    from sglang.srt.hardware_backend.mlx.model_runner import MlxModelRunner

BASE = 4096
BUDGET = 8 * BASE  # 32768 capacity tokens


class _Tree:
    """Just what PrefillBudget reads of the radix tree."""

    def supports_mamba(self):
        return False

    def evictable_size(self):
        return 0

    def full_evictable_size(self):
        return 0


def _allocator(in_use, pool_tokens=1_000_000):
    allocator = MlxTokenToKVPoolAllocator(
        size=pool_tokens,
        dtype=torch.float32,
        device="cpu",
        kvcache=SimpleNamespace(),
        need_sort=False,
        private_budget_tokens=BUDGET,
        private_tokens_in_use=in_use,
        private_cache_base=BASE,
    )
    return allocator


def _ask(budget, has_slot, prefill_tokens, prompt_tokens=None):
    """What the scheduler does for one candidate: ask the allocator, then check."""
    budget.allocator.request_slot_reserve(
        has_req_pool_slot=has_slot, prefill_tokens=prefill_tokens
    )
    return budget.check_prefill(
        extend_input_len=16,
        total_tokens=16,
        max_new_tokens=8,
        input_tokens=prefill_tokens if prompt_tokens is None else prompt_tokens,
        swa_host_hit_length=0,
        chunk_limit=None,
    )[0]


def _admit(budget):
    budget.reserve(16, 8)


@unittest.skipUnless(_HAS_MLX, "requires mlx")
class TestPrivateCacheCapacity(unittest.TestCase):
    def test_capacity_is_the_base_doubled_until_it_fits(self):
        self.assertEqual(private_cache_capacity(1, BASE), BASE)
        self.assertEqual(private_cache_capacity(BASE, BASE), BASE)
        self.assertEqual(private_cache_capacity(BASE + 1, BASE), 2 * BASE)
        self.assertEqual(private_cache_capacity(32_064, BASE), 32_768)
        self.assertEqual(private_cache_capacity(131_073, BASE), 262_144)

    def test_it_matches_what_a_contiguous_cache_really_allocates(self):
        for tokens in (100, 4097, 20_000, 32_768, 32_769):
            cache = ContiguousAttentionKVCache(max_seq_len=BASE)
            cache.update_and_fetch(
                mx.zeros((1, 1, tokens, 2)), mx.zeros((1, 1, tokens, 2))
            )
            self.assertEqual(
                cache.max_seq_len, private_cache_capacity(tokens, BASE), tokens
            )


@unittest.skipUnless(_HAS_MLX, "requires mlx")
class TestPrivateCacheAdmission(unittest.TestCase):
    def _budget(self, in_use=0):
        allocator = _allocator(lambda: in_use)
        return allocator.create_prefill_budget(_Tree())

    def test_a_request_that_fits_beside_the_running_ones_is_admitted(self):
        budget = self._budget(in_use=BASE)

        self.assertTrue(
            _ask(budget, False, 3 * BASE)
        )  # 4 x BASE more: 5 x BASE < 8 x BASE

    def test_a_request_that_would_pass_the_budget_waits(self):
        budget = self._budget(in_use=5 * BASE)

        self.assertFalse(
            _ask(budget, False, 3 * BASE)
        )  # capacity 4 x BASE: 9 x BASE > 8 x BASE

    def test_the_boundary_is_inclusive(self):
        budget = self._budget(in_use=4 * BASE)

        self.assertTrue(_ask(budget, False, 3 * BASE))  # 4 + 4 == 8
        self.assertFalse(_ask(self._budget(in_use=4 * BASE + 1), False, 3 * BASE))

    def test_requests_admitted_earlier_in_the_pass_count_before_their_caches_exist(
        self,
    ):
        budget = self._budget(in_use=0)

        admitted = 0
        for _ in range(10):
            if not _ask(budget, False, 2 * BASE):  # capacity 2 x BASE each
                break
            _admit(budget)
            admitted += 1

        self.assertEqual(admitted, 4)  # 4 x 2 x BASE == the budget

    def test_a_chunked_first_chunk_is_charged_for_the_whole_prompt(self):
        budget = self._budget(in_use=5 * BASE)

        # the scheduler asks about a 1-chunk prefill of a 3 x BASE prompt
        fits = _ask(budget, False, BASE, prompt_tokens=3 * BASE)  # capacity 4 x BASE

        self.assertFalse(fits)  # 5 + 4 > 8; the first chunk alone (1) would fit

    def test_a_chunked_first_chunk_is_admitted_at_the_whole_prompts_capacity(self):
        budget = self._budget(in_use=0)

        admitted = 0
        for _ in range(10):
            if not _ask(budget, False, BASE, prompt_tokens=3 * BASE):
                break
            _admit(budget)
            admitted += 1

        self.assertEqual(admitted, 2)  # 2 x 4 x BASE == the budget

    def test_a_continuation_after_a_check_is_not_charged_the_stale_prompt(self):
        budget = self._budget(in_use=0)
        _ask(budget, False, BASE, prompt_tokens=4 * BASE)  # checked, not admitted

        # a continuing chunk of another request is admitted without a check
        budget.allocator.request_slot_reserve(
            has_req_pool_slot=True, prefill_tokens=BASE
        )
        _admit(budget)

        self.assertEqual(budget.private_admitted, 0)

    def test_a_continuing_chunk_is_not_charged_again(self):
        budget = self._budget(in_use=BUDGET)  # full: its own cache is in `in_use`

        self.assertTrue(_ask(budget, True, 100 * BASE))

    def test_a_lone_request_is_always_admitted(self):
        budget = self._budget(in_use=0)

        self.assertTrue(_ask(budget, False, 40 * BASE))  # capacity 64 x BASE > budget

    def test_a_second_oversized_request_waits_for_the_first(self):
        budget = self._budget(in_use=0)
        self.assertTrue(_ask(budget, False, 40 * BASE))
        _admit(budget)

        self.assertFalse(_ask(budget, False, 40 * BASE))

    def test_a_refused_request_does_not_charge_the_pass(self):
        budget = self._budget(in_use=7 * BASE)
        self.assertFalse(_ask(budget, False, 2 * BASE))

        # nothing was admitted: a smaller one still fits
        self.assertTrue(_ask(budget, False, BASE))

    def test_can_allocate_prefill_applies_the_same_bound(self):
        budget = self._budget(in_use=7 * BASE)
        budget.allocator.request_slot_reserve(
            has_req_pool_slot=False, prefill_tokens=2 * BASE
        )

        fits = budget.can_allocate_prefill(
            paged_input=16, extend_input_len=16, max_new_tokens=8, chunk_limit=None
        )

        self.assertFalse(fits)

    def test_each_pass_starts_with_a_clean_slate(self):
        allocator = _allocator(lambda: 0)
        first = allocator.create_prefill_budget(_Tree())
        self.assertTrue(_ask(first, False, 4 * BASE))
        _admit(first)

        second = allocator.create_prefill_budget(_Tree())

        self.assertEqual(second.private_admitted, 0)
        self.assertIsInstance(second, MlxPrefillBudget)

    def test_the_pool_is_not_charged_for_the_private_cache(self):
        allocator = _allocator(lambda: 0)

        reserve = allocator.request_slot_reserve(
            has_req_pool_slot=False, prefill_tokens=3 * BASE
        )

        self.assertEqual(reserve, 0)


@unittest.skipUnless(_HAS_MLX, "requires mlx")
class TestRunnerPrivateCacheAccounting(unittest.TestCase):
    def _runner(self):
        runner = object.__new__(MlxModelRunner)
        runner._cache_layout = SimpleNamespace(
            first_attention_layer_index=0, has_auxiliary_state=True
        )
        runner._req_caches = {}
        runner._prefill_caches = {}
        return runner

    def _cache(self, capacity):
        return [ContiguousAttentionKVCache(max_seq_len=capacity)]

    def test_running_and_unfinalised_requests_both_count(self):
        runner = self._runner()
        runner._req_caches["running"] = self._cache(32_768)
        runner._prefill_caches["launched"] = self._cache(65_536)

        self.assertEqual(runner.private_cache_tokens_in_use(), 98_304)

    def test_a_cache_that_grew_counts_its_new_capacity(self):
        runner = self._runner()
        cache = self._cache(4096)
        runner._req_caches["r"] = cache
        before = runner.private_cache_tokens_in_use()

        cache[0].update_and_fetch(mx.zeros((1, 1, 5000, 2)), mx.zeros((1, 1, 5000, 2)))

        self.assertEqual((before, runner.private_cache_tokens_in_use()), (4096, 8192))

    def test_a_removed_request_frees_its_share(self):
        runner = self._runner()
        runner._req_token_ids = {}
        runner._req_sampling = {}
        runner._req_pool_idx = {}
        runner._req_synced_offset = {}
        runner._cache_pool = []
        runner._req_caches["r"] = self._cache(32_768)
        runner._prefill_caches["r"] = self._cache(32_768)

        runner.remove_request("r")

        self.assertEqual(runner.private_cache_tokens_in_use(), 0)


if __name__ == "__main__":
    unittest.main()
