"""Local JSON persistence for minimal SACCO workflow state (teaching prototype)."""
import json
import os
from pathlib import Path
import tempfile

from agent.state import validate_workflow_state


class MemoryAccessError(PermissionError):
    """Raised when a requester is not authorized to access a saved case."""


class CaseMemoryStore:
    def __init__(self, path):
        self.path = Path(path)

    def _read(self):
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Memory store is unreadable or invalid JSON") from exc
        if not isinstance(data, dict):
            raise ValueError("Memory store root must be an object")
        return data

    def _write(self, records):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".memory-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(records, stream, indent=2, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)


    @staticmethod
    def _actor_fields(actor):
        """Read a trusted actor context supplied by application/session code.

        Expected keys: membership_number, role (member/officer), and optionally
        authorized_member_numbers. Never build this object from model output.
        """
        if not isinstance(actor, dict):
            raise MemoryAccessError("Trusted actor context must be an object")
        membership_number = actor.get("membership_number")
        role = actor.get("role", "member")
        authorized = actor.get("authorized_member_numbers")
        if not isinstance(membership_number, str) or not membership_number.strip():
            raise MemoryAccessError("Trusted actor membership identity is required")
        if role not in {"member", "officer"}:
            raise MemoryAccessError("Unsupported actor role")
        if authorized is not None and not isinstance(authorized, (set, frozenset, list, tuple)):
            raise MemoryAccessError("Officer authorization must be supplied as a collection")
        return membership_number, role, set(authorized or ())

    def save_case_state(self, state, actor):
        """Contract API: save a case only when the trusted actor owns it."""
        membership_number, role, _ = self._actor_fields(actor)
        if role != "member":
            raise MemoryAccessError("Only the case owner may save case state")
        return self.save(state, membership_number)

    def load_case_state(self, case_id, actor):
        """Contract API: load own case or an explicitly authorized officer read."""
        membership_number, role, authorized = self._actor_fields(actor)
        return self.load(
            case_id, membership_number, actor_role=role,
            authorized_member_numbers=authorized if role == "officer" else None,
        )

    def list_my_case_states(self, actor):
        """Return minimal metadata for cases owned by the trusted actor."""
        membership_number, role, _ = self._actor_fields(actor)
        if role != "member":
            raise MemoryAccessError("This interface lists only the member's own cases")
        return self.list_for_owner(membership_number)

    def delete_case_state(self, case_id, actor):
        """Contract API: delete only the owner's saved case."""
        membership_number, role, _ = self._actor_fields(actor)
        if role != "member":
            raise MemoryAccessError("Only the case owner may delete case state")
        return self.delete(case_id, membership_number)

    def save(self, state, actor_membership_number):
        validate_workflow_state(state)
        if state["owner_membership_number"] != actor_membership_number:
            raise MemoryAccessError("Cannot save another member's case")
        records = self._read()
        existing = records.get(state["case_id"])
        if existing and existing.get("owner_membership_number") != actor_membership_number:
            raise MemoryAccessError("Case ID belongs to another member")
        records[state["case_id"]] = state
        self._write(records)

    def load(
        self, case_id, actor_membership_number, *, actor_role="member",
        authorized_member_numbers=None,
    ):
        """Load a case for its owner or an explicitly authorized officer.

        `authorized_member_numbers` must come from trusted authorization logic;
        callers must not populate it directly from untrusted user input.
        """
        state = self._read().get(case_id)
        if state is None:
            return None
        owner = state.get("owner_membership_number")
        is_owner = actor_role == "member" and owner == actor_membership_number
        is_authorized_officer = (
            actor_role == "officer"
            and authorized_member_numbers is not None
            and owner in authorized_member_numbers
        )
        if not (is_owner or is_authorized_officer):
            raise MemoryAccessError("Requester is not authorized to read this case")
        return validate_workflow_state(state)

    def list_for_owner(self, actor_membership_number):
        return [
            {"case_id": cid, "status": state["status"],
             "created_at": state["created_at"], "updated_at": state["updated_at"]}
            for cid, state in self._read().items()
            if state.get("owner_membership_number") == actor_membership_number
        ]

    def delete(self, case_id, actor_membership_number):
        """Delete only when requested by the case owner (retention policy)."""
        records = self._read()
        state = records.get(case_id)
        if state is None:
            return False
        if state.get("owner_membership_number") != actor_membership_number:
            raise MemoryAccessError("Cannot delete another member's case")
        del records[case_id]
        self._write(records)
        return True
