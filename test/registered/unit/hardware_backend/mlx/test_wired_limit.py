"""SGLANG_MLX_WIRED_LIMIT_GB decides whether and how much MLX memory is wired."""

from __future__ import annotations

import importlib.util
import unittest
from unittest import mock

from sglang.srt.environ import envs
from sglang.test.ci.ci_register import register_mlx_ci

register_mlx_ci(est_time=1, suite="stage-a-unit-test-mlx")

_HAS_MLX = importlib.util.find_spec("mlx") is not None

GIB = 1024**3

if _HAS_MLX:
    from sglang.srt.hardware_backend.mlx import model_runner


@unittest.skipUnless(_HAS_MLX, "requires mlx")
class TestWiredLimit(unittest.TestCase):
    def _apply(self, limit_gb):
        with (
            mock.patch.object(
                model_runner.mx,
                "device_info",
                return_value={"max_recommended_working_set_size": 16 * GIB},
            ),
            mock.patch.object(model_runner.mx, "set_wired_limit") as set_limit,
            envs.SGLANG_MLX_WIRED_LIMIT_GB.override(limit_gb),
        ):
            model_runner._apply_wired_limit()
        return set_limit

    def test_unset_wires_the_recommended_working_set(self):
        self._apply(None).assert_called_once_with(16 * GIB)

    def test_zero_sets_no_wired_limit(self):
        self._apply(0).assert_not_called()

    def test_a_given_size_is_wired(self):
        self._apply(8).assert_called_once_with(8 * GIB)

    def test_a_size_above_the_recommended_one_is_capped_with_a_warning(self):
        with self.assertLogs(model_runner.logger, level="WARNING") as logs:
            set_limit = self._apply(64)

        set_limit.assert_called_once_with(16 * GIB)
        self.assertIn("exceeds the recommended", logs.output[0])

    def test_a_negative_size_is_rejected(self):
        with self.assertRaises(ValueError):
            self._apply(-1)


if __name__ == "__main__":
    unittest.main()
