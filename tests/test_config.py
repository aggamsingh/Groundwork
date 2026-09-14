"""Run-config tests.

The fingerprint and the unjustified-settings list are the two things other work
depends on: ablations are attributed by fingerprint, and phase reports must not
present a guessed default as a finding.
"""

from __future__ import annotations

import unittest

from survey.config.config import (
    ChunkingConfig,
    RetrievalConfig,
    RunConfig,
    default_config,
)


class TestFingerprint(unittest.TestCase):
    def test_identical_configs_share_a_fingerprint(self) -> None:
        self.assertEqual(RunConfig().fingerprint(), RunConfig().fingerprint())

    def test_a_changed_setting_changes_the_fingerprint(self) -> None:
        a = RunConfig()
        b = RunConfig(retrieval=RetrievalConfig(top_k=10))
        self.assertNotEqual(a.fingerprint(), b.fingerprint())

    def test_commentary_does_not_change_the_fingerprint(self) -> None:
        # Two runs with the same settings must match even after one is annotated,
        # or the same experiment appears twice in an ablation table.
        a = RunConfig()
        b = RunConfig(notes="annotated later", justified=["retrieval.top_k"])
        self.assertEqual(a.fingerprint(), b.fingerprint())

    def test_nested_changes_are_caught(self) -> None:
        a = RunConfig()
        b = RunConfig(chunking=ChunkingConfig(chunk_tokens=256))
        self.assertNotEqual(a.fingerprint(), b.fingerprint())


class TestFlatten(unittest.TestCase):
    def test_nested_keys_are_dotted(self) -> None:
        flat = RunConfig().flatten()
        self.assertIn("chunking.chunk_tokens", flat)
        self.assertIn("retrieval.top_k", flat)
        self.assertEqual(flat["chunking.chunk_tokens"], 512)

    def test_lists_are_serialised(self) -> None:
        flat = RunConfig(justified=["a", "b"]).flatten()
        self.assertEqual(flat["justified"], "a,b")


class TestUnjustified(unittest.TestCase):
    def test_everything_tuneable_starts_unjustified(self) -> None:
        pending = RunConfig().unjustified()
        self.assertIn("chunking.chunk_tokens", pending)
        self.assertIn("retrieval.top_k", pending)
        self.assertIn("verification.entailment_threshold", pending)

    def test_justifying_a_setting_removes_it(self) -> None:
        config = RunConfig(justified=["retrieval.top_k"])
        self.assertNotIn("retrieval.top_k", config.unjustified())
        self.assertIn("chunking.chunk_tokens", config.unjustified())

    def test_non_tuneable_fields_are_not_listed(self) -> None:
        # corpus, phase and provenance are facts about the run, not knobs.
        pending = RunConfig().unjustified()
        self.assertNotIn("corpus", pending)
        self.assertNotIn("phase", pending)
        self.assertNotIn("code_version", pending)

    def test_description_warns_and_lists_values(self) -> None:
        text = RunConfig().describe_unjustified()
        self.assertIn("NOT results", text)
        self.assertIn("chunking.chunk_tokens = 512", text)

    def test_description_is_clean_when_all_justified(self) -> None:
        config = RunConfig()
        config.justified = config.unjustified()
        self.assertIn("All tuneable settings", config.describe_unjustified())

    def test_new_settings_default_to_unjustified(self) -> None:
        # The list is computed from `justified`, not maintained by hand, so a
        # setting added later cannot silently arrive pre-blessed.
        config = RunConfig(justified=["retrieval.top_k"])
        self.assertGreater(len(config.unjustified()), 5)


class TestDefaultConfig(unittest.TestCase):
    def test_matches_the_spec_baseline_shape(self) -> None:
        # Spec section 5, Phase 2: fixed 512-token flat chunks, dense-only,
        # top-k=5, single generation call, no citations enforced.
        config = default_config()
        self.assertEqual(config.chunking.strategy, "flat")
        self.assertEqual(config.chunking.chunk_tokens, 512)
        self.assertEqual(config.chunking.overlap_tokens, 0)
        self.assertEqual(config.retrieval.mode, "dense")
        self.assertEqual(config.retrieval.top_k, 5)
        self.assertFalse(config.retrieval.rerank)
        self.assertFalse(config.generation.require_citations)

    def test_baseline_is_not_marked_justified(self) -> None:
        # The baseline comes from the spec, which makes it the agreed starting
        # point -- not a measured result.
        self.assertEqual(default_config().justified, [])

    def test_models_are_unset_until_chosen(self) -> None:
        config = default_config()
        self.assertEqual(config.embedding.model_name, "unset")
        self.assertEqual(config.generation.provider, "unset")


if __name__ == "__main__":
    unittest.main()
