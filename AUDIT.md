# Pre-submission self-audit

Run against commit `ef888c1` on a stack rebuilt from scratch (`docker compose
down -v && docker compose up --build`). Every item below was executed, not
recalled. Commands and their real output are quoted.

**Headline: no automatic-rejection criterion is triggered. Three real defects
found, one of them a genuine bug (a 500 where a 409 belongs, under concurrency).**

---

## 1. Fresh-start integrity

### 1.1 `docker compose down -v && docker compose up --build` — PASS

Zero manual steps. `--wait` returned exit 0; both containers reported healthy.
Last 15 lines of `up`:

```
 Volume jarvis-skill-registry_pgdata Created
 Container jarvis-skill-registry-db-1 Creating
 Container jarvis-skill-registry-db-1 Created
 Container jarvis-skill-registry-api-1 Creating
 Container jarvis-skill-registry-api-1 Created
 Container jarvis-skill-registry-db-1 Starting
 Container jarvis-skill-registry-db-1 Started
 Container jarvis-skill-registry-db-1 Waiting
 Container jarvis-skill-registry-db-1 Healthy
 Container jarvis-skill-registry-api-1 Starting
 Container jarvis-skill-registry-api-1 Started
 Container jarvis-skill-registry-db-1 Waiting
 Container jarvis-skill-registry-api-1 Waiting
 Container jarvis-skill-registry-db-1 Healthy
 Container jarvis-skill-registry-api-1 Healthy
```

API container tail: `==> applying database migrations` → `==> seeding fixture
organizations and users` → `==> starting api on 0.0.0.0:8000` → `Application
startup complete.`

### 1.2 OpenAPI / docs — PASS

```
openapi.json: HTTP 200  bytes=17403
/docs:        HTTP 200  bytes=945
Jarvis Skill Registry v1.0.0 | paths: 12
```

### 1.3 Migrations from a clean DB — PASS

`alembic current` → `0002_db_level_guarantees (head)`; `SELECT version_num FROM
alembic_version` → `0002_db_level_guarantees`. No `error|traceback|exception` in
the startup log.

### 1.4 Seed proven by direct DB query — PASS

Not trusting exit 0 — queried the tables:

```
   organization   |       slug       |            email             |  role  | pw_hash_len | hash_prefix
------------------+------------------+------------------------------+--------+-------------+-------------
 ABC Construction | abc-construction | owner@abc-construction.test  | owner  |          60 | $2b$
 ABC Construction | abc-construction | member@abc-construction.test | member |          60 | $2b$
 XYZ Builders     | xyz-builders     | owner@xyz-builders.test      | owner  |          60 | $2b$
 XYZ Builders     | xyz-builders     | member@xyz-builders.test     | member |          60 | $2b$
```

`orgs=2 users=4 owners=2 members=2`. Passwords are real bcrypt (`$2b$`, 60 chars).
Re-running the seed left counts unchanged (`orgs=2 users=4`) — genuinely idempotent.

---

## 2. Test suite honesty

### 2.1 Fresh run vs `TEST_OUTPUT.md` — PASS

```
$ diff TEST_OUTPUT.md <fresh run>
191c191
< ============================= 144 passed in 24.08s =============================
---
> ============================= 144 passed in 23.44s =============================
```

Identical apart from the wall-clock duration. Not stale, not fabricated. Both
runs: `144 passed`, `TOTAL 899 0 100%`.

### 2.2 All 13 mandatory tests present as separate functions — PASS

| # | Requirement | Test function |
|---|---|---|
| 1 | Same-org create then read | `test_isolation.py:15 test_same_org_create_then_read_succeeds` |
| 2 | Cross-org read denied (404) | `test_isolation.py:34 test_cross_org_read_returns_404_not_403` |
| 3 | Cross-org update denied | `test_isolation.py:50 test_cross_org_update_is_denied` |
| 4 | Cross-org activation denied | `test_isolation.py:84 test_cross_org_activation_is_denied_with_404` |
| 5 | Member activation denied (403) | `test_activation.py:16 test_member_cannot_activate_and_gets_403` |
| 6 | Draft cannot load as active | `test_runtime_selection.py:16 test_a_draft_skill_never_loads_as_active` |
| 7 | Disabled excluded from runtime | `test_runtime_selection.py:68 test_a_disabled_skill_is_excluded_from_runtime_selection` |
| 8 | Active version immutable — API | `test_immutability.py:33 test_no_route_exists_to_mutate_a_version` |
| 8 | …application layer | `test_immutability.py:84 test_orm_guard_blocks_mutation_of_an_active_version` |
| 8 | …raw SQL / DB trigger | `test_immutability.py:146 test_db_trigger_blocks_raw_sql_mutation_of_an_active_version` |
| 9 | Duplicate activation idempotent | `test_activation.py:74 test_duplicate_activation_is_idempotent_and_writes_no_duplicate_audit` |
| 10 | Invalid tool rejected | `test_tools.py:20 test_an_unknown_tool_is_rejected_with_422` |
| 10 | Destructive tool rejected | `test_tools.py:56 test_a_destructive_or_malformed_tool_is_rejected_with_422` |
| 10 | Requested ≠ granted | `test_tools.py:93 test_a_requested_tool_is_never_auto_granted` |
| 11 | Audit has org/actor/event/version | `test_audit.py:18 test_an_audit_record_carries_organization_actor_event_and_version_number` |
| 12 | One active version (DB proof) | `test_immutability.py:210 test_only_one_active_version_per_skill_is_possible` |
| 13 | Validation code + status | `test_errors.py:43 test_validation_failures_return_422_with_the_validation_error_code` |

None folded together, none skipped.

### 2.3 Fake-test patterns — PASS

* `assert True` / `assert 1` — **none**
* `pytest.mark.skip` / `xfail` / `pytest.skip(` — **none**
* commented-out assertions (`# assert`) — **none**
* silent `except: pass` — **none** anywhere in `tests/` or `app/`
* All five `try:` blocks are `try/finally` cleanup (fixture teardown at
  `conftest.py:79,89,103`; engine disposal at `test_error_handlers.py:100,113`).
  None swallow a failure.

Two things a reviewer should not misread:

* `test_error_handlers.py:53` asserts `status_code == 500`. That is **not** a test
  passing because an endpoint crashed — it is a purpose-built throwaway app that
  deliberately raises, asserting the response contains no traceback, no exception
  class and no connection string. It is the "no stack traces leaked" test.
* **PARTIAL:** `test_lifecycle_edges.py:24
  test_the_application_lifespan_starts_and_stops_cleanly` contains **no assertion**.
  It only fails if `lifespan()` raises. Every other one of the 144 tests asserts or
  uses `pytest.raises` (verified by AST walk). This one is a bare smoke test and is
  weaker than it looks.

### 2.4 Immutability has both an API test and a raw-SQL test — PASS

Three layers, tested separately, not one test doing double duty:
API (`test_no_route_exists_to_mutate_a_version`, parametrised over PUT/PATCH/DELETE,
plus `test_an_active_version_cannot_be_re_reviewed`), application
(`test_orm_guard_blocks_mutation_of_an_active_version`), and raw SQL
(`test_db_trigger_blocks_raw_sql_mutation_of_an_active_version`, parametrised over
all four content columns, plus a tenant-reparenting case).

### 2.5 Duplicate activation, run live three times — PASS

```
audit rows for this skill BEFORE any activation: 0
activate #1 -> HTTP 200  | activated audit rows now: 1
activate #2 -> HTTP 200  | activated audit rows now: 1
activate #3 -> HTTP 200  | activated audit rows now: 1
activated_at unchanged across calls: 2026-08-26 14:49:12.17059+00
```

Count does not grow; `activated_at` does not move.

---

## 3. Isolation — verified by attack

Target: a **real, existing** ABC skill id. Control: a nonexistent UUID.

| Attack (as XYZ Builders owner) | Result |
|---|---|
| `GET /skills/{abc_id}` | **404** |
| `GET /skills/{nonexistent}` | **404** |
| `PATCH /skills/{abc_id}` | **404** |
| `POST /skills/{abc_id}/versions` | **404** |
| `POST /skills/{abc_id}/disable` | **404** |
| `POST /skills/{abc_id}/versions/1/review` | **404** |
| `POST /skills/{abc_id}/versions/1/activate` | **404** |
| `POST .../activate` as ABC **member** | **403** `NOT_ORG_OWNER` |

**No existence oracle.** The two 404 bodies were compared programmatically after
blanking the echoed id: `INDISTINGUISHABLE apart from the echoed id: True`. The
only difference is the `skill_id` the client itself supplied.

Post-attack state check confirmed nothing changed: `{"status":"active",
"description":"","versions":[{"version_number":1,"status":"active"}]}`.

### 3.5 `organization_id` injection — PASS

| Vector | Result |
|---|---|
| body on `POST /skills` | **422** `VALIDATION_ERROR` |
| body on `PATCH /skills/{id}` | **422** `VALIDATION_ERROR` |
| `?organization_id=` on `GET /skills` | 200, **ignored** — returned only ABC's org id |
| `?organization_id=` on `GET /audit` | 200, **ignored** — returned only ABC's org id |
| `X-Organization-Id` header | **ignored** — returned only ABC's org id |

Matches the spec's "ignore it (or 422 it)".

### 3.6 No cross-org endpoint — PASS

Enumerated **every** registered route from the app object, not just the OpenAPI
document (18 total). The only routes hidden from OpenAPI are FastAPI's own
`/openapi.json`, `/docs`, `/docs/oauth2-redirect`, `/redoc`. No list-all, no
admin, no organizations route.

---

## 4. Database-level guarantees

### 4.1 `UPDATE skill_versions … WHERE status='active'` — PASS

As app role **and** as schema owner:

```
ERROR:  skill_versions da877f04-…: the content of an ACTIVE version is immutable;
        create a new version instead
CONTEXT:  PL/pgSQL function skill_versions_forbid_active_mutation() line 8 at RAISE
```

Rows affected afterwards: `0`.

### 4.2 Second `active` row for one skill — PASS

```
ERROR:  duplicate key value violates unique constraint "uq_skill_versions_one_active_per_skill"
DETAIL:  Key (skill_id)=(17123f05-…) already exists.
```

### 4.3 `UPDATE` / `DELETE` on `audit_log` — PASS, with one gap

```
as jarvis_app  : ERROR:  permission denied for table audit_log     (UPDATE)
as jarvis_app  : ERROR:  permission denied for table audit_log     (DELETE)
as jarvis_owner: ERROR:  audit_log is append-only; UPDATE is not permitted
as jarvis_owner: ERROR:  audit_log is append-only; DELETE is not permitted
as jarvis_app  : ERROR:  permission denied for table audit_log     (TRUNCATE)
target row still present afterwards: count = 1
```

**PARTIAL — finding.** `TRUNCATE audit_log` **succeeds for the schema-owner role**:

```
BEGIN; TRUNCATE audit_log; SELECT count(*) → 0; ROLLBACK;
```

`trg_audit_log_append_only` is a **ROW-level** trigger, and `TRUNCATE` does not
fire row triggers. Confirmed:

```
          tgname           | fires_on_truncate | level
---------------------------+-------------------+-------
 trg_audit_log_append_only |                   | ROW
```

The application role — the one reachable from the network — is fully blocked by
the `TRUNCATE` revocation. The gap is only reachable by the migration/owner role.
But **`ARCHITECTURE.md:140` overstates it**: "tampering fails on privileges for
the app and on the trigger for everyone else, **including the owner**." That is
true for UPDATE/DELETE and false for TRUNCATE. Fix is a statement-level
`BEFORE TRUNCATE` trigger (~6 lines in a new migration).

### 4.4 Tenant columns in the live schema — PASS

From `information_schema`, not the model files:

```
   table_name   |   column_name   | is_nullable | data_type |                     fk_name                     |  references
----------------+-----------------+-------------+-----------+-------------------------------------------------+---------------
 audit_log      | organization_id | NO          | uuid      | fk_audit_log_organization_id_organizations      | organizations
 skill_versions | organization_id | NO          | uuid      | fk_skill_versions_organization_id_organizations | organizations
 skills         | organization_id | NO          | uuid      | fk_skills_organization_id_organizations         | organizations
 tool_grants    | organization_id | NO          | uuid      | fk_tool_grants_organization_id_organizations    | organizations
 users          | organization_id | NO          | uuid      | fk_users_organization_id_organizations          | organizations
```

All five NOT NULL with a foreign key to `organizations`.

---

## 5. Tool permission boundary

### 5.1 Four dangerous tools, submitted individually — PASS

```
  shell_exec   -> HTTP 422  FORBIDDEN_TOOL_PATTERN | destructive capability
  rm -rf       -> HTTP 422  FORBIDDEN_TOOL_PATTERN | whitespace
  drop_table   -> HTTP 422  FORBIDDEN_TOOL_PATTERN | destructive capability
  *            -> HTTP 422  FORBIDDEN_TOOL_PATTERN | wildcard
```

`Probe* skills created: 0` — a rejected tool creates nothing at all.

### 5.2 Valid tool stored ungranted — PASS

```
     tool_name      | granted | granted_by | granted_at
--------------------+---------+------------+------------
 read_invoice       | f       |            |
 summarise_document | f       |            |
```

Whole-table check: `granted_true_with_null_grantor=0`. Live column default:
`granted default=false nullable=NO`.

### 5.3 Only one code path sets `granted = True` — PASS

`app/services/skills.py:280`, inside `grant_tools`, which at line 5 of the method
resolves the version through the scoped repository (404 if invisible) and at line
6 calls `self._require_owner("grant tools")` (403). There is no other assignment
to `.granted` in `app/`.

---

## 6. Audit log completeness

### 6.1 One full workflow, every row — PASS (with a design note)

```
          event          | org | actor | skill | version_id | version_number
-------------------------+-----+-------+-------+------------+----------------
 skill.created           | t   | t     | t     | f          |
 skill_version.created   | t   | t     | t     | t          |              1
 skill_version.reviewed  | t   | t     | t     | t          |              1
 skill_version.activated | t   | t     | t     | t          |              1
```

Whole-table checks: `rows_missing_org_or_actor_or_event=0` and
`version_events_missing_version_number=0`.

**Design note:** `skill.created` has a null `version_number` / `skill_version_id`
because it is a skill-level event that does not refer to a version. Every
`skill_version.*` event has both populated. This is deliberate, not a gap, but it
means "every audit row has a version_number" is not literally true.

### 6.2 Audit and state share one transaction — PASS, proved empirically

Static: every state-changing method has exactly **one** `repo.commit()`, with its
audit records added before it. `AuditRecorder.record()` contains no `commit` or
`flush` — it only adds to the unit of work.

| method | `audit.record()` | `repo.commit()` |
|---|---|---|
| `create_skill` | 2 | 1 |
| `update_skill` | 1 | 1 |
| `create_version` | 1 | 1 |
| `review_version` | 1 | 1 |
| `grant_tools` | 1 | 1 |
| `disable_skill` | 2 | 1 |
| `activate` | 2 | 1 |

Empirical: Postgres assigns the same `xmin` to rows written by the same
transaction.

```
 skill_version_xmin | audit_row_xmin | same_transaction
--------------------+----------------+------------------
 1106               | 1106           | t
```

The state change and its audit row are literally the same transaction. A crash
between them is not possible.

---

## 7. Secrets and hygiene — PASS

### 7.1 Full-history grep

`git log -p | grep -iE "(secret|password|api[_-]?key|token)\s*="` returns 16
unique lines. Every one classified:

| Line | Verdict |
|---|---|
| `POSTGRES_PASSWORD=replace-me-owner-password` | `.env.example` placeholder |
| `APP_DB_PASSWORD=replace-me-app-password` | `.env.example` placeholder |
| `JWT_SECRET=replace-me-with-a-long-random-string` | `.env.example` placeholder |
| `SEED_PASSWORD=replace-me-seed-password` | `.env.example` placeholder |
| `PGPASSWORD=dev-only-not-a-secret` (×2) | README docs, dev-only value |
| `TEST_PASSWORD = "test-only-not-a-secret"` | test constant |
| `_HASHED_TEST_PASSWORD = hash_password(...)` | test constant |
| `hashed_password=...` (×2) | source code |
| `INVALID_TOKEN = "INVALID_TOKEN"` | error-code constant |
| `owner_token=` / `member_token=` / `token = create_access_token(` / `access_token=` | source code |

No real secret. No credential to any real system.

### 7.2 `.env` — PASS

`git log --all --full-history -- .env` → **empty** (never committed). Not tracked.
Not present on disk. `git check-ignore -v .env` → `.gitignore:28:.env`.

### 7.3 `.gitignore` coverage — PASS

All ignored: `.env`, `.env.local`, `__pycache__/`, `*.pyc`, `.pytest_cache/`,
`.coverage`, `htmlcov/`, `.venv/`, `*.egg-info/`. Docker state uses a **named
volume** (`pgdata`), not a bind mount, so there is no local volume directory to
ignore — confirmed none exists in the repo.

---

## 8. Git discipline

### 8.1 Commit count — PARTIAL

**28 commits** (29 including this audit) against the brief's stated target of
**15–25**. Over by 3–4.

Mitigating: the log is genuinely incremental and tells the build story in order.
Median commit is 3 files. Largest is `b68e722` at **10 files / 1455 insertions** —
the test suite landing in one commit. A reviewer could fairly call that one drop
too large. Cannot be corrected without rewriting history, which this pass is
forbidden from doing.

Full log: `08f75d5` gitignore → core → models → repository → schemas → services →
api → alembic → seed → tests → docs → report. No squashing, no `wip`, no `fix
typo` noise.

### 8.2 No real client data — PASS

No match for `millionaze|defaultpathway|closerintelligence|hermes|ghl|acme|client`
in any commit message. The only organization names anywhere in tracked files are
the two fixture orgs from the spec (ABC Construction, XYZ Builders), in
`app/seed.py`, `tests/conftest.py`, and the three docs.

---

## 9. Deliverables

| File | Size | Verdict |
|---|---|---|
| `README.md` | 537 lines | PASS — 26 curl commands, 17-step walkthrough, seeded credentials table, migration commands, known limitations |
| `ARCHITECTURE.md` | 235 lines | PASS — 7 sections, each ending in an explicit `**Trade-off.**` paragraph; covers 404-vs-403, the three-layer table, and the request/grant split |
| `TEST_OUTPUT.md` | 191 lines | PASS — matches the fresh run (§2.1) |
| `.env.example` | 19 lines | PASS — placeholders only |
| `docker-compose.yml` | 54 lines | PASS — `api` + `db`, healthchecks, named volume |
| `REPORT.md` | 255 lines | PASS — all 12 template fields present in order; exactly 3 `<FILL IN>` markers (Start time, Finish time, Approximate hours) |

Known-limitations section is present and specific: no RLS, no rate limiting, no
refresh tokens/rotation, no pagination, no soft delete/restore, no separation of
duties on review, single region, allowlist is a code constant, dev credentials in
compose.

---

## 10. Scope discipline — PASS, with two small additions

Confirmed **absent**: any frontend asset (`*.html/js/jsx/tsx/css/package.json` —
none), any external AI/model API, any third-party auth provider. Dependency list
is 14 packages, all framework/driver/test. No outbound network call anywhere in
`app/` (`requests|httpx.get|urllib|openai|anthropic|boto3|auth0|okta|clerk|firebase`
→ none).

Two endpoints exist beyond the brief's listed API surface:

* `GET /health` — required by the compose healthcheck; infrastructure, not feature.
* `GET /auth/me` — used by the README walkthrough and the auth tests to show which
  organization a token resolves to. Small, but strictly an addition.

Also beyond the literal brief, and in my view earning its place: `db/init/` creates
a second Postgres role, which is what makes the required "revoke UPDATE/DELETE on
audit_log from the app role" actually bind rather than be decorative.

One response header, `X-Activation-Changed`, was added so idempotent replay is
observable. Documented, but an addition.

---

## 11. Additional adversarial probes (not in the checklist)

I ran concurrency probes because the brief's activation rules are race-sensitive.

### 11.1 Concurrent activation of two different versions — PASS

Both requests returned **200**, and the database ended with **exactly 1** active
version. The `SELECT … FOR UPDATE` lock in `SkillRepository.lock_skill` serialised
them. No 500.

### 11.2 Concurrent version creation (5 simultaneous) — PASS

Version numbers assigned `2 3 4 5 6` — `rows=6 distinct_numbers=6`. No duplicates,
no errors. The row lock holds.

### 11.3 Concurrent tool grants on one version — PASS

Three simultaneous grants → `granted=3/3`. No lost update.

### 11.4 Concurrent creation of the same skill name — **FAIL**

```
  attempt1 -> HTTP 500   INTERNAL_ERROR
  attempt2 -> HTTP 500   INTERNAL_ERROR
  attempt3 -> HTTP 201   created
  rows actually created: 1
```

**This is a real bug.** `SkillService.create_skill` (`app/services/skills.py:108`)
does a check-then-insert with **no row lock** — unlike `create_version:174`, which
locks first. Under concurrency the `uq_skills_organization_id_name` constraint
fires an `IntegrityError`, which is handled **nowhere** in `app/` (`grep -rn
IntegrityError app/` → no match) and falls through to the catch-all 500 handler.

Severity assessment, honestly:

* **Data integrity is not harmed** — the database constraint did its job; exactly
  one row was created, never two.
* **Nothing leaks** — the response is the opaque `INTERNAL_ERROR` envelope; the
  traceback goes to the server log only, as designed.
* **But the status code is wrong.** A condition with a dedicated `409
  SKILL_NAME_CONFLICT` code returns 500 instead, and a client cannot distinguish
  "someone beat you to that name" from "the server is broken".
* It also mildly undercuts the "one consistent error envelope with machine-readable
  codes" claim, since this path produces the wrong code.

Fix is small: catch `IntegrityError` on that constraint in `create_skill` and
re-raise as `ConflictError(SKILL_NAME_CONFLICT)`, or take the same lock pattern
`create_version` already uses. Either way it needs a regression test.

### 11.5 `JWT_SECRET` really has no default — PASS

Ran the image with `DATABASE_URL` set and `JWT_SECRET` absent:

```
PASS: refused to start -> ValidationError
1 validation error for Settings  jwt_secret  Field required [type=missing, ...]
```

---

## Summary table

| Item | Status | Evidence |
|---|---|---|
| 1.1 Fresh `up --build`, zero manual steps | PASS | both containers Healthy, exit 0 |
| 1.2 `/openapi.json`, `/docs` | PASS | HTTP 200, 12 paths |
| 1.3 Migrations from clean DB | PASS | `0002_db_level_guarantees (head)`, no errors |
| 1.4 Seed proven by DB query | PASS | 2 orgs, 4 users, bcrypt hashes; idempotent |
| 2.1 `TEST_OUTPUT.md` matches fresh run | PASS | diff = 1 line (duration only) |
| 2.2 All 13 mandatory tests present | PASS | mapped table, §2.2 |
| 2.3 No fake-test patterns | PASS | no skip/xfail/`assert True`/swallowed except |
| 2.3b One test has no assertion | **PARTIAL** | `test_lifecycle_edges.py:24` |
| 2.4 Immutability: API *and* raw SQL tests | PASS | 3 layers tested separately |
| 2.5 Duplicate activation idempotent (live) | PASS | audit count 1→1→1 |
| 3.1 Cross-org read | PASS | 404, indistinguishable from nonexistent |
| 3.2 Cross-org update | PASS | 404 on PATCH/versions/disable/review |
| 3.3 Cross-org activation | PASS | 404 `SKILL_NOT_FOUND` |
| 3.4 Member activation | PASS | 403 `NOT_ORG_OWNER` |
| 3.5 `organization_id` injection | PASS | 422 in body; ignored in query/header |
| 3.6 No cross-org endpoint | PASS | all 18 routes enumerated |
| 4.1 Trigger blocks active mutation | PASS | raises for app role *and* owner |
| 4.2 Partial unique index | PASS | `uq_skill_versions_one_active_per_skill` |
| 4.3 `audit_log` UPDATE/DELETE blocked | PASS | privilege + trigger |
| 4.3b `TRUNCATE audit_log` by owner | **PARTIAL** | row trigger doesn't fire on TRUNCATE; doc overstates |
| 4.4 Tenant columns NOT NULL + FK | PASS | 5/5 from `information_schema` |
| 5.1 Four dangerous tools rejected | PASS | 4× 422, nothing created |
| 5.2 `granted=false` stored | PASS | direct query; default `false` NOT NULL |
| 5.3 One owner-gated grant path | PASS | `skills.py:280` behind `_require_owner` |
| 6.1 Audit rows populated | PASS | 0 rows missing org/actor/event |
| 6.2 Audit in same transaction | PASS | identical `xmin` |
| 7.1 No secrets in history | PASS | 16 lines, all classified |
| 7.2 `.env` never committed | PASS | empty history, gitignored |
| 7.3 `.gitignore` coverage | PASS | 9/9 patterns |
| 8.1 Commit count 15–25 | **PARTIAL** | 28 (29 w/ audit); largest 10 files/1455 lines |
| 8.2 No real client data | PASS | fixture orgs only |
| 9 Deliverables non-trivial | PASS | all 6 present and substantial |
| 10 Scope discipline | PASS | no frontend/AI/auth vendor; 2 small extra endpoints |
| 11.4 Concurrent same-name create | **FAIL** | 500 `INTERNAL_ERROR` instead of 409 |
| 11.5 `JWT_SECRET` no default | PASS | ValidationError on startup |

---

## Would cause automatic rejection if submitted as-is

**None.** Checked against each stated rejection criterion:

* **Committed secret** — no. Full-history grep classified line by line; `.env`
  never committed.
* **Cross-tenant leakage** — no. Every cross-org read, write and activation
  returns 404, and the 404 bodies are indistinguishable from a nonexistent id.
* **Fake tests** — no. No skips, no `assert True`, no swallowed exceptions; the
  isolation suite was mutation-tested during the build and fails when the tenancy
  filter is removed.
* **App fails to start** — no. Clean `down -v && up --build` reaches healthy in
  ~6 seconds with zero manual steps.
* **Active skill silently mutable** — no. Blocked at three layers, and the DB
  trigger fires even for the schema owner.

## Would cost points but not fail

1. **`create_skill` returns 500 instead of 409 under a concurrent same-name race**
   (`app/services/skills.py:108`). The only genuine bug found. Data integrity is
   preserved by the unique constraint and nothing leaks, but the status code is
   wrong and `IntegrityError` is unhandled anywhere in `app/`. `create_version`
   already does this correctly with a row lock.
2. **`TRUNCATE audit_log` succeeds for the schema-owner role** — the append-only
   trigger is ROW-level and TRUNCATE does not fire row triggers. The network-facing
   app role is blocked by the revocation, so this is reachable only by the trusted
   migration role. **`ARCHITECTURE.md:140` overstates the guarantee** by saying
   tampering fails "for everyone else, including the owner".
3. **28 commits against a stated target of 15–25**, and one commit (`b68e722`,
   10 files / 1455 insertions) is noticeably larger than the rest.
4. **`test_the_application_lifespan_starts_and_stops_cleanly` has no assertion** —
   a bare smoke test among 143 that all assert properly.
5. **Two endpoints beyond the listed API surface** (`GET /health`, `GET /auth/me`)
   and one extra response header (`X-Activation-Changed`). Each defensible, but a
   strict reviewer counts them as additions.
6. **`skill.created` audit rows carry a null `version_number`** — correct by design
   for a skill-level event, but it means the blanket claim "every audit row has a
   version number" is not literally true.

## Note on fixing any of the above

`REPORT.md` cites specific commit SHAs and `TEST_OUTPUT.md` is a verbatim run.
Any code fix invalidates both: they would need regenerating, and the "Final commit
SHA" line would move again. That is a reason to decide deliberately, not a reason
to leave a real bug in.
