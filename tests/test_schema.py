from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from survey.extraction.schema import (
    SchemaError,
    SchemaNotFrozenError,
    field_names,
    load_schema,
)

FROZEN = {
    "corpus": "semcom",
    "status": "frozen",
    "frozen_date": "2026-09-09",
    "fields": [
        {"name": "task", "type": "enum", "cardinality": "many"},
        {"name": "snr_range", "type": "numeric_range", "cardinality": "one"},
    ],
    "comparison_table_default_columns": ["task"],
}


class SchemaTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write(self, doc: object, corpus: str = "semcom") -> None:
        (self.dir / f"{corpus}.yaml").write_text(
            yaml.safe_dump(doc), encoding="utf-8"
        )


class TestFrozenGate(SchemaTestCase):
    def test_frozen_schema_loads(self) -> None:
        self.write(FROZEN)
        schema = load_schema("semcom", self.dir)
        self.assertEqual(field_names(schema), ["task", "snr_range"])

    def test_draft_is_refused(self) -> None:
        self.write({**FROZEN, "status": "draft", "frozen_date": None})
        with self.assertRaises(SchemaNotFrozenError) as ctx:
            load_schema("semcom", self.dir)
        self.assertIn("CHECKPOINT 2", str(ctx.exception))

    def test_frozen_without_date_is_refused(self) -> None:
        self.write({**FROZEN, "frozen_date": None})
        with self.assertRaises(SchemaError):
            load_schema("semcom", self.dir)

    def test_bad_date_is_refused(self) -> None:
        self.write({**FROZEN, "frozen_date": "sometime in september"})
        with self.assertRaises(SchemaError):
            load_schema("semcom", self.dir)

    def test_missing_file_names_the_checkpoint(self) -> None:
        with self.assertRaises(SchemaError) as ctx:
            load_schema("nonexistent", self.dir)
        self.assertIn("CHECKPOINT 2", str(ctx.exception))


class TestStructuralValidation(SchemaTestCase):
    def test_duplicate_field_names_rejected(self) -> None:
        doc = {**FROZEN, "fields": FROZEN["fields"] + [FROZEN["fields"][0]]}
        self.write(doc)
        with self.assertRaises(SchemaError) as ctx:
            load_schema("semcom", self.dir)
        self.assertIn("duplicate", str(ctx.exception).lower())

    def test_field_missing_cardinality_rejected(self) -> None:
        self.write({**FROZEN, "fields": [{"name": "task", "type": "enum"}]})
        with self.assertRaises(SchemaError) as ctx:
            load_schema("semcom", self.dir)
        self.assertIn("cardinality", str(ctx.exception))

    def test_bad_cardinality_value_rejected(self) -> None:
        self.write(
            {**FROZEN, "fields": [{"name": "t", "type": "enum", "cardinality": "lots"}]}
        )
        with self.assertRaises(SchemaError):
            load_schema("semcom", self.dir)

    def test_table_column_must_name_a_real_field(self) -> None:
        self.write({**FROZEN, "comparison_table_default_columns": ["task", "ghost"]})
        with self.assertRaises(SchemaError) as ctx:
            load_schema("semcom", self.dir)
        self.assertIn("ghost", str(ctx.exception))

    def test_empty_fields_rejected(self) -> None:
        self.write({**FROZEN, "fields": []})
        with self.assertRaises(SchemaError):
            load_schema("semcom", self.dir)


class TestShippedSchema(unittest.TestCase):
    """The real schema/semcom.yaml, frozen 2026-09-13 (CHECKPOINT 2).

    Until it was frozen this asserted the opposite — that the draft refused to
    load. Inverted on the freeze rather than deleted, so the repo schema stays
    covered either way.
    """

    def setUp(self) -> None:
        self.dir = Path(__file__).resolve().parents[1] / "schema"
        if not (self.dir / "semcom.yaml").exists():
            self.skipTest("no schema/semcom.yaml in repo")
        self.schema = load_schema("semcom", self.dir)

    def test_is_frozen_and_loads(self) -> None:
        self.assertEqual(str(self.schema["frozen_date"]), "2026-09-13")

    def test_carries_the_users_screening_vocabulary(self) -> None:
        # These come from the user's own review notes (D-011). If one silently
        # disappears, the gold table and the extractor stop sharing a vocabulary.
        for name in (
            "type",
            "modality",
            "encoder",
            "channel",
            "transmission",
            "ch_aware_train",
            "metric_validated",
            "failure_mode",
        ):
            self.assertIn(name, field_names(self.schema))

    def test_editorial_columns_are_not_extraction_fields(self) -> None:
        # verdict/status are the user's judgements about their own argument.
        # Scoring extraction on them would depress every accuracy number.
        names = field_names(self.schema)
        self.assertNotIn("verdict", names)
        self.assertNotIn("status", names)
        self.assertIn("verdict", self.schema["human_only_columns"])

    def test_metric_validated_is_critical_and_strictly_gated(self) -> None:
        field = next(
            f for f in self.schema["fields"] if f["name"] == "metric_validated"
        )
        self.assertEqual(field.get("priority"), "critical")
        thresholds = self.schema["abstention_thresholds"]
        self.assertGreater(thresholds["metric_validated"], thresholds["default"])


if __name__ == "__main__":
    unittest.main()
