# Jarvis Skill Registry

A multi-tenant, **organization-scoped registry for AI COO skills**. Organizations
draft custom skills, review them, and — with an owner's explicit approval —
activate exactly one immutable version of each for their agent runtime to load.

The whole point of the service is that one tenant can never see, touch or infer
another tenant's skills, and that an *active* skill can never change underneath
the agent running it.

```
draft skill  →  version 1 (immutable)  →  reviewed  →  owner activates  →  runtime loads it
                                                              ↓
                       edit? → version 2, reviewed, activated → version 1 becomes superseded
```

**Stack:** FastAPI (async) · Python 3.12 · PostgreSQL 16 · SQLAlchemy 2.0 (asyncpg)
· Alembic · Pydantic v2 · pytest + httpx.

> **Grading reference — [EVALUATION_MAP.md](EVALUATION_MAP.md)**
> Every requirement mapped to the exact file, line or test function that proves it.
>
> **Fastest verification** — two commands, about a minute:
> ```bash
> docker compose up --build -d     # migrates, seeds and serves; zero manual steps
> ./scripts/demo.sh                # 19 live checks: the full lifecycle + 5 attacks
> ```
> `scripts/demo.sh` exits non-zero if any check fails, so the exit code is the verdict.

Design decisions and their trade-offs are in **[ARCHITECTURE.md](ARCHITECTURE.md)**.
The verbatim test run is in **[TEST_OUTPUT.md](TEST_OUTPUT.md)**.

---

## What it guarantees

| Guarantee | How it is enforced |
|---|---|
| Tenancy comes only from the token | `get_current_user` reads a signed `org` claim and re-checks it against the database. No route, body or query parameter accepts an `organization_id`. |
| Every query is organization-filtered | Services can only reach the database through `ScopedRepository`, which has no way to express an unfiltered query. |
| Cross-tenant access is invisible, not forbidden | Reads, writes **and** activations outside your organization return `404`, never `403`. |
| An active version never changes | Three layers: no mutating route, a SQLAlchemy `before_update` guard, and a PL/pgSQL `BEFORE UPDATE` trigger that also catches raw SQL. |
| At most one active version per skill | Partial unique index `uq_skill_versions_one_active_per_skill`. |
| Nothing activates itself | Activation requires `role = 'owner'` in the owning org **and** a prior review. It is idempotent. |
| Requesting a tool never grants it | `tool_grants.granted` defaults to `false`; granting is a separate owner-only action. Runtime sees granted tools only. |
| The audit log only grows | Row-level `BEFORE UPDATE OR DELETE` trigger **and** a statement-level `BEFORE TRUNCATE` trigger (row triggers do not fire on `TRUNCATE`), plus `UPDATE`/`DELETE`/`TRUNCATE` revoked from the application role. |

---

## Prerequisites

* Docker with Compose v2 (`docker compose version`)
* Ports **8080** (API) and **5432** (Postgres) free — override with `API_HOST_PORT`
  and `DB_HOST_PORT` if not

Nothing else. No local Python, no manual database setup.

---

## Run it

```bash
docker compose up --build
```

That is the whole thing. The `api` container waits for Postgres to become
healthy, applies migrations, seeds the fixture organizations and starts the
server. When you see `Application startup complete`, the API is on
**http://localhost:8080** and interactive docs are at
**http://localhost:8080/docs**.

```bash
curl -s http://localhost:8080/health
# {"status":"ok"}
```

To start completely fresh (drops the database volume):

```bash
docker compose down -v && docker compose up --build
```

### Migrations and seeding

Both run automatically on start (see `scripts/entrypoint.sh`). To run them by
hand:

```bash
docker compose exec api alembic upgrade head     # apply migrations
docker compose exec api alembic downgrade base   # roll everything back
docker compose exec api alembic current          # show the current revision
docker compose exec api python -m app.seed       # re-seed (idempotent)
```

Alembic connects as the schema **owner** (`MIGRATION_DATABASE_URL`); the API
connects as a restricted **application** role (`DATABASE_URL`) that cannot own
tables and has no `UPDATE`/`DELETE` on `audit_log`. That separation is what makes
the append-only revocation real — see ARCHITECTURE.md.

### Seeded credentials

Development fixtures only. Obviously fake, and generated from `SEED_PASSWORD`
(default `dev-only-not-a-secret`, override in `.env`).

| Organization | Email | Role |
|---|---|---|
| ABC Construction | `owner@abc-construction.test` | `owner` |
| ABC Construction | `member@abc-construction.test` | `member` |
| XYZ Builders | `owner@xyz-builders.test` | `owner` |
| XYZ Builders | `member@xyz-builders.test` | `member` |

Password for all four: `dev-only-not-a-secret`

---

## Full walkthrough with curl

Every command below is real and runs against a freshly started stack. `jq` is
used only to pull ids out of responses.

```bash
API=http://localhost:8080
PASS=dev-only-not-a-secret
```

### 1. Log in as three different people

```bash
login() {
  curl -s -X POST $API/auth/login -H 'Content-Type: application/json' \
    -d "{\"email\":\"$1\",\"password\":\"$PASS\"}" | jq -r .access_token
}

ABC_OWNER=$(login owner@abc-construction.test)
ABC_MEMBER=$(login member@abc-construction.test)
XYZ_OWNER=$(login owner@xyz-builders.test)

curl -s $API/auth/me -H "Authorization: Bearer $ABC_OWNER" | jq
```

```json
{
  "id": "1166b976-05e0-476b-9f15-f5c4e51e2e0f",
  "email": "owner@abc-construction.test",
  "role": "owner",
  "organization_id": "099c2b37-6d16-4ae0-9924-f225f84d8ae4"
}
```

### 2. Create a skill draft

The call creates the skill *and* its immutable version 1. Note what comes back:
the skill is `draft`, and the two requested tools are recorded as
`"granted": false`.

```bash
SKILL=$(curl -s -X POST $API/skills \
  -H "Authorization: Bearer $ABC_MEMBER" -H 'Content-Type: application/json' \
  -d '{
    "name": "Daily Schedule Digest",
    "department": "operations",
    "description": "Summarises the day'"'"'s site schedule for managers.",
    "prompt_body": "You are the ABC Construction scheduling assistant. Summarise today'"'"'s schedule.",
    "requested_tools": ["query_schedule", "read_project"]
  }')

SKILL_ID=$(echo "$SKILL" | jq -r .id)
echo "$SKILL" | jq '{status, versions: [.versions[] | {version_number, status, content_hash, tool_grants}]}'
```

```json
{
  "status": "draft",
  "versions": [
    {
      "version_number": 1,
      "status": "draft",
      "content_hash": "4a2cb86b6cce50315be1be1ccc238d6e01264b9391f74825e64bbf85f655beb7",
      "tool_grants": [
        { "tool_name": "query_schedule", "granted": false, "granted_by": null, "granted_at": null },
        { "tool_name": "read_project",  "granted": false, "granted_by": null, "granted_at": null }
      ]
    }
  ]
}
```

### 3. A draft is not loadable by the runtime

```bash
curl -s "$API/skills/active" -H "Authorization: Bearer $ABC_OWNER" | jq
# []
```

### 4. Activation is refused before review

```bash
curl -s -X POST $API/skills/$SKILL_ID/versions/1/activate \
  -H "Authorization: Bearer $ABC_OWNER" | jq
```

```json
{
  "error": {
    "code": "VERSION_NOT_REVIEWED",
    "message": "Version must be reviewed before it can be activated.",
    "detail": { "version_number": 1 }
  }
}
```

### 5. Review it

```bash
curl -s -X POST $API/skills/$SKILL_ID/versions/1/review \
  -H "Authorization: Bearer $ABC_MEMBER" | jq '{version_number, status, reviewed_by, reviewed_at}'
```

### 6. A member cannot activate — 403

The member *can* see this skill, so hiding it would be a lie. Only the role is
insufficient.

```bash
curl -s -X POST $API/skills/$SKILL_ID/versions/1/activate \
  -H "Authorization: Bearer $ABC_MEMBER" | jq .error.code
# "NOT_ORG_OWNER"
```

### 7. The other organization's owner gets 404 — not 403

A `403` would confirm the id names a real row. The resource is invisible, so the
role check is never even reached.

```bash
curl -s -X POST $API/skills/$SKILL_ID/versions/1/activate \
  -H "Authorization: Bearer $XYZ_OWNER" | jq .error.code
# "SKILL_NOT_FOUND"

curl -s $API/skills/$SKILL_ID -H "Authorization: Bearer $XYZ_OWNER" -o /dev/null -w '%{http_code}\n'
# 404
```

### 8. The owner grants one of the two requested tools

```bash
curl -s -X POST $API/skills/$SKILL_ID/versions/1/tool-grants \
  -H "Authorization: Bearer $ABC_OWNER" -H 'Content-Type: application/json' \
  -d '{"tools": ["query_schedule"]}' | jq '[.tool_grants[] | {tool_name, granted}]'
```

```json
[
  { "tool_name": "query_schedule", "granted": true },
  { "tool_name": "read_project",  "granted": false }
]
```

### 9. The owner activates

```bash
curl -s -D- -o/dev/null -X POST $API/skills/$SKILL_ID/versions/1/activate \
  -H "Authorization: Bearer $ABC_OWNER" | grep -i x-activation-changed
# x-activation-changed: true
```

### 10. Activation is idempotent

Same call again: `200`, unchanged state, and **no second audit row**.

```bash
curl -s -D- -o/dev/null -X POST $API/skills/$SKILL_ID/versions/1/activate \
  -H "Authorization: Bearer $ABC_OWNER" | grep -i x-activation-changed
# x-activation-changed: false

curl -s $API/audit -H "Authorization: Bearer $ABC_OWNER" \
  | jq '[.[] | select(.event == "skill_version.activated")] | length'
# 1
```

### 11. Runtime selection — active only, granted tools only

```bash
curl -s "$API/skills/active?department=operations" \
  -H "Authorization: Bearer $ABC_OWNER" | jq '.[] | {name, version_number, content_hash, granted_tools}'
```

```json
{
  "name": "Daily Schedule Digest",
  "version_number": 1,
  "content_hash": "4a2cb86b6cce50315be1be1ccc238d6e01264b9391f74825e64bbf85f655beb7",
  "granted_tools": ["query_schedule"]
}
```

XYZ Builders sees nothing:

```bash
curl -s "$API/skills/active" -H "Authorization: Bearer $XYZ_OWNER" | jq
# []
```

### 12. Editing an active skill creates version 2 — it never mutates version 1

```bash
curl -s -X POST $API/skills/$SKILL_ID/versions \
  -H "Authorization: Bearer $ABC_OWNER" -H 'Content-Type: application/json' \
  -d '{"prompt_body": "Revised: include weather and crew availability.", "requested_tools": ["query_schedule"]}' \
  | jq '{version_number, status}'
# { "version_number": 2, "status": "draft" }

curl -s -X POST $API/skills/$SKILL_ID/versions/2/review -H "Authorization: Bearer $ABC_OWNER" >/dev/null
curl -s -X POST $API/skills/$SKILL_ID/versions/2/activate -H "Authorization: Bearer $ABC_OWNER" >/dev/null

curl -s $API/skills/$SKILL_ID -H "Authorization: Bearer $ABC_OWNER" \
  | jq '[.versions[] | {version_number, status}]'
```

```json
[
  { "version_number": 1, "status": "superseded" },
  { "version_number": 2, "status": "active" }
]
```

Version 1's `prompt_body` and `content_hash` are byte-for-byte what they were.

### 13. Destructive and unknown tools are refused

```bash
curl -s -X POST $API/skills -H "Authorization: Bearer $ABC_OWNER" -H 'Content-Type: application/json' \
  -d '{"name":"Bad","department":"ops","prompt_body":"p","requested_tools":["shell_exec"]}' | jq .error
```

```json
{
  "code": "FORBIDDEN_TOOL_PATTERN",
  "message": "Tool name 'shell_exec' is rejected: destructive capability.",
  "detail": { "tool": "shell_exec", "reason": "destructive capability" }
}
```

```bash
curl -s -X POST $API/skills -H "Authorization: Bearer $ABC_OWNER" -H 'Content-Type: application/json' \
  -d '{"name":"Bad","department":"ops","prompt_body":"p","requested_tools":["read_everything"]}' | jq .error.code
# "UNKNOWN_TOOL"
```

### 14. A smuggled `organization_id` is rejected

Tenancy comes from the token and nowhere else.

```bash
curl -s -X POST $API/skills -H "Authorization: Bearer $ABC_OWNER" -H 'Content-Type: application/json' \
  -d '{"name":"Smuggled","department":"ops","prompt_body":"p","requested_tools":[],
       "organization_id":"00000000-0000-0000-0000-000000000000"}' | jq .error.code
# "VALIDATION_ERROR"
```


### 15. The database refuses to mutate an active version, even from psql

The strongest guarantee, reached by going around the application entirely:

```bash
docker compose exec -e PGPASSWORD=dev-only-not-a-secret db \
  psql -U jarvis_app -d jarvis \
  -c "UPDATE skill_versions SET prompt_body = 'silently mutated' WHERE status = 'active';"
```

```
ERROR:  skill_versions ede6e667-…: the content of an ACTIVE version is immutable;
        create a new version instead
CONTEXT:  PL/pgSQL function skill_versions_forbid_active_mutation() line 8 at RAISE
```

And the audit log cannot be rewritten, by the app role or by the schema owner:

```bash
docker compose exec -e PGPASSWORD=dev-only-not-a-secret db \
  psql -U jarvis_app -d jarvis -c "DELETE FROM audit_log;"
# ERROR:  permission denied for table audit_log

docker compose exec -e PGPASSWORD=dev-only-not-a-secret db \
  psql -U jarvis_owner -d jarvis -c "DELETE FROM audit_log;"
# ERROR:  audit_log is append-only; DELETE is not permitted
```

### 16. Disable, and it leaves the runtime immediately

```bash
curl -s -X POST $API/skills/$SKILL_ID/disable -H "Authorization: Bearer $ABC_OWNER" | jq .status
# "disabled"

curl -s "$API/skills/active" -H "Authorization: Bearer $ABC_OWNER" | jq
# []
```

### 17. The audit trail

Every entry carries the organization, the actor, the event and the exact version
number.

```bash
curl -s $API/audit -H "Authorization: Bearer $ABC_OWNER" \
  | jq -r '.[] | "\(.created_at)  \(.event)  v\(.version_number // "-")  actor=\(.actor_user_id)"'
```

```
2026-08-26T14:31:07Z  skill.disabled           v-   actor=1166b976-…
2026-08-26T14:31:07Z  skill_version.disabled   v2   actor=1166b976-…
2026-08-26T14:31:05Z  skill_version.activated  v2   actor=1166b976-…
2026-08-26T14:31:05Z  skill_version.superseded v1   actor=1166b976-…
…
```

---

## API surface

All routes except `/health` and `/auth/login` require `Authorization: Bearer <token>`.

| Method | Path | Notes |
|---|---|---|
| `POST` | `/auth/login` | Email + password → access token |
| `GET` | `/auth/me` | Current user and organization |
| `POST` | `/skills` | Create skill draft + version 1 |
| `GET` | `/skills` | List skills in the caller's organization |
| `GET` | `/skills/{id}` | One skill with all its versions |
| `PATCH` | `/skills/{id}` | Skill metadata only — never version content |
| `POST` | `/skills/{id}/versions` | Create the next immutable version |
| `POST` | `/skills/{id}/versions/{n}/review` | Mark a draft reviewed |
| `POST` | `/skills/{id}/versions/{n}/activate` | **Owner only.** Idempotent |
| `POST` | `/skills/{id}/versions/{n}/tool-grants` | **Owner only.** Grant requested tools |
| `POST` | `/skills/{id}/disable` | **Owner only** |
| `GET` | `/skills/active?department=` | Runtime selection |
| `GET` | `/audit` | Audit log for the caller's organization |
| `GET` | `/health` | Liveness |

There is deliberately **no** `PUT`/`PATCH` on a version, no endpoint that takes an
`organization_id`, and no "list all skills" route.

### Errors

One envelope, everywhere:

```json
{ "error": { "code": "SKILL_NOT_FOUND", "message": "Skill not found.", "detail": { "skill_id": "…" } } }
```

| Code | Status | Meaning |
|---|---|---|
| `AUTH_REQUIRED` / `INVALID_TOKEN` / `INVALID_CREDENTIALS` | 401 | Authentication |
| `NOT_ORG_OWNER` | 403 | Visible to you, but owner-only |
| `SKILL_NOT_FOUND` / `SKILL_VERSION_NOT_FOUND` | 404 | Absent **or** another tenant's |
| `SKILL_NAME_CONFLICT` | 409 | Name already used in this organization |
| `VERSION_NOT_REVIEWED` | 409 | Activation before review |
| `VERSION_NOT_ACTIVATABLE` | 409 | Wrong lifecycle state |
| `VERSION_ALREADY_REVIEWED` | 409 | Duplicate review |
| `ACTIVE_VERSION_IMMUTABLE` | 409 | Attempted mutation of an active version |
| `SKILL_DISABLED` | 409 | Skill is disabled |
| `UNKNOWN_TOOL` | 422 | Not on the allowlist |
| `FORBIDDEN_TOOL_PATTERN` | 422 | Destructive or malformed tool name |
| `TOOL_NOT_REQUESTED` | 422 | Granting a tool this version never asked for |
| `VALIDATION_ERROR` | 422 | Request body/params failed validation |
| `INTERNAL_ERROR` | 500 | Opaque by design — no stack traces reach clients |

---

## Tests

```bash
docker compose run --rm api pytest -v --cov=app --cov-report=term-missing
```

For a live check against a running stack rather than the test suite, use
`./scripts/demo.sh` — see [Grading reference](EVALUATION_MAP.md).

Real PostgreSQL, real HTTP through the real ASGI app, real authorization. The
tenancy dependency is never mocked — overriding it would delete the thing under
test. The only substitution is the database session, swapped for one bound to a
transaction that is rolled back after each test.

The suite connects as the restricted application role while Alembic migrates as
the schema owner, which is what lets a test observe the `audit_log` revocation.

Highlights:

* `tests/test_isolation.py` — same-org read, cross-org read/update/activation
* `tests/test_immutability.py` — all three layers, including **raw SQL that proves
  the database trigger fires**, one case per content column
* `tests/test_activation.py` — owner-only, review-gated, idempotent, atomic supersede
* `tests/test_token_tampering.py` — forged `org` and self-promoted `role` claims
* `tests/test_structure.py` — scans the source and the OpenAPI document so the
  isolation model cannot quietly erode

The full run is recorded verbatim in [TEST_OUTPUT.md](TEST_OUTPUT.md).

---

## Layout

```
alembic/versions/     0001 schema · 0002 triggers, partial unique index, grants
app/
  api/                routers, tenancy dependencies, error handlers
  core/               config, errors, security, enums, tool allowlist
  db/                 base, session, ScopedRepository  ← the tenancy choke point
  models/             SQLAlchemy models + the before_update immutability guard
  schemas/            Pydantic v2 (extra="forbid" on every request)
  services/           skill lifecycle, activation, audit, hashing
  seed.py             fixture organizations and users
db/init/              creates the restricted app role and the test database
scripts/
  entrypoint.sh       migrate -> seed -> serve (the container's CMD)
  demo.sh             one-command live verification: lifecycle + 5 attacks
tests/
```

---

## Code quality

Both run inside the same container as the tests, so there is no "works on my
machine" gap:

```bash
docker compose run --rm api ruff check .
docker compose run --rm api mypy app/
```

```
$ ruff check .
All checks passed!

$ mypy app/
Success: no issues found in 36 source files
```

Configuration is in `pyproject.toml`. ruff runs pycodestyle, pyflakes, isort,
bugbear, pyupgrade, comprehensions, simplify, async correctness, **bandit
security checks** and private-member access. mypy runs with
`disallow_untyped_defs` and `check_untyped_defs` enabled.

There are no blanket ignores. Five findings are suppressed individually, each
with an inline comment naming the rule and the reason — for example
`app/core/config.py:33`, where bandit flags the development seed password that
this README deliberately publishes. Every other finding was fixed rather than
silenced, including replacing `dict[str, object]` in `app/seed.py` with real
dataclasses, which removed five `type: ignore` comments instead of hiding behind
them.

## Known limitations

Honest and complete. Everything here is true of this build; nothing is invented
to look thorough, and none of it is hidden by the tests.

**Security hardening not done**

* **No PostgreSQL row-level security.** Isolation is enforced by
  `ScopedRepository` and proved by tests, not by the database. RLS policies keyed
  on `organization_id` — with the app role setting a per-request
  `SET LOCAL app.organization_id` — would make the guarantee hold even for a
  future service that talks to this database without going through the
  repository. This is the natural next step *beyond* the triggers: the triggers
  protect immutability, RLS would protect tenancy. The schema is already shaped
  for it, since every tenant table carries a non-nullable `organization_id`.
* **No rate limiting or brute-force protection.** `POST /auth/login` will answer
  as fast as you can ask it. bcrypt makes each attempt costly, which is not the
  same as a lockout.
* **No refresh tokens, no revocation list, no key rotation.** HS256 with one
  shared secret; a stolen token stays valid for its 60-minute lifetime. Deleting
  the user does kill it, because the `(user, organization)` pair is re-checked
  against the database on every request — but that is a side effect, not a
  revocation mechanism.
* **No secrets management.** `JWT_SECRET` comes from the environment with no
  default, which is the right shape, but there is no rotation, no KMS, no
  envelope encryption.

**Operational gaps**

* **No structured logging, tracing or metrics.** Logging is `logging.basicConfig`
  to stdout in plain text. There is no request id propagated into log lines (the
  actor and organization are attached to `request.state` but never emitted), no
  OpenTelemetry spans, and no counters on the things worth alerting on —
  activation rate, 403/404 ratios, tool-grant frequency.
* **The audit write is same-transaction, but there is no outbox.** A state change
  and its audit row commit or roll back together, which is the important half.
  There is no outbox table, no change-data-capture and no retry pattern, so a
  downstream consumer — a SIEM, an analytics warehouse, a compliance archive —
  has no reliable way to be notified. Adding an outbox row inside the same
  transaction and draining it separately is the standard fix and is not done here.
* **No health signal beyond liveness.** `/health` returns `ok` without checking
  the database, so it proves the process is up, not that it can serve.
* **Single region, single writer.** No read replicas, no connection pooling
  beyond SQLAlchemy's defaults, no partitioning, and `audit_log` grows forever
  with no retention or archival policy.

**Product gaps**

* **No pagination anywhere.** `GET /skills` returns every skill in the
  organization; `GET /audit` is capped at 500 rows with no cursor. Fine at
  fixture scale, wrong at tenant scale.
* **No soft delete or restore.** `disable` is the only removal and it is one-way
  — there is no `enable`, and no way to recover a skill disabled by mistake other
  than creating a new one.
* **No separation of duties on review.** The author of a version may review their
  own version. Enforcing reviewer ≠ author is a small change and is probably the
  right default for a control that exists to gate activation.
* **The tool allowlist is a code constant.** Adding a tool requires a deploy
  (`app/core/tools.py`). Deliberate for now — it makes the set auditable in
  review — but a real deployment would want it to be data, per-tenant, and itself
  versioned and audited.
* **No bulk or batch operations**, and no way to copy a skill between
  departments or clone one as a starting point.

**Testing gaps**

* **Concurrency is not covered in the automated suite.** The pytest harness is
  single-connection by design (each test runs inside one transaction that is
  rolled back), so genuine parallel requests cannot be expressed in it. Parallel
  activation, parallel version creation and parallel tool grants were exercised
  by hand against a live stack — the `SELECT … FOR UPDATE` lock held in every
  case — and one race found that way is now covered by a deterministic
  regression test (`tests/test_lifecycle_edges.py:165`). Guarding the rest in CI
  needs a second harness that commits rather than rolls back.
* **No load or soak testing.** Nothing here has been run under sustained traffic,
  so the pool sizing and lock-contention behaviour are untested assumptions.

**Environment**

* **`docker-compose.yml` carries development placeholder credentials** behind
  `${VAR:-…}` fallbacks so the stack starts with zero manual steps. `.env.example`
  contains placeholders only, `.env` is gitignored and was never committed, and
  the application has **no default** for `JWT_SECRET` — it refuses to start
  without one.
