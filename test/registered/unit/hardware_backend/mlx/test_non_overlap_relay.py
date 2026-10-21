"""The non-overlap scheduler relays each batch's sampled tokens through the FutureMap.

The MLX worker returns CPU token ids while the relay buffer lives on the scheduler
device (MPS). An ``index_put`` of a CPU row vector into an MPS buffer is accepted for
one row and rejected for two or more, so ``--disable-overlap-schedule`` on the MLX
backend killed the scheduler as soon as two requests shared a batch.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

import torch

from sglang.srt.managers.overlap_utils import FutureMap, RelayPayload
from sglang.srt.speculative.spec_info import SpeculativeAlgorithm
from sglang.test.ci.ci_register import register_mlx_ci

register_mlx_ci(est_time=1, suite="stage-a-unit-test-mlx")

_HAS_MPS = torch.backends.mps.is_available()


@unittest.skipUnless(_HAS_MPS, "requires an MPS device")
class TestNonOverlapRelayAcrossDevices(unittest.TestCase):
    def _future_map(self) -> FutureMap:
        pool = SimpleNamespace(req_to_token=torch.zeros(8, 4, dtype=torch.int32))
        return FutureMap(
            device=torch.device("mps"),
            spec_algo=SpeculativeAlgorithm.NONE,
            req_to_token_pool=pool,
        )

    def test_cpu_tokens_for_a_multi_request_batch_reach_the_device_buffer(self):
        # Production shape: the scheduler's req_pool_indices are device tensors.
        for index_device in ("cpu", "mps"):
            with self.subTest(index_device=index_device):
                future_map = self._future_map()
                indices = torch.tensor(
                    [1, 2, 3], dtype=torch.int64, device=index_device
                )
                tokens = torch.tensor([11, 22, 33], dtype=torch.int64)  # CPU, as MLX

                future_map.stash(indices, RelayPayload(bonus_tokens=tokens))

                self.assertEqual(
                    future_map.output_tokens_buf[1:4].cpu().tolist(), [11, 22, 33]
                )

    def test_stash_bonus_tokens_accepts_cpu_tokens(self):
        future_map = self._future_map()

        future_map.stash_bonus_tokens(
            torch.tensor([4, 5], dtype=torch.int64, device="mps"),
            torch.tensor([7, 8], dtype=torch.int64),
        )

        self.assertEqual(future_map.output_tokens_buf[4:6].cpu().tolist(), [7, 8])


if __name__ == "__main__":
    unittest.main()
