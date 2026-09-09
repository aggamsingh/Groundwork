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


class TestShippedDraft(unittest.TestCase):
    """The draft in schema/ must stay unusable until the user freezes it."""

    def test_repo_schema_is_still_a_draft_and_refuses_to_load(self) -> None:
        repo_schema = Path(__file__).resolve().parents[1] / "schema"
        if not (repo_schema / "semcom.yaml").exists():
            self.skipTest("no schema/semcom.yaml in repo")
        with self.assertRaises(SchemaNotFrozenError):
            load_schema("semcom", repo_schema)


if __name__ == "__main__":
    unittest.main()
