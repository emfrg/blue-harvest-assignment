# API reference

This document describes how to call the API, what it returns and how requests
move through review. [SPEC.md](SPEC.md) defines the agreed requirements and
business decisions. See [README.md](README.md) for setup and a complete walkthrough.

The default local address is `http://127.0.0.1:8000`. FastAPI generates the
OpenAPI description at `/openapi.json` and the interactive documentation at
`/docs` from the routes and schemas.

## Access and headers

For mortgage operations, send a sample user's ID in `X-User-Id`. The API checks
that the user exists and that their role allows the action. There is no login
or password check: anyone calling the local API can send any sample user's ID.

| Header | When to send it | Value |
|---|---|---|
| `X-User-Id` | Every mortgage operation and `GET /demo/applications`. | An existing user ID, such as `1`. |
| `Idempotency-Key` | `POST /requests` only. | A non-blank string chosen by the caller, such as `api-25-1`. Use a new key for each new submission. |
| `Content-Type` | Both POST endpoints. | `application/json` |

Setup creates relationship managers `1` and `2`, and reviewers `3` and `4`.
Managers can submit requests. Reviewers can approve or decline them. Both roles
can read requests, application history and approved discounts.

`GET /health`, `GET /demo/users`, `/docs` and `/openapi.json` do not require a
user ID. Missing or malformed required headers return `422`. An unknown user
or a user with the wrong role returns `403`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/requests` | Submit a discount request. |
| GET | `/requests/{request_id}` | Read a request and its decision. |
| POST | `/requests/{request_id}/decision` | Approve or decline a pending request. |
| GET | `/applications/{application_id}/requests` | Read an application's request history. |
| GET | `/applications/{application_id}/approved-discount` | Read the application's current approved discount. |
| GET | `/health` | Check that the API responds. |
| GET | `/demo/users` | List users for the frontend's user selector. |
| GET | `/demo/applications` | List applications for the frontend's application selector. |

All successful responses below are JSON. For error bodies and validation rules,
see [Validation and errors](#validation-and-errors). An unexpected internal
failure can return `500`.

### POST /requests

Submit a discount request for a mortgage application.

**Access:** Relationship manager.

**Input:** `X-User-Id`, `Idempotency-Key` and a JSON body containing exactly
`application_id`, `discount_bps` and `reason`. For example, with user `1` and
key `api-25-1`:

```json
{
  "application_id": 1,
  "discount_bps": 25,
  "reason": "Competitive offer"
}
```

**Success:** `201` with a new request in `PENDING` status. Repeating the same
submission with the same user and key returns `200` with the existing request's
current state. Both responses use the [request fields](#request-response-fields).

Example `201` response; IDs and timestamps are assigned by the API:

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

**Errors:** `403` for an unknown user or wrong role; `404` for an unknown
application; `409` if another request is pending or the key was used with
different details; `422` for invalid input; `503` if the database stays busy.

### GET /requests/{request_id}

Read a request's submitted details, current status and decision.

**Access:** Either role.

**Input:** `X-User-Id` and the request ID in the path. No request body.

**Success:** `200` with the [request fields](#request-response-fields).
For example, `GET /requests/1` with user `1`, immediately after the submission
above, returns the same pending request shown above. After approval or decline,
it returns the updated status, reviewer and decision time.

**Errors:** `403` for an unknown user; `404` for an unknown request; `422` for
invalid input; `503` if the database stays busy.

### POST /requests/{request_id}/decision

Approve or decline a pending request.

**Access:** Reviewer.

**Input:** `X-User-Id`, the request ID in the path and a JSON body containing
only `outcome`. Its value must be `APPROVED` or `DECLINED`.
For example, send this to `/requests/1/decision` as user `3`:

```json
{"outcome": "APPROVED"}
```

**Success:** `200` with the [request fields](#request-response-fields), including
the decision. For the request above, an approval response could be:

```json
{
  "id": 1,
  "application_id": 1,
  "discount_bps": 25,
  "reason": "Competitive offer",
  "submitted_by": 1,
  "submitted_at": "2026-11-05T16:00:00.000000+00:00",
  "status": "APPROVED",
  "reviewer_id": 3,
  "decided_at": "2026-11-05T16:05:00.000000+00:00"
}
```

The API records the reviewer from `X-User-Id` and assigns the decision time.
To decline instead, send `{"outcome": "DECLINED"}` while the request is pending.

**Errors:** `403` for an unknown user or wrong role; `404` for an unknown
request; `409` if the request already has a decision; `422` for invalid input;
`503` if the database stays busy.

### GET /applications/{application_id}/requests

Read all requests and decisions for one mortgage application, ordered by
request ID from lowest to highest.

**Access:** Either role.

**Input:** `X-User-Id` and the application ID in the path. No request body.

**Success:** `200` with `application_id` and a `requests` list. Each list item
contains the [request fields](#request-response-fields), including any decision.
For example, `/applications/2/requests` returns the following if application `2`
exists but has no requests:

```json
{"application_id": 2, "requests": []}
```

**Errors:** `403` for an unknown user; `404` for an unknown application; `422`
for invalid input; `503` if the database stays busy.

### GET /applications/{application_id}/approved-discount

Read the discount currently approved for use on a mortgage application.

**Access:** Either role.

**Input:** `X-User-Id` and the application ID in the path. No request body.

**Success:** `200` with `application_id` and `approved_discount`.
For example, after approving request `1` for 25 basis points:

```json
{
  "application_id": 1,
  "approved_discount": {"request_id": 1, "discount_bps": 25}
}
```

For an existing application without an approved request, `approved_discount`
is `null`:

```json
{"application_id": 2, "approved_discount": null}
```

**Errors:** `403` for an unknown user; `404` for an unknown application; `422`
for invalid input; `503` if the database stays busy.

### GET /health

Check that the API responds.

**Access:** No user ID required.

**Input:** No parameters or request body.

**Success:** `200` with:

```json
{"status": "ok"}
```

**Errors:** No database or role checks run here. This endpoint does not check
whether the database has been set up.

### GET /demo/users

List the stored users so a frontend can offer them in its user selector.
This endpoint is an optional addition for the frontend; the mortgage request
workflow does not require it.

**Access:** No user ID required.

**Input:** No parameters or request body.

**Success:** `200` with a list of user IDs and roles, ordered by ID. With the
sample records created by setup:

```json
[
  {"id": 1, "role": "RELATIONSHIP_MANAGER"},
  {"id": 2, "role": "RELATIONSHIP_MANAGER"},
  {"id": 3, "role": "REVIEWER"},
  {"id": 4, "role": "REVIEWER"}
]
```

If there are no users, the response is `[]`.

**Errors:** `503` if the database stays busy.

### GET /demo/applications

List the stored mortgage application IDs so a frontend can offer them in its
application selector. Like the user list, this is an optional addition for
the frontend.

**Access:** Either role.

**Input:** `X-User-Id`. No request body.

**Success:** `200` with a list of application IDs, ordered from lowest to
highest. With the sample records created by setup:

```json
[1, 2]
```

Applications are included even if they have no discount requests. If there are
no applications, the response is `[]`.

**Errors:** `403` for an unknown user; `422` for a missing or malformed user
header; `503` if the database stays busy.

### Request response fields

Submission, request lookup and decision responses use the same fields.
Application history contains a list of these objects.

| Field | Type | Meaning |
|---|---|---|
| `id` | Integer | ID of the discount request. |
| `application_id` | Integer | Mortgage application the request concerns. |
| `discount_bps` | Integer | Requested discount in basis points. |
| `reason` | String | Reason supplied by the relationship manager. |
| `submitted_by` | Integer | ID of the relationship manager who submitted it. |
| `submitted_at` | Timestamp string | Time the API recorded the submission. |
| `status` | String | `PENDING`, `APPROVED` or `DECLINED`. |
| `reviewer_id` | Integer or null | ID of the reviewer who decided it; null while pending. |
| `decided_at` | Timestamp string or null | Time the API recorded the decision; null while pending. |

Times are returned as UTC text, for example `2026-11-05T16:05:00.000000+00:00`.
The submission key is stored for matching retries and is not returned in these
responses.

### Validation and errors

Submission bodies must contain a positive integer `application_id`, a positive
whole-number `discount_bps`, and a string `reason`. The reason cannot be empty
or contain only whitespace, such as spaces, tabs or line breaks. Numeric strings,
decimals and booleans are rejected for the two integer fields. Both POST
endpoints reject extra body fields.

IDs in paths and headers must parse as positive integers. All input IDs and
discounts must fit SQLite's integer storage, up to `9223372036854775807`.

The submission key must also contain at least one character other than whitespace.
The API keeps the reason and key exactly as supplied; it does not trim spaces or
change letter case.

| Status | Meaning |
|---|---|
| `403` | The supplied user does not exist or their role cannot perform the action. |
| `404` | The application or request does not exist. User access is checked before this lookup. |
| `405` | The HTTP method is not supported on that path, including editing or deleting a request. |
| `409` | The action conflicts with saved data: a pending request, a previous decision or a submission key used with different details. |
| `422` | A required header or body field is missing or invalid, the JSON is malformed, or the body contains extra fields. |
| `503` | The database is still busy after three attempts. |
| `500` | An unexpected internal error occurred. |

Expected application errors return a string in `detail`, for example:

```json
{"detail": "Request already decided"}
```

Validation errors return a list in `detail`, describing the invalid fields and
where they occur. An unexpected `500` returns a generic server error rather
than database exception details.

## Request lifecycle

| Starting status | Action | Result |
|---|---|---|
| No request yet | Submit valid details. | A new request with a new ID and status `PENDING`. |
| `PENDING` | Approve. | Status becomes `APPROVED`; reviewer and decision time are saved. |
| `PENDING` | Decline. | Status becomes `DECLINED`; reviewer and decision time are saved. |
| `APPROVED` or `DECLINED` | Submit another decision, including the same outcome. | `409`; the saved decision is unchanged. |
| Any status | PUT, PATCH or DELETE `/requests/{request_id}`. | `405`; requests cannot be edited or deleted through the API. |

An approval is specific to one request and its requested discount. Once
submitted, the application ID, discount and reason cannot be edited.

Each application can have only one pending request. To change a pending request,
a reviewer must first decline it. The relationship manager can then submit a
new request with a new submission key. The earlier request is kept in history.

Suppose an application has an approved discount of 25 basis points. Submitting
a new request for 40 does not change the active discount. If the reviewer declines
the new request, 25 stays active. If the reviewer approves it, 40 becomes the new
active discount. The two discounts are not added together.

Both requests and their decisions are available in the application's history.
The earlier approved request still shows `APPROVED`, even after another approved
request supplies the active discount. The approved-discount endpoint identifies
which request currently applies. These rules are defined in SPEC's FR-04 to FR-12.

## Retries and simultaneous calls

### Repeating a submission

Choose a new `Idempotency-Key` for each new submission. If you do not receive
a response, send the same user, key and body again.

| Situation | Result |
|---|---|
| That user and key already have a saved request, and the body matches. | `200` with the same request ID and its current state. No new request is created. |
| That user and key already have a saved request, but the body differs. | `409`; the saved request is unchanged. |
| That user and key have no saved request. | The API attempts a new submission, applying the usual validation and pending-request rules. |

For example, repeating the original submission after its approval returns that
request with status `APPROVED`. A matching retry also works while a later request
is pending.

A submission rejected without saving a request does not reserve its key.

Keys belong to the submitting user. Two users can use the same key independently.
One user cannot reuse a saved key for a different application or different request
details, including after the first request is approved or declined. These rules
implement FR-14 to FR-16.

### Calls arriving at the same time

The submission examples use new keys and start with no pending request. The
decision example starts with one pending request. Inputs and user roles are valid.
These outcomes assume the database allows the calls to finish within the retry
limit, as in SPEC's AC-17 to AC-19.

| Calls arriving together | Result |
|---|---|
| Same user, key and submission body. | One `201`, one `200`, and one saved request. |
| Same user and key, but different requested discounts. | One `201`, one `409`, and one saved request. |
| New submissions with different keys for the same application. | One `201`, one `409`, and one pending request. |
| Two reviewers deciding the same pending request. | One `200`, one `409`, and one saved decision. |

If the database stays busy through three attempts, a call instead returns `503`
with `{"detail": "Database busy; try again"}`. That failed call saves no partial
changes. Another call may still have succeeded. Retrying a submission with its
original user, key and body returns the saved request if one exists; otherwise,
the API attempts to create it. This is the temporary-failure behaviour in QR-02
and AC-22.

## Implementation notes

### Storage and constraints

The tables are defined in [app/models.py](app/models.py):

| Table | Stored data and relationships |
|---|---|
| `mortgage_applications` | Integer primary key `id` for each sample application. |
| `users` | Integer primary key `id` and required `role`: `RELATIONSHIP_MANAGER` or `REVIEWER`. |
| `requests` | All request response fields plus `retry_key`. `application_id` references an application; `submitted_by` and `reviewer_id` reference users. |

Each request stores its submission and, once decided, its outcome, reviewer and
decision time in the same row. The API builds history from these rows. There is
no separate event table, reviewer assignment history or decision reason.

The database enforces these rules:

- Referenced applications and users must exist. Foreign-key checks are enabled
  on every connection.
- Discounts must be positive integers, and roles and statuses must use the
  permitted values.
- Pending requests have no reviewer or decision time. Approved and declined
  requests must have both.
- The combination of submitting user and submission key must be unique.
- A unique index on application ID applies only to pending requests. It allows
  at most one pending request per application while keeping all earlier requests.

The API exposes no route for editing submitted requests. Role permissions and
protection against replacing a saved decision are enforced by the operations in
[app/operations.py](app/operations.py).

To find the current approval, the implementation selects the highest request ID
among that application's approved requests. Because only one request can be
pending, it must receive a decision before the next request is created. This
makes request ID order sufficient to identify the latest approval.

### Transactions

`run_operation` creates a session and transaction for each attempt using
`with sessions.begin() as session:`. It commits all changes together before
returning success. An exception rolls back that attempt's changes.

A submission saves the request and its key together. A decision uses one UPDATE
that matches both the request ID and `PENDING` status. It sets the outcome,
reviewer and decision time together. A second decision cannot update the row
after its status has changed.

The operation checks for a matching submission key before checking for another
pending request. This lets a repeated submission retrieve the saved request
instead of being rejected as a new pending request.

Conflicts with the two uniqueness rules above trigger a new transaction so the
operation can read the request saved by another call. SQLite busy errors also
retry the whole transaction, with waits of 50 ms and 100 ms. There are at most
three attempts, and connections use SQLite's default five-second lock timeout.
Unrelated database errors are raised immediately. If a uniqueness conflict still
cannot be resolved on the last attempt, it is raised as an internal error; only
the busy-database case is converted to `503`.

### SQLite concurrency limits and PostgreSQL

SQLite allows one write transaction at a time, even when calls change different
mortgage applications. Running more API workers does not remove this limit.
See [SQLite isolation documentation](https://www.sqlite.org/isolation.html).

The tests cover two overlapping calls and a database kept busy by another
transaction. They do not measure how much traffic the API can handle.

PostgreSQL can update different rows at the same time. Calls updating the same
row may still wait for each other, and deadlocks can require a transaction retry. See
[PostgreSQL locking documentation](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-ROWS).

Moving to PostgreSQL would still require the unique submission key, single
pending request rule and protection against replacing decisions. It would also
require adapting the SQLite-specific connection settings, constraints, partial
index and error handling, then running the database and concurrency tests against
PostgreSQL. PostgreSQL has not been tested in this project.

### Where behaviour is checked

| Behaviour | Tests |
|---|---|
| Submission, decisions, history, active discounts, validation, access and demo lists. | [tests/test_api.py](tests/test_api.py) |
| Competing submissions, competing decisions and temporary failure when SQLite stays busy. | [tests/test_api_concurrency.py](tests/test_api_concurrency.py) |
| Stored fields, defaults and database constraints. | [tests/test_models.py](tests/test_models.py) |
| Connection setup, saved data after reconnection and transaction rollback. | [tests/test_database.py](tests/test_database.py) |

The concurrency test `test_busy_database_returns_503_without_reserving_submission_key`
holds a write lock, checks that a submission returns `503` without saving a request,
then checks that resending succeeds after the lock is released. This covers AC-22.
All these tests use temporary SQLite databases.
