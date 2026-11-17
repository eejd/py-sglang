"""Grammar masks apply on the MLX greedy path, without --mlx-enable-sampling."""

from __future__ import annotations

import importlib.util
import unittest
from types import SimpleNamespace

from sglang.test.ci.ci_register import register_mlx_ci
from sglang.test.test_utils import CustomTestCase

register_mlx_ci(est_time=5, suite="stage-a-unit-test-mlx")

_HAS_MLX = importlib.util.find_spec("mlx") is not None

if _HAS_MLX:
    import mlx.core as mx
    import torch


@unittest.skipUnless(_HAS_MLX, "requires mlx")
class TestGrammarWithoutSampling(CustomTestCase):
    VOCAB = 3

    @classmethod
    def setUpClass(cls):
        from sglang.srt.runtime_context import get_context

        cls._config = get_context().override_server_args(mlx_enable_sampling=False)
        cls._config.install()
        cls.addClassCleanup(cls._config.restore)

    def test_greedy_selection_honours_the_edit_rows(self):
        from sglang.srt.hardware_backend.mlx.model_runner import MlxModelRunner

        runner = object.__new__(MlxModelRunner)
        runner._enable_sampling = False
        runner._sanitize_nan = False
        logits = mx.array([[0.0, 5.0, 1.0]])
        rows = mx.array([[0.0, -float("inf"), 0.0]])

        masked, _ = runner._select_tokens_with_logprobs(logits, ["a"], [[]], rows)
        plain, _ = runner._select_tokens_with_logprobs(logits, ["a"], [[]], None)

        self.assertEqual(masked.tolist(), [2])
        self.assertEqual(plain.tolist(), [1])

    @staticmethod
    def _worker():
        from sglang.srt.hardware_backend.mlx.tp_worker import MlxTpModelWorker

        return MlxTpModelWorker.__new__(MlxTpModelWorker)

    def _batch(self, *, grammar, logit_bias):
        class FakeGrammar:
            def apply_vocab_mask(self, logits, vocab_mask):
                logits[0, 1] = -float("inf")

        sinfo = SimpleNamespace(
            grammars=None,
            logit_bias=logit_bias,
            vocab_size=self.VOCAB,
            grammar_mask=None,
        )
        sinfo.update_regex_vocab_mask = lambda: setattr(
            sinfo,
            "grammar_mask",
            SimpleNamespace(grammar=FakeGrammar(), vocab_mask=torch.zeros(1, 1)),
        )
        req = SimpleNamespace(rid="r0", grammar=object() if grammar else None)
        return SimpleNamespace(
            reqs=[req], sampling_info=sinfo, has_grammar=grammar, return_logprob=False
        )

    def test_a_grammar_batch_gets_its_mask_and_ignores_logit_bias(self):
        bias = torch.tensor([[0.0, 0.0, 9.0]])
        rows = self._worker()._build_logit_edit_rows(
            self._batch(grammar=True, logit_bias=bias)
        )

        self.assertEqual(rows["r0"].tolist(), [0.0, -float("inf"), 0.0])

    def test_logit_bias_alone_is_not_applied(self):
        bias = torch.tensor([[0.0, 0.0, 9.0]])

        self.assertIsNone(
            self._worker()._build_logit_edit_rows(
                self._batch(grammar=False, logit_bias=bias)
            )
        )

    def test_a_grammar_batch_is_not_chain_safe(self):
        from sglang.srt.hardware_backend.mlx.scheduler_mixin import (
            SchedulerMlxOverlapMixin,
        )

        for grammar in (True, False):
            batch = self._batch(grammar=grammar, logit_bias=None)
            self.assertEqual(
                SchedulerMlxOverlapMixin._mlx_batch_chain_safe(None, batch), not grammar
            )


if __name__ == "__main__":
    unittest.main()
