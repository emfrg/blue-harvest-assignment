# Mortgage pricing exceptions

An HTTP API for requesting and reviewing discounts on mortgage interest rates.
A relationship manager submits a requested discount and a reason. A reviewer
approves or declines it, and the mortgage application process can retrieve the
approved amount. Each request records who submitted it, who decided it and when.

The API uses Python, FastAPI and SQLAlchemy with a local SQLite database.
The steps below take you through submitting a request, approving it and reading
the result. The agreed requirements and decisions are in [SPEC.md](SPEC.md);
the endpoint contracts are in [API.md](API.md).

## Before You Start

You need:

- **Python 3.13.** Download it from [python.org](https://www.python.org/downloads/).
- **Git** to clone the repository. See the [Git downloads](https://git-scm.com/downloads/).
- **A browser**, if you want to try the API through its interactive documentation.

The API and its database run entirely on your computer. No cloud account,
paid service or separate database installation is needed.

## Run Locally

### 1. Clone the Repository

```bash
git clone https://github.com/emfrg/blue-harvest-assignment.git
cd blue-harvest-assignment
```

If you already have the repository, open a terminal in its root folder.

### 2. Install the Dependencies

A virtual environment keeps this project's packages separate from your other
Python projects. Create and activate it using the commands for your system.

**macOS (Terminal)**

```bash
python3.13 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell)**

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Then install the dependencies and commit hooks. These commands, and the database
and server commands below, are the same on both systems:

```sh
python -m pip install -r requirements.txt
python -m pre_commit install
```

The last command installs the checks that run before each local commit.
`requirements.txt` includes the API dependencies and development tools.

### 3. Create the Database and Sample Records

```bash
python -m app.init_db
```

Expect `Database ready:` followed by the path to `data/requests.sqlite3`.
This creates the tables, two sample mortgage applications and four sample users.
It does not create discount requests.

Run this setup before using the mortgage endpoints. Rerunning it adds missing
sample records and preserves existing data. It does not update existing sample
records or migrate tables after a model change. The database file is ignored by Git.

### 4. Start the API

```bash
python -m uvicorn app.main:app --reload --reload-dir app
```

Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).
The page lists the endpoints and lets you call them from your browser.

You can also call the API with **curl** from a second terminal. For example,
read the request history for application `1`:

**macOS (Terminal)**

```bash
curl -i -H "X-User-Id: 1" http://127.0.0.1:8000/applications/1/requests
```

**Windows (PowerShell)**

```powershell
curl.exe -i -H "X-User-Id: 1" http://127.0.0.1:8000/applications/1/requests
```

Expect HTTP **200** with a JSON response containing the application's requests.
On a fresh database, the `requests` list is empty. All endpoints can be called
with curl; [API.md](API.md) describes their headers and request bodies.

Uvicorn runs the API server in this terminal. The `--reload --reload-dir app`
options restart it when Python files in `app/` change. Press `Ctrl+C` to stop it.
When returning later, activate `.venv` again and run the server command.
You do not need to recreate the database or reinstall packages each time.

## Try the API

Setup provides these records:

| Record | IDs | Use |
|---|---|---|
| Mortgage applications | `1`, `2` | Applications for which you can request a discount. |
| Relationship managers | `1`, `2` | Submit requests and read results. |
| Reviewers | `3`, `4` | Approve or decline requests and read results. |

Supply the chosen user ID in the `X-User-Id` header for each mortgage operation.
In `/docs`, expand an endpoint, select **Try it out**, fill in the fields and
select **Execute**. Check the HTTP status and JSON body under **Server response**.

The walkthrough assumes application `1` has no pending request. If you repeat
it, choose unused keys for both submissions, such as `readme-25-2` and
`readme-40-2`. If a request is already pending, see the pending-request entry
under [Troubleshooting](#troubleshooting).

### 1. Submit a Discount Request

Open **POST /requests**. Set `X-User-Id` to `1` and `Idempotency-Key` to an
unused key, such as `readme-25-1`. Use this body:

```json
{
  "application_id": 1,
  "discount_bps": 25,
  "reason": "Competitive offer"
}
```

Expect **201**, status `PENDING`, and null decision fields. Save the returned
`id`; use that value wherever the next steps ask for `request_id`.
The discount is 25 basis points, or 0.25 percentage points.

Choose a new submission key for each new request. If a call times out, resend
the same user, key and body. Repeating this submission returns **200** with the
same request ID and its current state, without creating a duplicate.

### 2. Read the Request

Open **GET /requests/{request_id}**. Enter the returned request ID and
`X-User-Id: 1`. Expect **200** with the submitted details and status `PENDING`.

### 3. Approve It

Open **POST /requests/{request_id}/decision**. Use the same request ID,
set `X-User-Id` to reviewer `3`, and send:

```json
{"outcome": "APPROVED"}
```

Expect **200**, status `APPROVED`, `reviewer_id: 3` and a populated `decided_at`.
The requested discount remains 25 basis points.

### 4. Retrieve the Approved Discount

Open **GET /applications/{application_id}/approved-discount** with
`application_id: 1` and `X-User-Id: 1`.

Expect **200**. The `approved_discount` object contains your request ID and
`discount_bps: 25`. This is the amount the mortgage application process can use.

### 5. Inspect the History

Open **GET /applications/{application_id}/requests** with `application_id: 1`
and `X-User-Id: 1`. Expect **200** with the request, its original details and
the recorded approval, reviewer and decision time.

To also try a decline, submit a new request for 40 basis points using a new key,
such as `readme-40-1`. Send `{"outcome": "DECLINED"}` as reviewer `3` for the
new request ID. History should show both requests, and the current approved
discount should still be 25 basis points.

Two additional endpoints let a frontend load its user and application choices
from the database instead of keeping hardcoded lists:

- `GET /demo/users` returns the available user IDs and their roles.
- `GET /demo/applications` returns the available mortgage application IDs.
  Supply a known user ID in the `X-User-Id` header.

In `/docs`, these endpoints are grouped under **Frontend demo**. You can complete
the request and review workflow above without using them.

## Run Tests and Quality Checks

In a terminal at the repository root, activate the environment.

**macOS (Terminal)**

```bash
source .venv/bin/activate
```

**Windows (PowerShell)**

```powershell
.\.venv\Scripts\Activate.ps1
```

Then run the tests and checks on either system:

```sh
python -m pytest
python -m pre_commit run --all-files
```

Tests create temporary SQLite databases, so they do not modify
`data/requests.sqlite3`. They exercise the request workflow, validation and
permissions, duplicate submissions, competing decisions and persistence.

The pre-commit checks cover Ruff formatting, Ruff linting and strict mypy type
checking for `app/` and `tests/`. They report problems without rewriting files.
To apply formatting corrections, run:

```bash
python -m ruff format app tests
```

Review the changes and rerun the checks. Once installed, these hooks block a
local commit if a check fails. Keep `.venv` activated when committing so the
hooks use the project's installed tools. Pytest runs separately. Each new
checkout needs the `python -m pre_commit install` step.

## Assumptions and Scope

### Users and Access

Setup creates sample users and mortgage applications. For each mortgage operation,
you send a user ID in `X-User-Id`. The API checks that the user exists and that
their role allows the action.

There is no login or password check. Anyone calling the local API can send any
of the sample user IDs. Company login integration and cloud deployment are
outside the scope of this assignment.

### Requests and Decisions

Once a request is submitted, its application ID, discount and reason cannot be
edited. An approval is specific to that request and its requested discount.

Each mortgage application can have only one request waiting for a decision.
To change a request that is still pending, a reviewer must first decline it.
The relationship manager can then submit a new request with the changed details.

If an application already has an approved discount, that discount stays active
while a new request is pending. It also stays active if the new request is declined.
If the new request is approved, the newly approved discount becomes the active
discount for that application.

The history lists all requests, including earlier approvals and declines. For
each decision, it shows who made it and when.

Discounts must be positive whole numbers of basis points. The full business rules
and acceptance examples are in [SPEC.md](SPEC.md).

### Database Access

SQLite allows only one database operation to write at a time. If an operation
fails because the database is busy, the API tries again. If the database is
still busy after three attempts, the API returns `503`.

The concurrency tests check specific situations, such as two reviewers trying to
decide the same request at the same time. They do not measure how much traffic
the API can handle. See [API.md](API.md#sqlite-concurrency-limits-and-postgresql)
for the database limitations and the comparison with PostgreSQL.

## Project Files

| File or directory | Where to look |
|---|---|
| [SPEC.md](SPEC.md) | Agreed behaviour, acceptance scenarios and decision history. Start here when changing requirements. It also explains the specification's preparation and AI contribution. |
| [API.md](API.md) | Endpoints, request and response fields, error codes and transaction handling. |
| [app/main.py](app/main.py) | Application startup and shutdown, router registration and the health endpoint. |
| [app/api.py](app/api.py) | HTTP routes, headers and generated API documentation. |
| [app/schemas.py](app/schemas.py) | Input validation and response shapes. |
| [app/operations.py](app/operations.py) | Business operations, access checks and transaction retries. |
| [app/models.py](app/models.py) | Database tables, fields and constraints. |
| [app/database.py](app/database.py), [app/init_db.py](app/init_db.py) | Database connections, sessions and initial setup with sample records. |
| [tests/](tests/) | API, concurrency, model, database and health checks. Shared fixtures are in `conftest.py`. |
| [pyproject.toml](pyproject.toml), [.pre-commit-config.yaml](.pre-commit-config.yaml) | Formatting, linting, type-checking and commit-hook configuration. |

## Troubleshooting

| Problem | What to check |
|---|---|
| Python 3.13 is not found | Install Python 3.13 and reopen the terminal. Check with `python3.13 --version` on macOS or `py -3.13 --version` on Windows. |
| PowerShell blocks `Activate.ps1` | See [Python's Windows activation guidance](https://docs.python.org/3.13/library/venv.html#creating-virtual-environments), then retry the activation command. |
| `ModuleNotFoundError` | Activate `.venv` and install `requirements.txt` using that environment's `python`. |
| Mortgage endpoints fail with a missing-table error in the server log | Run `python -m app.init_db` from the repository root. A successful `/health` response only confirms that the API responds; it does not check database readiness. |
| Port 8000 is already in use | Use `python -m uvicorn app.main:app --reload --reload-dir app --port 8001` and open `http://127.0.0.1:8001/docs`. |
| `403` | Check that `X-User-Id` exists and has the required role. Use a manager to submit and a reviewer to decide. |
| `422` | Read the response's `detail` field for the invalid or missing input. Supply the required headers and a positive integer discount. |
| `409`: application already has a pending request | Read that application's history. Review the pending request before submitting another. If you intended to change it, decline it first and submit the changed details with a new key. |
| `409`: retry key already used with different details | Use the original body for a retry. For a new request, use a new key and ensure the application has no pending request. |
| `409`: request already decided | The saved decision cannot be changed. Further consideration requires a new request. |
| `503` | Another database operation may still be holding a lock. Try again after it finishes. For a submission retry, keep the original user, key and body. |

For other response details, see [Validation and errors](API.md#validation-and-errors).
