# Initial Architecture / Context Diagram — Week 1

![SACCO agent initial architecture](week1-context-diagram.png)

## Description

The loan officer interacts with a chat/case workspace. A bounded agent orchestrator:
1. Retrieves policy context from a document corpus (RAG).
2. Calls deterministic tools — an illustrative schedule calculator and a case-file compiler — through a guardrail layer that enforces validation, the tool allow-list, and logging.
3. Produces a draft case packet, which is sent to the credit committee/supervisor for human review and decision.

No path in this diagram allows the agent to approve, disburse, or modify a real account — that boundary is enforced by the deterministic guardrail layer and confirmed in the [AI Boundary Matrix](../requirements/ai-boundary-matrix.md).

This diagram will be extended in later weeks as the RAG pipeline (Week 3), tools (Week 4), and agent loop (Week 5) are implemented and evidenced with execution traces (`evidence/traces/`).
