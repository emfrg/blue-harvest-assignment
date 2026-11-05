# Mortgage pricing exceptions — specification

## Revision history

| Revision | Timestamp (Europe/Amsterdam) | Changes and reason | Author | Review |
|---|---|---|---|---|
| 0.1 | 2026-11-03 11:43:31 +01:00 | Initial requirements proposed for Sprint 1, Task 1. | Codex, for project-author review | Pending |
| 0.2 | 2026-11-03 12:16:50 +01:00 | Added sources and preparation method; separated assumptions from validation rules (FR-02); clarified decline and discount-limit decisions (section 4, AC-05); required retry keys (FR-16, AC-21); tightened concurrency scenarios (AC-17 to AC-19). | Codex, following project-author feedback | Pending final review |
| 1.0 | 2026-11-03 12:21:49 +01:00 | First agreed requirements baseline after project-author review. No requirement changes from revision 0.2. | Codex, recording project-author approval | Approved by project author |
| 1.1 | 2026-11-05 12:10:36 +01:00 | Clarified FR-03 and AC-03 for the final local deliverable: the health check and generated API documentation are accessible without user identity; mortgage operations require identity and role checks. This allows local health checks and API exploration without granting access to mortgage records or decisions. | Codex, recording project-author decision | Approved by project author |
| 1.2 | 2026-11-05 14:03:37 +01:00 | Added QR-03, QR-04 and QR-05 for consistent formatting, linting and static type checking to support maintainability. These requirements apply to the completed deliverable; tool selection and configuration remain for the technical plan. | Codex, recording project-author approval | Approved by project author |
| 1.3 | 2026-11-05 14:24:52 +01:00 | Added QR-06 to make formatting, linting and static type checks part of the local commit workflow through pre-commit hooks. Failed checks must block the commit, supporting QR-03, QR-04 and QR-05. | Codex, recording project-author approval | Approved by project author |

The timestamps for revisions 0.1 and 0.2 were recovered from the file's creation and last-modification times, respectively, before this timestamp correction.

For each requirements change, record the affected requirement IDs and the reason in the revision history.

## Sources and preparation

The source of the requested capabilities is *Blue Harvest Agentic SDLC Engineering Assignment*. Choices left open by the assignment brief are recorded below as assumptions or business decisions.

The structure is a manual adaptation of [GitHub Spec Kit's feature-specification template](https://github.com/github/spec-kit/blob/ba8363f8ab56b2da456a81299cfdbfee1ef7b871/templates/spec-template.md). It retains user scenarios, acceptance examples, numbered functional requirements, domain concepts, assumptions and success criteria. Explicit quality requirements, decision rationale and revision history are additions for this assignment. Spec Kit was used as reference material; its CLI and automated workflow were not used.

Codex assisted with drafting and checking the requirements against the assignment brief. The project author directed the scope, challenged proposals and requested revisions. For example, the author rejected an AI proposal to prohibit further requests after an approval. The resulting decision permits a new request while preserving the existing approved discount until a replacement is approved. The revision history records the review status of each draft.

## 1. Purpose and boundaries

This specification defines the requirements and business rules for mortgage pricing exception requests. It covers submitting requests, reviewing them, retrieving approved discounts and inspecting request history.

The scope includes a locally runnable HTTP API and predefined local users with role checks. Connecting to a company login system, configuring cloud deployment, and building a graphical interface are outside the scope.

A relationship manager submits a request. An authorised reviewer approves or declines it. The mortgage application process can retrieve the current approved discount. Internal users can inspect requests and their decisions.

The assignment deliverable includes:

- Request submission and validation.
- Approval and decline.
- Retrieval of requests, decisions and the current approved discount.
- Request and decision history.
- Protection against duplicate submissions caused by retries.
- Local setup and seed data sufficient to demonstrate these behaviours.

## 2. Domain concepts and assumptions

### Domain concepts

| Concept | Meaning |
|---|---|
| Mortgage application | An existing application identified by an application ID. |
| Request | A uniquely identified submission containing the application ID, requested discount, reason, submitter, submission time and current status. |
| Discount | A reduction in the mortgage interest rate, expressed in basis points. One basis point equals 0.01 percentage points. |
| Decision | The outcome, reviewer ID and decision time recorded for one request. |
| Current approved discount | The discount from the most recently approved request for an application. |
| Retry key | A caller-supplied identifier used to recognise a repeated submission. |

Submission and decision timestamps are assigned by the service and recorded in UTC.

### Local demonstration assumptions

The following assumptions address details left open by the assignment brief:

- The project includes sample mortgage applications and sample users for running the service locally. Relationship managers can create discount requests for those mortgage applications.
- Each user has one role: relationship manager or reviewer.
- The supplied user identity is trusted locally. The service still checks that the user exists and has the required role.
- System-to-system calls use a predefined local identity for the demonstration.

### Submission validation

- An application ID is required and must identify an existing mortgage application.
- A requested discount is required and must be a positive whole number of basis points.
- A reason is required and must contain at least one non-whitespace character.
- A retry key is required and must contain at least one non-whitespace character.

### Access rules

| Action | Permitted role |
|---|---|
| Submit a request | Relationship manager |
| Approve or decline | Reviewer |
| Read requests, history or the current approved discount | Either role |

For the final locally runnable deliverable, `GET /health` and the generated API documentation, including its schema, are accessible without a user identity. The health endpoint returns only `{"status": "ok"}` to confirm that the API responds. Viewing the documentation does not bypass identity and role checks when calling mortgage operations. This decision does not define access policy for a future production deployment.

## 3. User scenarios

All five scenarios are required for the assignment deliverable.

Acceptance scenarios in section 6 provide their independent checks. Prepared application and request records can supply the starting conditions.

| ID | User story | Independent check |
|---|---|---|
| US-01 | As a relationship manager, I want to submit a discount request so that a reviewer can consider it. | Submit against an existing application and inspect the resulting pending request. |
| US-02 | As a reviewer, I want to approve a pending request so that its exact discount is authorised for use. | Approve a prepared pending request and retrieve the approved discount. |
| US-03 | As a reviewer, I want to decline a pending request so that it does not authorise a discount. | Decline a prepared request and inspect the recorded outcome. |
| US-04 | As a relationship manager, I want to check a request’s status so that I know whether it is awaiting a decision. | Retrieve prepared pending, approved and declined requests. |
| US-05 | As a reviewer, I want to inspect an application’s request history so that I can trace how its current approved discount was reached. | Retrieve an application with several prepared requests and decisions. |

## 4. Business decisions

### Submitted details are frozen

The application ID, discount and reason cannot change after submission. A change requires a new request with a new request ID.

**Reason:** an approval must apply to exactly what was reviewed. This resolves the conflicting stakeholder input in favour of preserving the submitted request.

### One pending request per application

An application may have multiple historical requests, but only one pending request at a time.

To change a pending request, a reviewer must first decline it. The relationship manager can then submit another request.

**Reason:** this keeps one request under review and avoids introducing a separate withdrawal or replacement transition. The deliberate trade-off is that changing a pending request requires reviewer involvement.

In this scope, DECLINED means that the particular request is not authorised for use. It can represent a rejection of the requested terms or closure of an outdated request before a changed request is submitted. No decision reason is recorded, so the history does not distinguish these two causes. This is an explicit limitation of using one outcome for both cases.

### One final decision per request

The permitted transitions are:

```text
PENDING → APPROVED
PENDING → DECLINED
```

Approved and declined requests cannot receive another decision.

**Reason:** each request provides an unambiguous record of the reviewed submission and its outcome. Further consideration uses a new request.

Request records, decisions and successful-submission retry keys are retained for the lifetime of the local data. Earlier decisions remain available through the application's request history.

### A later approval replaces the current discount

A new request can be submitted after an approval.

- While the new request is pending, the existing approved discount remains current.
- Declining the new request leaves the existing approved discount current.
- Approving the new request makes its discount current.
- Discounts are never combined.
- Earlier approved requests retain their recorded status and decision in history.

**Reason:** requesting a change must not silently remove an existing approval. “Approved” describes a request’s outcome; “current” identifies which approval the application process should use.

### Discount limits

The assignment brief does not specify a product-specific maximum discount. No automatic product-specific upper limit is enforced in this scope. Reviewers assess whether a requested discount is acceptable.

**Reason:** choosing a numeric ceiling without a product rule would introduce an unsupported pricing policy. The applicable pricing rules would need to be agreed and enforced before production use.

## 5. Requirements

### Functional requirements

| ID | Required behaviour |
|---|---|
| FR-01 | An accepted submission must create one uniquely identified request with initial status PENDING. |
| FR-02 | A submission must be rejected if its application does not exist or its required data fails the validation rules in section 2. |
| FR-03 | Each mortgage operation must require a known user with a role permitted by the access table in section 2. |
| FR-04 | Attempts to change a submitted application ID, discount or reason must be rejected. |
| FR-05 | A new submission must be rejected if its application already has a pending request. |
| FR-06 | Approving a pending request must set its status to APPROVED and authorise exactly its submitted discount. |
| FR-07 | Declining a pending request must set its status to DECLINED. |
| FR-08 | A decision attempt on an approved or declined request must be rejected without changing its recorded decision. |
| FR-09 | Each accepted decision must record its outcome, reviewer ID and service-assigned decision time. |
| FR-10 | Reading a request must return its original submission details, current status and recorded decision, or explicitly indicate that no decision exists. |
| FR-11 | Reading an application’s history must return all its submitted requests and recorded decisions, including earlier approvals. |
| FR-12 | Reading the current approved discount must return the applicable request ID and discount according to section 4, or explicitly indicate that no approval exists. |
| FR-13 | A lookup using an unknown application or request ID must report that the identified record does not exist. |
| FR-14 | Repeating a successful submission with the same submitting user, retry key and submitted field values must return the original request ID and its current stored state without creating another request. |
| FR-15 | Reusing a successful submission’s retry key for the same user with different submitted field values must be rejected. |
| FR-16 | A submission without a retry key containing at least one non-whitespace character must be rejected. |

For retry matching, the submitted fields are the application ID, discount and reason.

Retry matching happens before the restriction on creating another pending request is applied. It continues to work after the original request has been decided.

Rejected submissions do not reserve retry keys. A different key represents a new submission and is subject to the normal creation rules.

### Quality requirements

These are requirements chosen for this assignment to support reliable operation.

| ID | Requirement | Verification approach |
|---|---|---|
| QR-01 | Successfully saved requests, decisions and retry-key associations must survive a normal service restart without changed values. | Restart the service and repeat retrieval and submission-retry checks. |
| QR-02 | Two concurrent submissions or decisions must preserve the single-pending-request, single-decision and retry guarantees. | Send competing calls and inspect the resulting records. |
| QR-03 | Python application and test code must follow a consistent formatting configuration. | The formatter’s check reports no required changes. |
| QR-04 | Python application and test code must have no unresolved findings under the agreed linting rules. | The linter passes using the recorded configuration. |
| QR-05 | Python code within the agreed annotation and checking scope must pass static type checking without reported type errors. | Review annotation coverage and run the selected type checker. |
| QR-06 | The documented local setup must enable formatting, linting and static type checks as pre-commit hooks. A failed check must block the commit. | Follow the documented setup in an isolated checkout. Attempt commits with a formatting, linting or type-checking failure, one at a time; each must be blocked. Confirm a commit succeeds when all checks pass. |

These requirements apply to the completed deliverable. The technical plan will define the tools, configurations, type-annotation coverage and type-checking strictness.

For this assignment, the service must run locally without paid services or private infrastructure. Setup instructions and seed data must make the acceptance scenarios reproducible.

## 6. Acceptance scenarios and behaviour checklist

| ID | Given / when | Expected result | Requirements |
|---|---|---|---|
| AC-01 | A permitted manager submits valid details for an existing application with no pending request. | One identified PENDING request contains the submitted details, submitter and submission time. | FR-01 |
| AC-02 | A submission contains an unknown application, missing required field, non-positive or fractional discount, or blank reason. Check each case separately. | The submission is rejected without creating a request. | FR-02 |
| AC-03 | An unknown user or a user with a disallowed role attempts a mortgage operation. | The operation is rejected without changing stored records. | FR-03 |
| AC-04 | Someone attempts to edit submitted details on a pending, approved or declined request. | The edit is rejected; the original details remain unchanged. | FR-04 |
| AC-05 | An application has a pending request and receives a distinct submission. | The second submission is rejected. After the first is declined, a valid new submission can succeed with a new request ID; the original request and its decline remain in history. | FR-05, FR-11 |
| AC-06 | A reviewer approves a pending request for 25 basis points. | It becomes APPROVED for exactly 25; the reviewer and decision time are recorded. | FR-06, FR-09 |
| AC-07 | A reviewer declines a pending request. | It becomes DECLINED; the reviewer and decision time are recorded. | FR-07, FR-09 |
| AC-08 | A decision is attempted on an already approved or declined request. | The attempt is rejected; the first decision remains unchanged. | FR-08 |
| AC-09 | A known request is retrieved in each possible status. | Its original details and correct status are returned; a decision is present only after approval or decline. | FR-10 |
| AC-10 | An application with several historical requests is inspected. | All requests and their recorded decisions remain available, including an earlier approval replaced by a later approval. | FR-11 |
| AC-11 | An existing application has no approved requests. | Retrieval explicitly reports no approved discount. | FR-12 |
| AC-12 | An application has an approved discount of 25 and a newer request for 40. Check the newer request as pending, declined and approved. | The current discount is respectively 25, 25 and 40, with the corresponding approved request ID. | FR-12 |
| AC-13 | An unknown request or application is retrieved. | The result reports a missing record, distinguishable from an existing application with no approval. | FR-13 |
| AC-14 | An identical successful submission is retried while its request is pending or after it has been decided. | The original request ID and current state are returned; no additional request is created. | FR-14 |
| AC-15 | The same user reuses a successful retry key with a changed application, discount or reason. Check each field separately. | The retry is rejected; the original request remains unchanged. | FR-15 |
| AC-16 | An invalid submission is rejected, then corrected and resubmitted with the same key. | The corrected submission is evaluated normally and can create a request. | FR-01, FR-02 |
| AC-17 | An existing application has no pending request. Two identical valid submissions from the same manager, using the same retry key, arrive concurrently. | Both resolve to the same request; exactly one request is created. | FR-14, QR-02 |
| AC-18 | An existing application has no pending request. Two otherwise valid submissions with different retry keys arrive concurrently for that application. | Exactly one submission creates a pending request; the other is rejected. | FR-05, QR-02 |
| AC-19 | Two authorised reviewers concurrently submit opposing decisions for the same pending request. | Exactly one decision succeeds and is recorded. If approval succeeds, the requested discount becomes current. If decline succeeds, the previous approved discount, or absence of an approval, is preserved. | FR-06, FR-07, FR-08, FR-09, FR-12, QR-02 |
| AC-20 | The service restarts after successful submissions and decisions. | Previously saved records remain retrievable; retry matching still returns the original request. | QR-01 |
| AC-21 | An otherwise valid submission has no retry key, an empty key or a key containing only whitespace. Check each case separately. | The submission is rejected without creating a request. | FR-16 |

## 7. Delivery success criteria

These criteria apply to the completed implementation:

- A seeded local workflow demonstrates submission, approval, retrieval of the exact approved discount and inspection of its history.
- Decline, replacement approval and retry scenarios produce the outcomes specified above.
- Each acceptance scenario has recorded verification evidence.
- Another engineer can reproduce the workflow using the supplied setup instructions and seed data without paid services or private infrastructure.
