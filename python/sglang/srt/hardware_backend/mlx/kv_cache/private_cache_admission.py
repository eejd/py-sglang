"""Admission bound on the private attention caches of running MLX requests.

The shared token pool counts a cached prefix once, but every running request
holds its own contiguous attention cache (``ContiguousAttentionKVCache``: it
starts at ``max_seq_len`` tokens and doubles), and a request that hits the radix
tree gathers its whole prefix into it. N concurrent requests sharing a P-token
prefix therefore cost the pool P tokens and the device N x capacity(P) tokens of
attention KV, which nothing bounded: 24 x 32k hits and 8 x 131k hits killed a
snapshot-saturated Qwen3.5-4B engine (py-sglang#15).

``MlxTokenToKVPoolAllocator`` hands the scheduler a ``MlxPrefillBudget`` that
refuses (the request stays queued) a new request whose private cache would take
the running requests' total past ``budget_tokens``. The budget is a number of
cache tokens (capacity, not used length); the runner derives it from what
``mem_fraction_static`` leaves for live requests.
"""

from __future__ import annotations

from typing import Callable

from sglang.srt.mem_cache.allocator.token import TokenToKVPoolAllocator
from sglang.srt.mem_cache.prefill_budget import PrefillBudget


def private_cache_capacity(tokens: int, base: int) -> int:
    """Capacity of a contiguous cache holding *tokens*: ``base`` doubled until it fits."""
    capacity = max(base, 1)
    while capacity < tokens:
        capacity *= 2
    return capacity


class MlxPrefillBudget(PrefillBudget):
    """Token-pool budget plus the private-cache bound of the running requests."""

    def __init__(self, allocator: MlxTokenToKVPoolAllocator, *args, **kwargs):
        super().__init__(allocator, *args, **kwargs)
        # Capacity tokens of the requests admitted earlier in this scheduling pass:
        # their caches are built after the pass, so the runner cannot see them yet.
        self.private_admitted = 0
        # Capacity of the whole prompt of the request checked last: a chunked
        # prefill is asked about with its first chunk only, but its cache ends up
        # holding the whole prompt.
        self.checked_prompt_capacity = 0

    def _private_fits(self, need: int) -> bool:
        if need == 0:
            return True
        held = self.allocator.private_tokens_in_use() + self.private_admitted
        # Nothing else running: always admit. A lone request is bounded by the
        # token pool (its capacity is below twice the pool).
        return held == 0 or held + need <= self.allocator.private_budget_tokens

    def check_prefill(self, **kwargs):
        pending = self.allocator.pending_private_tokens
        self.checked_prompt_capacity = (
            private_cache_capacity(
                kwargs["input_tokens"], self.allocator.private_cache_base
            )
            if pending
            else 0
        )
        if not self._private_fits(max(pending, self.checked_prompt_capacity)):
            return (False, None)
        return super().check_prefill(**kwargs)

    def can_allocate_prefill(self, **kwargs) -> bool:
        return self._private_fits(
            self.allocator.pending_private_tokens
        ) and super().can_allocate_prefill(**kwargs)

    def reserve(self, *args, **kwargs) -> None:
        # Called when a request is admitted, right after the scheduler asked
        # ``request_slot_reserve`` about it: charge what it asked.
        pending = self.allocator.pending_private_tokens
        if pending:
            self.private_admitted += max(pending, self.checked_prompt_capacity)
        self.allocator.pending_private_tokens = 0
        self.checked_prompt_capacity = 0
        super().reserve(*args, **kwargs)


class MlxTokenToKVPoolAllocator(TokenToKVPoolAllocator):
    """Token allocator of the MLX stub that bounds the running requests' private caches."""

    def __init__(
        self,
        *args,
        private_budget_tokens: int,
        private_tokens_in_use: Callable[[], int],
        private_cache_base: int,
        **kwargs,
    ):
        self.private_budget_tokens = private_budget_tokens
        self.private_tokens_in_use = private_tokens_in_use
        self.private_cache_base = private_cache_base
        # Capacity the request the scheduler asked about last would add.
        self.pending_private_tokens = 0
        super().__init__(*args, **kwargs)

    def create_prefill_budget(self, tree_cache, *, num_mixed_decode_tokens=0):
        self.pending_private_tokens = 0
        return MlxPrefillBudget(
            self, tree_cache, num_mixed_decode_tokens=num_mixed_decode_tokens
        )

    def request_slot_reserve(
        self, *, has_req_pool_slot: bool, prefill_tokens: int = 0
    ) -> int:
        """Record what a NEW request's private cache will hold (a continuing chunk
        already has its cache, which the runner counts); the pool is not charged."""
        self.pending_private_tokens = (
            0
            if has_req_pool_slot
            else private_cache_capacity(prefill_tokens, self.private_cache_base)
        )
        return 0
