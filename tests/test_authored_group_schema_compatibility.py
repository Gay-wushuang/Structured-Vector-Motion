from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import jsonschema

from svm.document import (
    AUTHORED_GROUP_AUTHORITY,
    AUTHORED_GROUP_TYPE,
    DocumentDialect,
    authored_group_identity,
    validate_document,
)
from svm.document_io import read_document, select_document_dialect, write_document
from svm.evaluator import DocumentError, canonical_bytes
from svm.revisions import RevisionStore, Transaction

ROOT = Path(__file__).resolve().parents[1]
BASELINE_SCHEMA = ROOT / "schema/svm-document-v0.1.schema.json"
AUTHORED_SCHEMA = ROOT / "schema/svm-document-v0.1-authored-group-assembly-v0.1.schema.json"


class AuthoredGroupSchemaCompatibilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline_schema = json.loads(BASELINE_SCHEMA.read_bytes())
        cls.authored_schema = json.loads(AUTHORED_SCHEMA.read_bytes())
        cls.old_document = json.loads((ROOT / "examples/001-head-basic.svm.json").read_bytes())

    def authored_document(self):
        document = copy.deepcopy(self.old_document)
        members = sorted(entity["id"] for entity in document["entities"][:2])
        group_id, membership_hash = authored_group_identity(members)
        document.setdefault("groups", []).append(
            {
                "id": group_id,
                "kind": "explicit-group",
                "members": members,
                "provenance": {
                    "type": AUTHORED_GROUP_TYPE,
                    "authority_identity": AUTHORED_GROUP_AUTHORITY,
                    "source_revision_id": "revision:" + "1" * 64,
                    "source_document_hash": "sha256:"
                    + hashlib.sha256(canonical_bytes(self.old_document)).hexdigest(),
                    "membership_hash": membership_hash,
                },
            }
        )
        return document

    def assert_extension_rejects(self, mutate):
        document = self.authored_document()
        mutate(document["groups"][-1])
        with self.assertRaises((DocumentError, KeyError, TypeError)):
            validate_document(document, DocumentDialect.AUTHORED_GROUP_ASSEMBLY)

    def test_extension_schema_preserves_baseline_except_closed_provenance_union(self):
        baseline = copy.deepcopy(self.baseline_schema)
        extension = copy.deepcopy(self.authored_schema)
        self.assertEqual(
            extension.pop("$id"),
            "https://structured-vector-motion.dev/schema/"
            "svm-document-v0.1-authored-group-assembly-v0.1.schema.json",
        )
        baseline.pop("$id")
        baseline.pop("title")
        extension.pop("title")
        baseline_group = baseline["$defs"]["groupDefinition"]
        extension_group = extension["$defs"]["groupDefinition"]
        baseline_provenance = baseline_group["properties"].pop("provenance")
        extension_provenance = extension_group["properties"].pop("provenance")
        self.assertEqual(extension, baseline)
        self.assertEqual(extension_provenance["oneOf"][:2], baseline_provenance["oneOf"])
        self.assertEqual(len(extension_provenance["oneOf"]), 3)

    def test_new_reader_accepts_old_inference_and_construction_documents_unchanged(self):
        documents = (
            self.old_document,
            json.loads((ROOT / "examples/022-group-transform.svm.json").read_bytes()),
            json.loads(
                (ROOT / "examples/046-representation-certification/accepted.svm.json").read_bytes()
            ),
        )
        for document in documents:
            with self.subTest(document_id=document["document_id"]):
                jsonschema.validate(document, self.baseline_schema)
                jsonschema.validate(document, self.authored_schema)
                validate_document(document)
                validate_document(document, DocumentDialect.AUTHORED_GROUP_ASSEMBLY)
                self.assertEqual(select_document_dialect(document), DocumentDialect.BASELINE)

    def test_authored_group_requires_explicit_extension_reader(self):
        document = self.authored_document()
        jsonschema.validate(document, self.authored_schema)
        validate_document(document, DocumentDialect.AUTHORED_GROUP_ASSEMBLY)
        self.assertEqual(select_document_dialect(document), DocumentDialect.AUTHORED_GROUP_ASSEMBLY)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(document, self.baseline_schema)
        with self.assertRaisesRegex(DocumentError, "construction provenance"):
            validate_document(document)
        with self.assertRaises(DocumentError):
            RevisionStore.create(document)
        store = RevisionStore.create(document, dialect=DocumentDialect.AUTHORED_GROUP_ASSEMBLY)
        self.assertEqual(store.document_dialect, DocumentDialect.AUTHORED_GROUP_ASSEMBLY)
        self.assertEqual(store.get_document(store.head), document)
        revision = store.commit(store.head, Transaction("transaction:structural-reader", ()))
        self.assertEqual(store.get_document(revision.revision_id), document)

    def test_membership_identity_is_deterministic_and_recomputed(self):
        document = self.authored_document()
        members = document["groups"][0]["members"]
        self.assertEqual(authored_group_identity(members), authored_group_identity(sorted(members)))
        expected_id, expected_hash = authored_group_identity(members)
        self.assertEqual(document["groups"][0]["id"], expected_id)
        self.assertEqual(document["groups"][0]["provenance"]["membership_hash"], expected_hash)
        for field in ("id", "membership_hash"):
            with self.subTest(field=field):
                self.assert_extension_rejects(
                    lambda group, field=field: (
                        group.update(id="group:" + "0" * 64)
                        if field == "id"
                        else group["provenance"].update(membership_hash="sha256:" + "0" * 64)
                    )
                )

    def test_authored_provenance_is_closed_and_sources_are_structural_only(self):
        mutations = (
            lambda group: group["provenance"].update(source_revision_id="revision:bad"),
            lambda group: group["provenance"].update(source_document_hash=True),
            lambda group: group["provenance"].update(type="authored-group-assembly@0.2"),
            lambda group: group["provenance"].update(authority_identity="caller"),
            lambda group: group["provenance"].update(authenticated=True),
        )
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                self.assert_extension_rejects(mutation)
        document = self.authored_document()
        document["groups"][0]["provenance"].update(
            source_revision_id="revision:" + "f" * 64,
            source_document_hash="sha256:" + "e" * 64,
        )
        validate_document(document, DocumentDialect.AUTHORED_GROUP_ASSEMBLY)

    def test_existing_group_structure_transform_and_member_rules_still_apply(self):
        mutations = (
            lambda group: group.update(members=[group["members"][0]] * 2),
            lambda group: group["members"].append("entity:missing"),
            lambda group: group.update(
                transform={
                    "translate": [0, 0],
                    "rotation_degrees": 0,
                    "scale": 0,
                    "origin": [0, 0],
                }
            ),
            lambda group: group.update(extra=True),
        )
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                self.assert_extension_rejects(mutation)

    def test_import_export_preserves_provenance_and_rejects_downgrade(self):
        document = self.authored_document()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            authored_path = root / "authored.svm.json"
            self.assertEqual(
                write_document(authored_path, document),
                DocumentDialect.AUTHORED_GROUP_ASSEMBLY,
            )
            loaded, dialect = read_document(authored_path)
            self.assertEqual(dialect, DocumentDialect.AUTHORED_GROUP_ASSEMBLY)
            self.assertEqual(loaded, document)
            self.assertEqual(
                loaded["groups"][0]["provenance"],
                document["groups"][0]["provenance"],
            )
            rejected = root / "baseline.svm.json"
            with self.assertRaises(DocumentError):
                write_document(rejected, document, dialect=DocumentDialect.BASELINE)
            self.assertFalse(rejected.exists())

            old_path = root / "old.svm.json"
            self.assertEqual(write_document(old_path, self.old_document), DocumentDialect.BASELINE)
            old_loaded, old_dialect = read_document(old_path)
            self.assertEqual(old_dialect, DocumentDialect.BASELINE)
            self.assertEqual(old_loaded, self.old_document)


if __name__ == "__main__":
    unittest.main()
