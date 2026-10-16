"""Synthetic demonstration of save/load continuity, access control, and deletion."""
from pathlib import Path
import json
import tempfile
from agent.state import new_workflow_state, update_stage, apply_preparation_observation
from agent.memory import CaseMemoryStore, MemoryAccessError


def main():
    with tempfile.TemporaryDirectory(prefix="sacco-week6-") as folder:
        store = CaseMemoryStore(Path(folder) / "memory.json")
        owner = "HS-SYNTHETIC-0001"
        state = new_workflow_state(
            owner, "member",
            "Prepare a Development Loan case for UGX 2,000,000 over 12 months.",
            "demo-case-001",
        )
        update_stage(state, "collecting_policy")
        apply_preparation_observation(
            state, member_record_retrieved=True,
            policy_documents=["development_loan.md"],
            repayment_calculated=False,
            missing_requirements=["Confirm repayment term"],
        )
        owner_actor = {"membership_number": owner, "role": "member"}
        store.save_case_state(state, owner_actor)
        # A second store instance simulates a separate application session.
        restored = CaseMemoryStore(Path(folder) / "memory.json").load_case_state(
            "demo-case-001", owner_actor
        )
        assert restored["preparation"]["policy_documents"] == ["development_loan.md"]
        print("Restored case context:")
        print(json.dumps({
            "case_id": restored["case_id"], "status": restored["status"],
            "stage": restored["workflow"]["current_stage"],
            "policy_already_retrieved": restored["preparation"]["policy_documents"],
            "missing_requirements": restored["preparation"]["missing_requirements"],
        }, indent=2))
        try:
            store.load_case_state(
                "demo-case-001",
                {"membership_number": "HS-SYNTHETIC-0002", "role": "member"},
            )
        except MemoryAccessError:
            print("PASS: another member cannot read this case")
        else:
            raise AssertionError("Unauthorized read was allowed")
        assert store.delete_case_state("demo-case-001", owner_actor)
        assert store.load_case_state("demo-case-001", owner_actor) is None
        print("PASS: owner can delete saved case")
        print("PASS: temporary synthetic-data demo completed")


if __name__ == "__main__":
    main()
