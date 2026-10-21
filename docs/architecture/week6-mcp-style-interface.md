# Week 6 — MCP-Style Interface Specification

This is a local Python capability contract. It is **not** a claim that an MCP server or MCP transport has been implemented.

## Capability: `case_memory`

The public methods below are implemented by `CaseMemoryStore` in `src/agent/memory.py`:

```python
save_case_state(state: dict, actor: dict) -> None
load_case_state(case_id: str, actor: dict) -> dict | None
list_my_case_states(actor: dict) -> list[dict]
delete_case_state(case_id: str, actor: dict) -> bool
```

`actor` is a trusted context supplied by application/session code. Its shape is:

```python
{
    "membership_number": "HS-SYNTHETIC-0001",
    "role": "member",  # "member" or "officer"
    # Officers only; obtained from trusted authorization logic:
    "authorized_member_numbers": {"HS-SYNTHETIC-0001"}
}
```

Do not construct trusted actor context from model-generated claims or unverified user input.

## Behavior and outputs

- `save_case_state`: validates the state and saves only if the actor is the member who owns the case. Officers cannot write member case state through this interface.
- `load_case_state`: returns the state for an owner; returns `None` if the case does not exist; raises `MemoryAccessError` when access is unauthorized. An officer can read a cross-member case only when the trusted actor context includes that case owner in `authorized_member_numbers`.
- `list_my_case_states`: returns only case ID, status, and creation/update timestamps for the member's own cases. This method is intentionally not an officer-wide search.
- `delete_case_state`: deletes only the owner's record, returns `True` when deleted and `False` when not found, and raises `MemoryAccessError` for an unauthorized deletion.
- Invalid state/schema/limits raise `ValueError`; authorization failures raise `MemoryAccessError`.

Legacy internal methods (`save`, `load`, `list_for_owner`, and `delete`) remain available to the existing loop for compatibility. New integrations should use the public contract methods above.

## Permission and safety boundary

The default is deny. Cross-member officer reading is a narrow, read-only exception requiring authorization from trusted application/session code. It is not enough for a requester or model to state that they are an officer. The capability does not execute arbitrary tools, approve/reject/score/disburse loans, change member accounts, or calculate financial values. A history read returns historical preparation metadata and must not call Gemini or any loan tools.

If this capability is exposed through MCP in a later iteration, expose these narrow methods with explicit schemas rather than a generic filesystem tool.
