# API contract and lifecycle

This document describes the implemented HTTP contract for `SPEC.md` revision 1.4.
The specification defines required behaviour; this document records fields,
routes, validation, state changes and transaction handling.
The executable schemas are in `app/schemas.py` and appear in `/docs` and
`/openapi.json`.

## Revision history

| Revision | Timestamp (Europe/Amsterdam) | Change                                                                                                                                                                                                                                                                                                       |
| -------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 0.1      | 2026-11-05 17:08:48 +01:00   | Initial implemented contract, ready for author review. Business requirements remain those in specification revision 1.3.                                                                                                                                                                                     |
| 0.2      | 2026-11-06 08:37:22 +01:00   | Author-approved response change: omit `retry_key` from request responses so they focus on submitted details and decisions. The key remains required on submission and stored for duplicate protection. Clarify submission descriptions and session-factory access. Specification revision 1.3 still applies. |
| 0.3      | 2026-11-07 17:02:58 +01:00   | Document SQLite concurrency limits and what PostgreSQL would change. No API behaviour changes.                                                                                                                                                                                                               |
| 0.4      | 2026-11-08 18:17:46 +01:00   | Remove internal planning references from the introduction and verification section. No API behaviour changes.                                                                                                                                                                                                |
| 0.5      | 2026-11-08 18:25:45 +01:00   | Align the overlapping-call and busy-database descriptions with specification revision 1.4, QR-02, AC-17 to AC-19, and AC-22. Link AC-22 to the existing busy-database test. No API behaviour changes.                                                                                                        |

## Data model and audit history

| Table                   | Fields and relationships                                                                                            |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `mortgage_applications` | `id`: integer primary key identifying a predefined application.                                                     |
| `users`                 | `id`: integer primary key; required `role`: `RELATIONSHIP_MANAGER` or `REVIEWER`.                                   |
| `requests`              | Fields below. `application_id` references a mortgage application; `submitted_by` and `reviewer_id` reference users. |

Each request retains its original submission and its one final decision.
Submission and decision timestamps are assigned by the API in UTC, stored and
returned as ISO 8601 text with microseconds and a `+00:00` offset.

| Stored request field | Type                     | Rule                                                   |
| -------------------- | ------------------------ | ------------------------------------------------------ |
| `id`                 | Integer                  | Database-generated primary key.                        |
| `application_id`     | Integer                  | Existing mortgage application; cannot change.          |
| `discount_bps`       | Integer                  | Positive whole number; cannot change.                  |
| `reason`             | String                   | Non-blank submission reason; cannot change.            |
| `submitted_by`       | Integer                  | Checked relationship-manager identity; cannot change.  |
| `submitted_at`       | Timestamp string         | Submission time; cannot change.                        |
| `status`             | String                   | `PENDING`, `APPROVED` or `DECLINED`.                   |
| `retry_key`          | String                   | Non-blank submission key; cannot change.               |
| `reviewer_id`        | Integer or null          | Null while pending; checked reviewer after a decision. |
| `decided_at`         | Timestamp string or null | Null while pending; assigned with the decision.        |

`app/models.py` defines foreign keys, allowed-role/status checks, a positive
integer discount check, and a check requiring decision fields to match status.
A unique constraint on `(submitted_by, retry_key)` prevents duplicate records
for one user's submission key. A partial unique index on `application_id` for
`PENDING` rows permits only one pending request per application.

History returns every retained request for the application, ordered by request
ID. Each row supplies the original submission, submitter and time, plus the
outcome, reviewer and decision time when present. Previous approvals and declines
remain visible after later submissions. A separate event table is unnecessary
for the agreed single-decision lifecycle. This covers FR-09 to FR-11.

There is no reviewer justification or assignment history in the current scope.
The audit record is protected through the API; it is not a tamper-proof log
against someone directly editing the local SQLite file.

## Allowed transitions and changes

| Starting state           | Action                                           | Result                                                 |
| ------------------------ | ------------------------------------------------ | ------------------------------------------------------ |
| No request               | Submit valid details                             | New request ID, `PENDING`.                             |
| `PENDING`                | Approve                                          | `APPROVED`, reviewer and decision time saved together. |
| `PENDING`                | Decline                                          | `DECLINED`, reviewer and decision time saved together. |
| `APPROVED` or `DECLINED` | Any further decision, including the same outcome | `409`; the first decision remains unchanged.           |
| Any state                | PUT, PATCH or DELETE a request                   | `405`; no edit or delete operation exists.             |

Changed application, discount or reason requires a new submission with a new
key and request ID. If the application has a pending request, a reviewer must
decline it first. Extra fields in a decision body cannot alter submitted details
and are rejected with `422`. These rules implement FR-04 to FR-08.

A previous approval remains current while a later request is pending or declined.
A later approval replaces the current discount; discounts are never combined.
Select the highest request ID among the application's approved requests: with
only one pending request allowed, it must be decided before the next request
can be created. This gives approval order without relying on wall-clock order.
Earlier approved rows retain their status in history (FR-12).

## Endpoints and identity

Every mortgage operation requires `X-User-Id`, identifying a predefined local
user. This identity is trusted locally, with existence and role checks. It is
not production authentication. Health, interactive docs and the generated schema
remain public, as specified in FR-03.

| Method | Path                                               | Role                 | Successful response                                     |
| ------ | -------------------------------------------------- | -------------------- | ------------------------------------------------------- |
| POST   | `/requests`                                        | Relationship manager | `201` Request created; `200` existing Request returned. |
| GET    | `/requests/{request_id}`                           | Either role          | `200` Request.                                          |
| POST   | `/requests/{request_id}/decision`                  | Reviewer             | `200` Request after the decision.                       |
| GET    | `/applications/{application_id}/requests`          | Either role          | `200` History.                                          |
| GET    | `/applications/{application_id}/approved-discount` | Either role          | `200` CurrentApproval.                                  |
| GET    | `/health`                                          | Public               | `200` with `{"status":"ok"}`.                           |

## Request and response schemas

POST bodies use `Content-Type: application/json`.

A relationship manager submits an application ID, requested discount and reason.
The request starts as `PENDING`. The body requires exactly these fields:

```json
{ "application_id": 1, "discount_bps": 25, "reason": "Competitive offer" }
```

Submission also requires the `Idempotency-Key` header, described under
[submission retries](#submission-retries-and-transactions).

Decision requires exactly one field; its value is `APPROVED` or `DECLINED`:

```json
{ "outcome": "APPROVED" }
```

Every Request response contains the nine fields shown below. Decision fields are
null while pending. The stored `retry_key` is used for duplicate protection and
is not included in response bodies.

```json
{
	"id": 1,
	"application_id": 1,
	"discount_bps": 25,
	"reason": "Competitive offer",
	"submitted_by": 1,
	"submitted_at": "2026-11-05T16:00:00.000000+00:00",
	"status": "PENDING",
	"reviewer_id": null,
	"decided_at": null
}
```

History has `application_id` (integer) and `requests` (array of Request objects).
An existing application without requests returns
`{"application_id":1,"requests":[]}`.

CurrentApproval has `application_id` (integer) and `approved_discount` (object
or null). The object contains `request_id` and `discount_bps`, both integers:

```json
{
	"application_id": 1,
	"approved_discount": { "request_id": 1, "discount_bps": 25 }
}
```

An existing application without an approval returns
`{"application_id":1,"approved_discount":null}`. An unknown application is `404`.

## Validation and errors

JSON application IDs and discounts must be positive integers; booleans, decimal
numbers and numeric strings are rejected. Path/header IDs must parse as positive
integers. Integer inputs must fit SQLite's signed 64-bit storage, up to
`9223372036854775807`; this is a technical bound, not a product pricing ceiling.

Reason and submission key must contain a non-whitespace character. Their values
are retained exactly, without trimming or changing case. Additional body fields
are rejected, including caller-supplied reviewer IDs or timestamps.

| HTTP status | Meaning                                                                                                   |
| ----------- | --------------------------------------------------------------------------------------------------------- |
| `403`       | Supplied user is unknown or their role cannot perform the operation.                                      |
| `404`       | Application or request does not exist. Permissions are checked first.                                     |
| `405`       | Method is unsupported, including editing/deleting a request.                                              |
| `409`       | Another request is pending, a key has different submitted details, or a request is already decided.       |
| `422`       | Missing/malformed required header, invalid field, missing/extra field, invalid outcome or malformed JSON. |
| `503`       | SQLite remains busy after three transaction attempts.                                                     |
| `500`       | Unexpected internal failure; it is not converted into a business conflict.                                |

Expected application errors return `{"detail":"message"}`, for example
`{"detail":"Request already decided"}`. Validation errors use FastAPI's
`{"detail":[...]}` format, with location, type and message for each error.
Unexpected failures return a generic server error; raw database errors are not
included in API responses.

## Submission retries and transactions

The caller chooses a new `Idempotency-Key` for each new submission. When resending
the same submission after a timeout, it sends the same key and details.

Check `(submitted_by, retry_key)` before checking for a pending request. If found,
compare application ID, discount and reason exactly. A match returns the original
request's current state (`200`), including after a decision or later submission.
Different details return `409`. Failed submissions reserve no key. A successful
key remains associated with its original request for the lifetime of local data
(FR-14 to FR-16).

Every database operation uses its own session and transaction. Successful writes
commit before a success response; exceptions roll back. Submission saves its
key and request together. A decision uses one conditional UPDATE matching the
request ID and `PENDING`, setting status, reviewer and time together.

`get_session_factory` in `app/api.py` retrieves the application's session factory.
`run_operation` in `app/operations.py` opens each session and transaction with
`with sessions.begin() as session:`.

Uniqueness conflicts are re-evaluated in a fresh transaction. SQLite busy errors
retry the complete transaction, with a maximum of three attempts and waits of
50 ms and 100 ms. The connection uses SQLite's five-second lock timeout.
Unrelated database errors are not retried or treated as business conflicts.

The outcomes below assume database access allows the operations to finish within
the retry limit, as stated in SPEC's AC-17 to AC-19. If SQLite remains busy after
three attempts, the affected call returns `503` without saving partial changes
(QR-02, AC-22). Another overlapping call may have succeeded. Resending a submission
with its original key and details returns the existing request if it was saved.

| Competing operations                          | Required result                               |
| --------------------------------------------- | --------------------------------------------- |
| Identical submissions, same user and key      | One `201`, one `200`, one stored request.     |
| Different submission keys for one application | One `201`, one `409`, one pending request.    |
| Two decisions on one pending request          | One `200`, one `409`, one preserved decision. |

### SQLite concurrency limits and PostgreSQL

SQLite allows only one write transaction at a time, even when the changes concern
different mortgage applications. Adding API workers does not remove this limit.
See [SQLite's isolation documentation](https://www.sqlite.org/isolation.html).

The existing tests cover two overlapping calls and a held write lock.
Performance under sustained traffic has not been measured.

PostgreSQL can handle writes to different rows concurrently. Updates to the same
row can still wait for each other, and deadlocks can require a transaction retry.
See [PostgreSQL's locking documentation](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-ROWS).

The unique submission key, single pending request rule and conditional `PENDING`
update would still be needed. Using PostgreSQL would require adapting the
SQLite-specific connection settings, constraint and index definitions, and error
handling, then running the transaction and concurrency tests against PostgreSQL.
PostgreSQL has not been tested in this project.

## Implementation and verification

| Area                                                     | Implementation and checks                                                                                            |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Fields, relationships, constraints and auditable history | `app/models.py`; history operation and response schema; model tests and API history/restart tests.                   |
| Allowed transitions and treatment of edits/revisions     | Lifecycle table above; `decide_request` in `app/operations.py`; final-decision, rejected-edit and replacement tests. |
| Endpoints, schemas, validation and errors                | `app/api.py`, `app/schemas.py`, `/docs`, `/openapi.json`; API validation, access, retry and error tests.             |

`tests/test_api.py` covers AC-01 to AC-16, AC-20 and AC-21.
`tests/test_api_concurrency.py` covers AC-17 to AC-19 by holding both calls after
their first database read, then allowing them to compete. Its
`test_busy_database_returns_503_without_reserving_submission_key` checks AC-22:
a held SQLite write lock causes `503` without saving a submission or reserving
its key; resending succeeds after the lock is released. Test files use isolated
SQLite databases; the author's manual API review is separate.

Framework references: [FastAPI response models](https://fastapi.tiangolo.com/tutorial/response-model/),
[FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/), and
[SQLAlchemy conditional updates](https://docs.sqlalchemy.org/en/21/orm/queryguide/dml.html#orm-update-and-delete-with-custom-where-criteria).
