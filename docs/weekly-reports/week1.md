# Weekly Progress Report — Week 1

**Group / project:** I Evening — SACCO Loan Application Preparation Agent
**Week ending:** 4 September 2026 (Week 1 of 8: 31 August – 4 September 2026)

## 1. Work completed against the weekly objectives

Weekly focus (from the brief): Problem framing and AI-native requirements. Choose a feasible
problem, define users and success criteria, justify AI use, and set the boundaries of the agent.

| Deliverable | Status (Done / Partial / Not started) |
|---|---|
| Use case selection: reviewed the eight recommended use cases and selected the SACCO agent, confirming it fits the proposal rules (bounded, single workflow, synthetic/public data, not chatbot-only) | Done |
| Minimum Proposal Statement (user, AI use, deterministic boundaries, approved tools, prohibited actions) | Done |
| Project Charter (problem, target user, pain point, AI value, scope, assumptions, constraints). | Done |
| User stories and acceptance criteria (11 stories covering loan preference capture, member record retrieval, transaction summary, loan product matching, repayment illustration, requirements checklist, form and document submission and review, clarification of missing information, case summary, human review and handover, and audit trail) | Done |
| AI Boundary Matrix (what AI may do, what stays deterministic, what needs human approval, for every function in the workflow). | Done |
| Initial architecture / context diagram (agent orchestrator, RAG policy retrieval, deterministic guardrail layer, tools, human-review boundary).| Done |
| GitHub repository with the recommended folder structure.| Done |
| ClickUp project and Week 1 task list with owners and deadlines | Done |
| Week 1 progress report (this document) | Done |


## 2. Key engineering decisions and why

- **Decision:** Separate all numeric computation (repayment schedules, eligibility thresholds)
  into deterministic tools rather than letting the language model calculate or infer figures.
  **Why:** Directly enforces the "no credit scoring / no approval" safety boundary from the use
  case description.
- **Decision:** Ground all policy explanations in a retrieved document corpus (RAG) rather than
  model memory. **Why:** Every answer is traceable to a specific policy clause, which matters
  because SACCO members rely on accurate procedural information.
- **Decision:** The agent's output is always a "draft case packet" that requires explicit human
  (credit committee) review, never an autonomous decision. **Why:** Satisfies the safety
  boundary that no credit or financial decision may be made by the agent.

## 3. Failures, challenges and current response

- **Issue:** Sourcing a realistic-but-public SACCO policy handbook was difficult.
  **Cause:**
  **Response / status:** The team decided to author a synthetic-but-representative policy
  document, modelled on typical Ugandan SACCO bylaws.

## 4. Links

- GitHub: https://github.com/KisomoseArnoldPatrick/sacco-agent
- ClickUp: https://app.clickup.com/1200440000000513/v/li/1200440000003322 — links to this week's tasks:
- AI Engineering Log entries this week:

## 5. Individual contribution summary

| Member | Role | Task(s) owned this week | Evidence |
|---|---|---|---|
| Kisomose Arnold Patrick | | GitHub repo setup (folder structure, recommended layout); AI Boundary Matrix; ClickUp board setup and task tracking | https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/docs/requirements/ai-boundary-matrix.md|
| Hannington Wandera | | User stories and acceptance criteria | https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/docs/requirements/user-stories.md|
| Kukiriza Sinai Jose | | Project Charter | https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/docs/requirements/charter.md|
| Mugisha Modern | | Week 1 progress report;| https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/docs/weekly-reports/week1.md|
| Kabalebe Joshua | | initial architecture / context diagram | https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/docs/architecture/architecture-overview.md|

## 6. Plan for next week

Next week's focus (from the brief): Foundation-model engineering and prompting (Week 2, 7–11 Sept 2026).

Planned tasks:
- Select and document the foundation model (capability, cost, latency, privacy, access considerations)
- Integrate the model into the application and produce a working baseline model interaction
- Write Prompt Specification v1.0 (role, task, context, constraints, output format, failure behaviour) for the policy-explanation and case-drafting prompts
- Create at least 10 test cases with expected vs actual behaviour, and version at least two meaningful prompt iterations
- Begin assembling the SACCO policy document corpus for RAG in Week 3