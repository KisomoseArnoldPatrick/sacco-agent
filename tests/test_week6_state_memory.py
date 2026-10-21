
"""Automated Week 6 tests for SACCO workflow state and persistent memory."""

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from agent.state import (
    new_workflow_state,
    validate_workflow_state,
    apply_preparation_observation,
)
from agent.memory import CaseMemoryStore, MemoryAccessError


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = REPO_ROOT / "evidence" / "memory"
RESULTS_PATH = EVIDENCE_DIR / "test_results.json"


def record_test_evidence(scenario, details):
    """Append a successful test scenario to the evidence log."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    if RESULTS_PATH.exists():
        try:
            records = json.loads(
                RESULTS_PATH.read_text(encoding="utf-8")
            )
            if not isinstance(records, list):
                records = []
        except (json.JSONDecodeError, OSError):
            records = []
    else:
        records = []

    records.append({
        "scenario": scenario,
        "result": "PASS",
        "details": details,
    })

    RESULTS_PATH.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


class Week6Tests(unittest.TestCase):

    def setUp(self):
        # Isolate each test so it cannot accidentally use another
        # test's saved case.
        self.temp = tempfile.TemporaryDirectory()
        self.store_path = Path(self.temp.name) / "memory.json"
        self.store = CaseMemoryStore(self.store_path)

        self.owner = f"HS-SYNTHETIC-{uuid.uuid4().hex[:8]}"
        self.case_id = f"case-{uuid.uuid4().hex}"

        self.state = new_workflow_state(
            self.owner,
            "member",
            "Prepare a synthetic loan case for human review.",
            self.case_id,
        )

        self.member_actor = {
            "membership_number": self.owner,
            "role": "member",
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_01_write_and_read_in_new_session(self):
        """Saved preparation context survives a new store instance."""
        apply_preparation_observation(
            self.state,
            policy_documents=["development_loan.md"],
            missing_requirements=["Confirm repayment term"],
        )

        self.store.save_case_state(
            self.state, self.member_actor
        )

        # A new instance simulates reopening memory in another session.
        new_session_store = CaseMemoryStore(self.store_path)
        loaded = new_session_store.load_case_state(
            self.case_id, self.member_actor
        )

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["case_id"], self.case_id)
        self.assertEqual(
            loaded["preparation"]["policy_documents"],
            ["development_loan.md"],
        )
        self.assertIn(
            "Confirm repayment term",
            loaded["preparation"]["missing_requirements"],
        )

        record_test_evidence(
            "write_and_read_in_new_session",
            "Saved case and preparation context restored using a new store instance.",
        )

    def test_02_unauthorized_access_denied(self):
        """Another member cannot read, delete, or save as the owner."""
        self.store.save_case_state(
            self.state, self.member_actor
        )

        other_actor = {
            "membership_number": f"HS-OTHER-{uuid.uuid4().hex[:8]}",
            "role": "member",
        }

        with self.assertRaises(MemoryAccessError):
            self.store.load_case_state(
                self.case_id, other_actor
            )

        with self.assertRaises(MemoryAccessError):
            self.store.delete_case_state(
                self.case_id, other_actor
            )

        with self.assertRaises(MemoryAccessError):
            self.store.save_case_state(
                self.state, other_actor
            )

        record_test_evidence(
            "unauthorized_access_denied",
            "Unauthorized read, delete, and save attempts were denied.",
        )

    def test_03_authorized_officer_can_read_case(self):
        """An officer may read only when trusted authorization is supplied."""
        self.store.save_case_state(
            self.state, self.member_actor
        )

        officer = {
            "membership_number": "OFFICER-SYNTHETIC-01",
            "role": "officer",
        }

        # Officer role alone does not grant access.
        with self.assertRaises(MemoryAccessError):
            self.store.load_case_state(
                self.case_id, officer
            )

        authorized_officer = {
            **officer,
            "authorized_member_numbers": {self.owner},
        }

        loaded = self.store.load_case_state(
            self.case_id, authorized_officer
        )
        self.assertEqual(loaded["case_id"], self.case_id)

        # An officer cannot overwrite the member's case.
        with self.assertRaises(MemoryAccessError):
            self.store.save_case_state(
                loaded, authorized_officer
            )

        record_test_evidence(
            "officer_access_control",
            "Authorized officer read succeeded; unauthorized read and officer write were denied.",
        )

    def test_04_owner_can_delete_case_history(self):
        """Deleting a case makes it unavailable for later retrieval."""
        self.store.save_case_state(
            self.state, self.member_actor
        )

        self.assertTrue(
            self.store.delete_case_state(
                self.case_id, self.member_actor
            )
        )

        self.assertIsNone(
            self.store.load_case_state(
                self.case_id, self.member_actor
            )
        )

        self.assertFalse(
            self.store.delete_case_state(
                self.case_id, self.member_actor
            )
        )

        record_test_evidence(
            "owner_deletion",
            "Owner deleted case history; subsequent retrieval returned None.",
        )

    def test_05_workflow_limits_are_enforced(self):
        """Excessive iteration and tool-call counts are rejected."""
        validate_workflow_state(self.state)

        workflow = self.state["workflow"]
        self.assertEqual(workflow["max_iterations"], 6)
        self.assertEqual(workflow["max_calls_per_tool"], 2)

        workflow["iteration_count"] = 7
        with self.assertRaises(ValueError):
            validate_workflow_state(self.state)

        workflow["iteration_count"] = 0
        workflow["tool_call_counts"]["retrieve_policy"] = 3

        with self.assertRaises(ValueError):
            validate_workflow_state(self.state)

        record_test_evidence(
            "workflow_limits",
            "Validation rejected excessive iteration and tool-call counts.",
        )

    def test_06_memory_minimizes_stored_data(self):
        """Raw member records and full policy text are excluded."""
        self.assertNotIn("member_record", self.state)
        self.assertNotIn("policy_content", self.state)

        metadata = self.state["memory_metadata"]
        self.assertFalse(metadata["contains_raw_member_record"])
        self.assertFalse(metadata["contains_full_policy_text"])

        record_test_evidence(
            "data_minimization",
            "State excludes raw member records and full policy text.",
        )

    def test_07_loan_decisions_are_rejected(self):
        """Memory cannot store a loan approval or rejection decision."""
        self.assertNotIn("loan_decision", self.state)
        self.assertNotIn("approval_status", self.state)

        self.state["loan_decision"] = "approved"
        with self.assertRaises(ValueError):
            validate_workflow_state(self.state)

        record_test_evidence(
            "decision_boundary",
            "State validation rejected a prohibited loan-decision field.",
        )

    def test_08_public_contract_methods_and_owner_listing(self):
        """All four documented memory methods work for the owner."""
        self.store.save_case_state(
            self.state, self.member_actor
        )

        loaded = self.store.load_case_state(
            self.case_id, self.member_actor
        )
        self.assertEqual(loaded["case_id"], self.case_id)

        listed = self.store.list_my_case_states(
            self.member_actor
        )
        self.assertEqual(
            [row["case_id"] for row in listed],
            [self.case_id],
        )

        # Listing should expose summary metadata, not full case content.
        self.assertNotIn("member_record", listed[0])
        self.assertNotIn("policy_content", listed[0])

        self.assertTrue(
            self.store.delete_case_state(
                self.case_id, self.member_actor
            )
        )

        record_test_evidence(
            "public_memory_contract",
            "Save, load, owner-only listing, and delete methods worked.",
        )

    def test_09_listing_does_not_expose_other_members_cases(self):
        """A member's listing contains only that member's cases."""
        self.store.save_case_state(
            self.state, self.member_actor
        )

        other_actor = {
            "membership_number": "HS-SYNTHETIC-OTHER",
            "role": "member",
        }

        other_cases = self.store.list_my_case_states(other_actor)
        self.assertNotIn(
            self.case_id,
            [row["case_id"] for row in other_cases],
        )

        record_test_evidence(
            "owner_only_listing",
            "Member listing did not expose another member's case.",
        )

    def test_10_boolean_counter_and_unknown_tool_rejected(self):
        """Boolean counters and unapproved tool names are rejected."""
        workflow = self.state["workflow"]

        workflow["iteration_count"] = True
        with self.assertRaises(ValueError):
            validate_workflow_state(self.state)

        workflow["iteration_count"] = 0
        workflow["tool_call_counts"]["delete_member"] = 0

        with self.assertRaises(ValueError):
            validate_workflow_state(self.state)

        record_test_evidence(
            "strict_state_validation",
            "Boolean counter and unapproved tool name were rejected.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
