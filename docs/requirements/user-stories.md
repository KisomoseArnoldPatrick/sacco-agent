# SACCO LOAN APPLICATION PREPARATION AGENT  
## User Stories and Acceptance Criteria

### Primary actor
**SACCO Member**  
The person seeking a suitable SACCO loan product and preparing a loan application.

### Secondary actor
**SACCO Relationship Officer**  
The person who reviews the prepared loan application case.

### System
**SACCO Loan Application Preparation Agent**

The AI supports the member and relationship officer in preparing a loan application. It does not approve or reject loans, determine creditworthiness, disburse funds, or make financial decisions.

---

## SACCO Member

### US01: Loan Preference Capture

**As a SACCO member, I want to provide my desired loan amount, repayment period and payment frequency so that the system can understand the type of loan arrangement I am looking for.**

#### Acceptance criteria

- The system allows the member to provide a desired loan amount.
- The system allows the member to specify the desired loan repayment period.
- The system allows the member to select a repayment frequency from supported options such as daily, weekly, monthly, quarterly, bi-annually or annually.
- The system validates that the loan amount and repayment period are valid numerical values.
- The system rejects unsupported repayment frequencies.
- The system requests clarification when required loan-preference information is missing or ambiguous.
- The captured preferences are retained as part of the active loan application case.

---

### US02: Member Financial Information Retrieval

**As a SACCO member, I want the system to retrieve relevant information from my SACCO record so that available member information can be considered when preparing my loan application.**

#### Acceptance criteria

- The system retrieves the member's synthetic SACCO record using a valid member identifier.
- The system retrieves only information relevant to preparing the loan application.
- Relevant information may include savings information, existing loan obligations, membership duration and permitted transaction information.
- Invalid or non-existent member identifiers produce an appropriate error.
- The system does not modify the member's SACCO record.
- The system does not use the retrieved information to autonomously determine creditworthiness or approve a loan.
- The source of retrieved member information is identifiable.

---

### US03: Transaction Information Summary

**As a SACCO member, I want the system to summarize relevant information from my transaction history so that factual financial information required during loan preparation can be presented clearly.**

#### Acceptance criteria

- The system retrieves permitted synthetic transaction records associated with the member.
- Transaction calculations are performed using deterministic software logic.
- The system may calculate factual indicators such as savings balances, transaction totals, average deposits or existing loan repayments where required by SACCO policy.
- The system clearly distinguishes calculated facts from AI-generated explanations.
- Missing or incomplete transaction data is identified.
- The system does not generate an independent credit score from the member's transactions.
- The system does not label the member as creditworthy or non-creditworthy.

---

### US04: Loan Product Matching

**As a SACCO member, I want the system to compare my requested loan terms against available SACCO loan products so that I can understand which products support the terms I am seeking.**

#### Acceptance criteria

- The system retrieves available loan products from the approved SACCO knowledge base.
- The system considers the member's requested loan amount, repayment period and payment frequency.
- The system compares the requested terms against documented product conditions.
- The system identifies loan products whose documented terms support the member's request.
- The system explains why each displayed product matches the requested terms.
- Products that do not support the requested terms are not presented as suitable matches.
- If no product matches the requested terms, the system informs the member and may explain which requested conditions caused the mismatch.
- The system does not claim that a matching product has been approved for the member.

---

### US05: Loan Product Information and Repayment Illustration

**As a SACCO member, I want to see the interest rates, repayment structure and estimated instalments for matching loan products so that I can compare the available options.**

#### Acceptance criteria

- The system retrieves the applicable interest rate from the approved loan-product information.
- The system identifies the documented interest calculation method where available.
- Repayment calculations are performed using deterministic financial logic.
- The system calculates the illustrative instalment according to the selected payment frequency.
- The system presents the requested loan amount, repayment period, payment frequency, applicable interest rate and illustrative instalment.
- The system clearly labels all repayment calculations as illustrative.
- Where the policy does not provide enough information to calculate a repayment schedule reliably, the system states this instead of inventing values.
- The displayed calculation does not constitute a loan offer or approval.

---

### US06: Loan Requirements Checklist

**As a SACCO member, I want to know the requirements for a selected loan product so that I can prepare everything required for my application.**

#### Acceptance criteria

- The system retrieves requirements from the approved policy or loan-product documentation.
- Requirements are presented as a structured checklist.
- The checklist may include documents, member information, guarantor information and other requirements where supported by SACCO policy.
- The system distinguishes requirements already satisfied by available information from those still outstanding.
- Each significant requirement can be traced to an approved source.
- Unsupported requirements are not invented.
- If a requirement is unclear from the available policy, the system identifies it as requiring staff clarification.

---

### US07: Supporting Document Submission and Audit

**As a SACCO member, I want to submit the documents required for my selected loan product so that the system can check whether my application documentation is complete.**

#### Acceptance criteria

- The system allows the member to submit supported document types.
- The system associates submitted documents with the active loan application case.
- The system compares submitted documents against the requirements checklist for the selected loan product.
- Each document is classified as present, missing, unclear or requiring human verification.
- The system identifies missing required documents.
- The system identifies unreadable, incomplete or unsupported documents.
- The system does not claim that a document is authentic unless authenticity has been verified by an authorized process.
- The system does not automatically reject an application because of a missing or unclear document.

---

### US08: Clarification of Missing or Conflicting Information

**As a SACCO member, I want the system to ask me for clarification when submitted information is missing, inconsistent or unclear so that I can improve the completeness of my loan application before staff review.**

#### Acceptance criteria

- The system identifies missing information required by the applicable loan-product requirements.
- The system identifies inconsistencies between submitted information and available case data.
- The system asks specific clarification questions relating to the identified issue.
- The system records the member's clarification as part of the active case.
- After clarification is provided, the system re-evaluates the affected requirement.
- The system does not repeatedly request information that has already been satisfactorily provided.
- Information that cannot be resolved by the member is marked for human review.
- The clarification process stops when all requirements are either satisfied, missing or marked for staff verification.

---

## SACCO Relationship Officer

### US09: Structured Loan Application Case Summary

**As a SACCO relationship officer, I want the system to prepare a structured summary of the member's loan application so that I can review the case efficiently.**

#### Acceptance criteria

- The system includes the member's requested loan amount, repayment period and payment frequency.
- The system identifies the selected or matching SACCO loan product.
- The system includes the documented interest rate and illustrative repayment information where applicable.
- The system summarizes relevant permitted member and transaction information.
- The system lists applicable loan-product requirements.
- The system shows which requirements have been satisfied, which are missing and which require human verification.
- The system lists the supporting documents submitted by the member.
- The system includes relevant clarifications supplied by the member.
- The summary clearly distinguishes factual data, deterministic calculations and AI-generated explanations.
- The summary does not contain a loan approval or rejection recommendation.

---

### US10: Human Review and Handover

**As a SACCO relationship officer, I want to review the prepared loan application case before any further processing so that consequential financial decisions remain under human control.**

#### Acceptance criteria

- The prepared application case is presented to an authorized relationship officer.
- The officer can review the member information, loan terms, repayment illustration, documents, requirements and outstanding issues.
- The system clearly identifies information that requires human verification.
- AI-generated explanations or summaries are identifiable.
- The relationship officer remains responsible for deciding whether and how the case proceeds.
- The system does not automatically approve or reject the loan.
- The system does not disburse funds or modify the member's account.
- The system records that the application-preparation workflow has reached human handover.
- The agent stops its autonomous preparation workflow once the case has been handed over for staff review.
