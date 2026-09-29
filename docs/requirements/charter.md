# PROJECT CHARTER
## SACCO Loan Application Preparation Agent

### 1. Project Overview

The project proposes a **SACCO Loan Application Preparation Agent**, an AI-native system that helps
SACCO members prepare loan applications and presents structured cases for review by SACCO
relationship officers.

The agent will capture a member's preferred loan amount, repayment period and payment frequency,
review relevant synthetic member and transaction information, identify matching SACCO loan
products, explain interest rates and repayment structures, identify required documents, check
submitted forms and review uploaded documents for completeness and consistency, request
clarification where necessary, and generate a case summary for staff review.

The agent will not approve or reject loans, determine creditworthiness, disburse funds, modify
accounts, or perform real financial transactions.

---

## 2. Problem

Preparing a SACCO loan application may require members to understand multiple loan products,
interest rates, repayment options, eligibility requirements and supporting documents.

Relevant information may also be spread across policy documents, product descriptions, member
records and submitted documents. This can make application preparation slow and may require
repeated communication between members and relationship officers.

The proposed system brings these activities into one guided workflow that prepares a more complete
and organized case before human review.

---

## 3. Target Users

The primary user is the **SACCO member** seeking to prepare a loan application. The member provides
preferred borrowing terms, views matching loan products, understands requirements, submits
information through structured forms, uploads supporting documents and responds to clarification
questions.

The secondary user is the **SACCO relationship officer**, who reviews the structured case prepared
by the agent, can review the audit trail of the agent's actions, and decides how the application
should proceed.

The AI supports both users but does not make financial decisions.

---

## 4. Current Pain Points

Members may struggle to identify the loan product that matches their needs or understand product
requirements and repayment structures.

Incomplete or unclear documentation can also delay the process, while relationship officers may
spend significant time checking missing information and organizing details from different sources.

The agent is intended to reduce these preparation challenges without replacing human judgment.

---

## 5. AI Value

AI adds value through natural-language interaction, retrieval of SACCO policies, interpretation of
requirements, review of uploaded documents (identifying document types and extracting key
details), and clarification.

Using Retrieval-Augmented Generation, the agent can answer from approved SACCO policy and product
documents rather than relying only on model knowledge.

The agent can also coordinate several steps: understand the request, retrieve information, call
approved tools, check whether requirements are satisfied, ask for missing information and stop
when the case is ready for review.

Deterministic software will handle financial calculations and rule-based validation, including
form validation, product matching, requirements checking and comparison of extracted document
details with case data.

---

## 6. Project Scope

The system will support one end-to-end workflow: **preparing a SACCO loan application case for
human review**.

The workflow will include:

- capturing loan amount, repayment period and frequency;
- starting the case from a member ID and retrieving relevant synthetic member and transaction information;
- retrieving SACCO loan products and policies;
- matching requested terms with available products;
- calculating illustrative repayment schedules;
- generating a requirements checklist;
- receiving structured form submissions and uploaded documents (text-based PDF and images);
- reviewing forms and documents for completeness and consistency with case data;
- identifying missing or unclear information;
- asking clarification questions;
- preparing a structured case summary;
- recording an audit trail of agent actions; and
- handing the case over to a relationship officer.

The system will use a small controlled corpus and synthetic data to remain testable and explainable.

---

## 7. Assumptions

The project assumes that SACCO loan products can be represented in structured or semi-structured
documents containing interest rates, loan limits, repayment periods and requirements.

All member records, transactions, form submissions and uploaded documents will be synthetic and
created for testing. Uploaded documents will be text-based PDFs and images.

The member starts a case by entering a member ID. The prototype has no real authentication, and
the system uses only that member's synthetic record.

Financial calculations will be performed using deterministic formulas, while document review will
focus on completeness and consistency rather than legal authenticity.

Final loan decisions will remain the responsibility of authorized SACCO officers.

---

## 8. Constraints and Boundaries

The agent will not:

- approve or reject loans;
- assign credit scores;
- determine creditworthiness;
- recommend final lending decisions;
- disburse money;
- change account balances;
- modify official member records;
- conduct real financial transactions; or
- claim that any document or submitted information is authentic or verified.

Only public, synthetic, team-created or otherwise authorized data will be used. No real personal
data will be used or sent to external AI services.

The eight-week project period also requires the team to focus on one complete workflow rather than
developing a full SACCO management system.

---

## 9. Expected Outcome

A working AI-native system that can take a member from an initial loan request to a structured case
ready for human review.

Success will be measured by the system's ability to retrieve relevant SACCO information, match loan
products to the requested terms, calculate illustrative repayment schedules, identify requirements,
review submitted forms and documents, manage missing information, maintain case state, record an
audit trail and generate a clear case summary.

The project therefore demonstrates how AI can improve loan application preparation while keeping
consequential financial decisions under human control.