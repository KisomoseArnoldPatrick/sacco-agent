Week 1 Progress Report — SACCO Member-Case Preparation Agent

Group: I Evening
Project: SACCO Member-Case Preparation 
Agent Week ending: 4 September 2026 (Week 1 of 8: 31 August – 4 September 2026)

1. Work Completed Against Weekly Objectives

Reviewed the eight recommended use cases and selected the SACCO Member-Case Preparation Agent as our project, confirming it fits the proposal rules (bounded, single workflow, synthetic/public data, no chatbot-only scope).

Drafted the Minimum Proposal Statement defining the user, AI use, deterministic boundaries, approved tools and prohibited actions.

Wrote the Project Charter covering problem, target user, pain point, AI value, scope, assumptions and constraints. (Owner: Kukiriza Sinai Jose)

Defined 10 testable user stories with acceptance criteria covering policy Q&A, schedule calculation, member lookup, case-file drafting, eligibility flagging, logging, and refusal of prohibited actions. (Owner: Hannington Wandera)

Built the AI Boundary Matrix specifying what the AI may do, what must remain deterministic, and what requires human approval for every function in the workflow. (Owner: Kisomose Arnold Patrick)

Produced the initial architecture/context diagram showing the agent orchestrator, RAG policy retrieval, deterministic guardrail layer, tools, and the human-review boundary. (Owner: Kukiriza Sinai Jose)

Created the GitHub repository with the recommended folder structure — (https://github.com/KisomoseArnoldPatrick/sacco-agent). (Owner: Kisomose Arnold Patrick)
Created the ClickUp project and Week 1 task list with owners and deadlines — (https://app.clickup.com/1200440000000513/chat/r/123tcvwccg1-255).

2. Key Engineering Decisions and Why They Were Made

Decided to separate all numeric computation (repayment schedules, eligibility thresholds) into deterministic tools rather than letting the language model calculate or infer figures, directly enforcing the "no credit scoring / no approval" safety boundary from the use case description.

Decided to ground all policy explanations in a retrieved document corpus (RAG) rather than model memory, so every answer is traceable to a specific policy clause — important given SACCO members rely on accurate procedural information.

Decided the agent's output is always a "draft case packet" that requires explicit human (credit committee) review, never an autonomous decision, to satisfy the safety boundary that no credit/financial decision may be made by the agent.

3. Failures / Challenges and Current Response

Sourcing a realistic-but-public SACCO policy handbook was difficult; the team decided to author a synthetic-but-representative policy document instead, modeled on typical Ugandan SACCO bylaws.

4. Links to Repository and Task Board Evidence

GitHub repository: (https://github.com/KisomoseArnoldPatrick/sacco-agent)
ClickUp Week 1 task list: (https://app.clickup.com/1200440000000513/chat/r/123tcvwccg1-255)


5. Individual Contribution Summary

Task ownership and status are tracked on the ClickUp Week 1 task list. Summary below.

Member	Tasks Completed (Week 1)
Kisomose Arnold Patrick	GitHub repo setup (folder structure, recommended layout); AI Boundary Matrix

Hannington Wandera	User stories and acceptance criteria (10 stories, incl. prohibited-action story US-08)

Kukiriza Sinai Jose	Project Charter; Initial architecture/context diagram

Mugisha Modern	Week 1 progress report (this document); ClickUp board setup and task tracking

6. Plan for Next Week (Week 2)
Select and document the foundation model to be used (capability, cost, latency, privacy, access considerations).
Integrate the model into the application and produce a working baseline model interaction.
Write Prompt Specification v1.0 (role, task, context, constraints, output format, failure behaviour) for the policy-explanation and case-drafting prompts.
Create at least 10 test cases with expected vs. actual behaviour, and version at least two meaningful prompt iterations.
Begin assembling the SACCO policy document corpus that will be used for RAG in Week 3.