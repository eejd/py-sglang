"""A request for logprobs the MLX path cannot produce is refused, not crashed on.

Without --mlx-enable-sampling the MLX worker returns no logprobs, and the output
processing of a request that asked for them (``logprobs: true``) raised
``AttributeError: 'NoneType' object has no attribute 'tolist'`` in the scheduler,
which stopped the whole engine.
"""

import unittest
from types import SimpleNamespace
from unittest import mock

from sglang.srt.managers import scheduler as scheduler_module
from sglang.srt.managers.scheduler import mlx_logprob_refusal
from sglang.test.ci.ci_register import register_cpu_ci

register_cpu_ci(est_time=5, suite="base-a-test-cpu")


def _refusal(*, mlx, sampling, return_logprob=True, start=10, input_len=10):
    with (
        mock.patch.object(scheduler_module, "use_mlx", return_value=mlx),
        mock.patch.object(
            scheduler_module,
            "get_device",
            return_value=SimpleNamespace(mlx_enable_sampling=sampling),
        ),
    ):
        return mlx_logprob_refusal(
            return_logprob=return_logprob,
            logprob_start_len=start,
            input_len=input_len,
        )


class TestMlxLogprobRefusal(unittest.TestCase):
    def test_logprobs_without_sampling_are_refused(self):
        self.assertIn("--mlx-enable-sampling", _refusal(mlx=True, sampling=False))

    def test_logprobs_with_sampling_are_served(self):
        self.assertIsNone(_refusal(mlx=True, sampling=True))

    def test_a_request_without_logprobs_is_never_refused(self):
        self.assertIsNone(_refusal(mlx=True, sampling=False, return_logprob=False))
        self.assertIsNone(_refusal(mlx=True, sampling=True, return_logprob=False))

    def test_other_backends_are_not_affected(self):
        self.assertIsNone(_refusal(mlx=False, sampling=False))

    def test_prompt_logprobs_are_refused_on_the_sampling_path(self):
        reason = _refusal(mlx=True, sampling=True, start=3, input_len=10)

        self.assertIn("logprob_start_len", reason)

    def test_the_prompt_boundary_is_output_only(self):
        # logprob_start_len == len(prompt) is the default for output logprobs
        self.assertIsNone(_refusal(mlx=True, sampling=True, start=10, input_len=10))
        self.assertIsNotNone(_refusal(mlx=True, sampling=True, start=9, input_len=10))


if __name__ == "__main__":
    unittest.main()
