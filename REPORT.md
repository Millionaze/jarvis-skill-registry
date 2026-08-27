```
Repository URL:
https://github.com/Millionaze/jarvis-skill-registry  (private)

Start time:
2026-08-26 19:08 PKT (UTC+5)

Finish time:
2026-08-27 00:30 PKT (UTC+5)

  This window records my own oversight of the build and the self-audit. Later
  commits on the branch are a polish pass (lint/type gate, the evidence map, the
  demo script, the lifecycle diagram) and are excluded from the figure above.

Approximate hours:
~5.5 hours

Final commit SHA:
61e44e2a3a70c940ff03d20f3b75bb690a57b36e

  A commit cannot contain its own hash, so if a later commit adds this report
  the tip will be one ahead. `git rev-parse origin/main` is authoritative.

Goal achieved:
Yes - complete and verified end to end.

A multi-tenant, organization-scoped registry for AI COO skills: FastAPI (async)
on Python 3.12, PostgreSQL 16 with SQLAlchemy 2.0 (asyncpg) and Alembic, Pydantic
v2 throughout, pytest + httpx against a real database. `docker compose up --build`
from a clean state brings the stack up with zero manual steps - the api container
waits for Postgres to be healthy, applies all three migrations, seeds ABC
Construction and XYZ Builders with an owner and a member each, then serves on
:8080. Verified from scratch with `docker compose down -v && docker compose up
--build`: the container reported healthy 6 seconds after start, and the full
suite passed against that fresh instance.

The whole workflow works and is documented as a runnable curl walkthrough in
README.md - 17 steps, every one executed against a freshly built stack before
being written down: authenticate -> create skill draft -> review -> owner
activates -> retrieve active skill -> exact version recorded in the audit log by
version number and content hash.

Two things make the submission fast to verify:

  * EVALUATION_MAP.md maps every requirement - the six scoring categories, the 13
    mandatory tests, the 9 restrictions and the 5 automatic-rejection risks - to
    the exact file, line or test function that proves it. All 66 line references
    in it were checked programmatically against the source, not written by hand.
  * `./scripts/demo.sh` runs the full lifecycle against the live stack and then
    attacks it five ways, printing the request, the real status and a PASS/FAIL
    verdict at each point - 19 numbered steps carrying 27 assertions, about
    twenty seconds. It exits non-zero if any assertion fails, so the exit code
    is the verdict on its own.

After the build I ran a deliberately adversarial self-audit against a stack
rebuilt from scratch, trying to fail the work rather than defend it. It found
three defects, all fixed with regression tests:

  1. Concurrent POST /skills with the same name returned 500 rather than 409. The
     pre-check in create_skill had been treated as the guarantee; it is only a
     fast path, and two concurrent requests can both pass it. Data was never at
     risk - uq_skills_organization_id_name kept it to one row - but the status
     code was wrong and IntegrityError was unhandled anywhere in the app. Fixed
     by translating that constraint into the same 409, plus a global
     IntegrityError handler so no future constraint violation can reach a client
     as an internal error.
  2. TRUNCATE on audit_log succeeded for the schema-owner role, because
     PostgreSQL does not fire ROW triggers for TRUNCATE. "Append-only" was
     therefore true for UPDATE and DELETE and false for TRUNCATE. Fixed by
     migration 0003, a statement-level BEFORE TRUNCATE trigger; the overstated
     sentence in ARCHITECTURE.md was corrected rather than quietly patched.
  3. The application-lifespan smoke test had no assertion. Given one.

Architecture decisions:
Written up with trade-offs in ARCHITECTURE.md, which also carries a mermaid state
diagram showing where the immutability boundary sits. In brief:

  * PostgreSQL, because the invariants worth protecting are data invariants. One
    active version per skill, immutable active content and an append-only audit
    log are enforced by the database itself, so they survive a bug in the
    service, a future second writer, or an operator with psql.
  * organization_id as the canonical ownership key on every tenant table,
    denormalised onto skill_versions and tool_grants on purpose. Every table is
    scoped by the same single predicate with no join, so there is no query that
    is only safe because someone remembered to join.
  * 404 over 403 for cross-tenant access, because a 403 confirms a row exists and
    turns the status code into an existence oracle. Resources outside the
    caller's organization are not forbidden, they are invisible: the scoped
    repository filters before the row is fetched, so the service genuinely does
    not know. 403 is reserved for the case where the caller CAN see the resource
    and the role is insufficient - a member activating. The ordering (resolve,
    then role, then state) is written identically in every service method.
  * Three-layer immutability, because each layer has a different bypass: the API
    has no mutating route (bypassed by anything not going through HTTP), a
    SQLAlchemy before_update listener (bypassed by raw SQL), and a PL/pgSQL
    BEFORE UPDATE trigger (bypassed by nothing short of dropping it). All three
    agree on one definition of "content", named once in
    SkillVersion.CONTENT_COLUMNS and mirrored in the trigger.
  * Tool requests decoupled from grants, because the person who writes a prompt
    and the person who widens an agent's blast radius should not be the same act.
    `granted` defaults to false in the model, the migration and the column's
    server default; granting is separate, owner-only and individually audited;
    runtime selection reads granted tools only.
  * Self-contained HS256 JWT, scoped for this evaluation and replaced by the
    platform IdP in production - the rest of the system only asks authentication
    for a user with an organization_id and a role, produced by one dependency.
    JWT_SECRET has no default, so a deployment that omits it fails at startup.
    The token is not trusted alone: the (user, organization) pair is re-checked
    against the database on every request and role is read from the row, so a
    forged org claim or a self-promoted role claim buys nothing.
  * Services cannot express an unfiltered query. They reach the database only
    through ScopedRepository, which is constructed with an organization id and
    exposes no raw session and no unscoped select. The single deliberate
    exception, the pre-authentication user lookup, is named UnscopedAuthRepository
    so its unscoped-ness is greppable rather than accidental.

Tests passed:
============================= 153 passed in 28.03s =============================

100% statement coverage of 969 statements across all 36 modules under app/,
with nothing omitted from the report. Raw, unedited output of `docker compose run --rm api
pytest -v --cov=app --cov-report=term-missing` is in TEST_OUTPUT.md.

All 13 mandatory tests exist as separate functions and pass:
   1. test_isolation.py::test_same_org_create_then_read_succeeds
   2. test_isolation.py::test_cross_org_read_returns_404_not_403
   3. test_isolation.py::test_cross_org_update_is_denied
   4. test_isolation.py::test_cross_org_activation_is_denied_with_404
   5. test_activation.py::test_member_cannot_activate_and_gets_403
   6. test_runtime_selection.py::test_a_draft_skill_never_loads_as_active
   7. test_runtime_selection.py::test_a_disabled_skill_is_excluded_from_runtime_selection
   8. test_immutability.py::test_no_route_exists_to_mutate_a_version (API),
      ::test_orm_guard_blocks_mutation_of_an_active_version (application), and
      ::test_db_trigger_blocks_raw_sql_mutation_of_an_active_version (raw SQL)
   9. test_activation.py::test_duplicate_activation_is_idempotent_and_writes_no_duplicate_audit
  10. test_tools.py::test_an_unknown_tool_is_rejected_with_422,
      ::test_a_destructive_or_malformed_tool_is_rejected_with_422,
      ::test_a_requested_tool_is_never_auto_granted
  11. test_audit.py::test_an_audit_record_carries_organization_actor_event_and_version_number
  12. test_immutability.py::test_only_one_active_version_per_skill_is_possible
  13. test_errors.py::test_validation_failures_return_422_with_the_validation_error_code

Nothing is faked. There is no `assert True`, no skip or xfail, no commented-out
assertion, no swallowed exception, and the authorization layer is never mocked -
overriding it would delete the thing under test. The only substitution is the
database session, swapped for one bound to a transaction that is rolled back
after each test, so the application's own commits are real: triggers fire,
constraints are checked, audit rows land.

The isolation suite was mutation-tested: with the tenancy predicate removed from
ScopedRepository.select(), 6 tests fail (cross-org read, cross-org update,
cross-org activation, listing, per-tenant name uniqueness, audit scoping) and
pass again once it is restored. The tests detect the failure they claim to.

`ruff check .` reports "All checks passed!" and `mypy app/` reports "Success: no
issues found in 36 source files", both run in the same container as the tests.
There are no blanket ignores; five findings are suppressed individually, each
with an inline comment naming the rule and the reason.

Security/isolation evidence:

Tenant isolation - every pointer below is in EVALUATION_MAP.md with a line number
  * app/api/deps.py:31 get_current_user is the only source of tenancy. It reads
    the signed org claim, then re-validates the (user, organization) pair against
    the database via UnscopedAuthRepository.get_user_in_organization
    (app/db/repository.py:196).
  * app/db/repository.py:34 ScopedRepository - every statement is built by
    select() (:54) / owned() (:47), which bake in
    organization_id == <token's org>. add() (:85) overwrites any organization_id
    on an incoming object rather than trusting it.
  * Cross-tenant rows are invisible, not forbidden: require() (:64) raises 404,
    so a 403 can never confirm another tenant's row exists.
  * app/schemas/common.py:8 StrictModel sets extra="forbid", so a smuggled
    organization_id is a 422, not a silently ignored field.
  * Forged tokens: test_token_tampering.py::test_a_token_claiming_another_organization_is_rejected
    and ::test_a_self_promoted_role_claim_does_not_grant_owner_powers.
  * Structural enforcement: test_structure.py::test_no_service_builds_an_unscoped_query
    scans every module under app/services for select(, session.execute,
    session.add and engine construction;
    ::test_no_request_schema_accepts_an_organization_id walks the generated
    OpenAPI document; ::test_there_is_no_cross_tenant_escape_hatch asserts the
    role set is exactly {owner, member} and that no /admin, /organizations or
    list-all route exists.
  * Verified by attack, not only by test: all 18 registered routes were
    enumerated (not just the documented ones) and none reads across tenants; the
    404 body for a real other-tenant id is byte-identical to one for a
    nonexistent id apart from the id the caller supplied, so there is no
    existence oracle.

Database constraints and triggers, by name
  * trg_skill_versions_immutable_active (function
    skill_versions_forbid_active_mutation, alembic 0002) - BEFORE UPDATE on
    skill_versions. Raises 23514 if the row was ACTIVE and prompt_body,
    requested_tools, content_hash or version_number changes; if organization_id
    or skill_id changes; or if status leaves 'active' for anything but
    'superseded' or 'disabled'. Proved by raw SQL, one case per content column:
    test_immutability.py::test_db_trigger_blocks_raw_sql_mutation_of_an_active_version
    plus ::test_db_trigger_blocks_raw_sql_reassignment_of_an_active_version_to_another_org.
    ::test_db_trigger_permits_the_legal_supersede_transition proves the guard is
    not so blunt that the lifecycle stops working.
  * uq_skill_versions_one_active_per_skill (alembic 0002) - partial unique index
    on skill_versions (skill_id) WHERE status = 'active'. Proved by
    test_immutability.py::test_only_one_active_version_per_skill_is_possible,
    which reads the index definition out of pg_indexes, then forces a second
    active row and asserts the constraint name in the error.
  * trg_audit_log_append_only (function audit_log_forbid_mutation, alembic 0002)
    - BEFORE UPDATE OR DELETE on audit_log, always raises. Plus
    REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM jarvis_app. The API
    connects as jarvis_app, a non-owning role, precisely so the revocation binds
    - a table owner would bypass the privilege check.
  * trg_audit_log_no_truncate (alembic 0003, same function) - statement-level
    BEFORE TRUNCATE, because row triggers do not fire on TRUNCATE. Proved on a
    dedicated schema-owner connection by
    test_audit.py::test_the_audit_log_cannot_be_truncated_even_by_the_schema_owner.
  * uq_skills_organization_id_name - skill names are tenant-local, not global.
  * uq_skill_versions_skill_id_version_number - monotonic version numbering,
    backstopping the FOR UPDATE row lock in SkillRepository.lock_skill.
  * tool_grants.granted - NOT NULL, server_default false, so no code path can
    create a pre-granted row.

Audit integrity
  * Every state-changing method has exactly one repo.commit(), with its audit
    records added before it; AuditRecorder.record() never commits. Proved
    empirically rather than argued: the state row and its audit row share the
    same PostgreSQL xmin, which is transaction identity.
  * test_audit.py::test_a_failed_state_change_writes_no_audit_row confirms the
    converse - a rejected change writes nothing.

Error hygiene
  * One envelope everywhere: {"error": {"code", "message", "detail"}}, with
    machine-readable codes and handlers for validation, domain, HTTP and
    unexpected errors.
  * test_error_handlers.py::test_an_unexpected_error_becomes_an_opaque_500 raises
    a RuntimeError containing a fake connection string and asserts the response
    contains no traceback, no exception class and no connection string.

Known limitations:
Listed in full in README.md, grouped by kind. The ones that matter:

  * No PostgreSQL row-level security. Isolation is enforced by the repository and
    proved by tests, not by the database. RLS policies keyed on organization_id,
    with a per-request SET LOCAL app.organization_id, would make the guarantee
    hold even for a future service that bypasses the repository. This is the
    natural next step beyond the triggers - they protect immutability, RLS would
    protect tenancy - and the schema is already shaped for it.
  * No rate limiting or brute-force protection on login.
  * No refresh tokens, no revocation list, no key rotation. HS256 with one shared
    secret; a stolen token is valid for its 60-minute lifetime. Deleting the user
    does kill it, because the (user, org) pair is re-checked per request, but
    that is a side effect rather than a revocation mechanism.
  * No structured logging, tracing or metrics. Plain-text logs to stdout, no
    request id emitted, no spans, no counters on activation or denial rates.
  * The audit write is same-transaction but there is no outbox. A state change
    and its audit row commit or roll back together, which is the important half,
    but there is no outbox table, no CDC and no retry, so a downstream consumer
    (SIEM, warehouse, compliance archive) has no reliable way to be notified.
  * No pagination anywhere. GET /skills returns everything; GET /audit is capped
    at 500 rows with no cursor.
  * No soft delete or restore. `disable` is one-way; there is no `enable`.
  * No separation of duties on review - a version's author may review it.
  * The tool allowlist is a code constant, so adding a tool needs a deploy.
  * Single region, single writer. No replicas, no partitioning, and audit_log
    grows forever with no retention policy.
  * Concurrency is not covered in the automated suite. The pytest harness is
    single-connection by design, so parallel requests cannot be expressed in it.
    Parallel activation, version creation and tool grants were exercised by hand
    against a live stack - the FOR UPDATE lock held in every case - and the one
    race found that way is now covered by a deterministic regression test.
  * docker-compose.yml carries dev-only placeholder credentials behind
    ${VAR:-...} fallbacks so the stack starts with zero steps. .env.example holds
    placeholders only, .env was never committed, and the application has no
    default for JWT_SECRET.

What I would implement next:
In the order I would actually do it.

  1. PostgreSQL row-level security as a second, independent enforcement of what
     the repository already enforces, so isolation survives a future service that
     talks to this database without going through ScopedRepository.
  2. A composite foreign key (skill_id, organization_id) from skill_versions to a
     matching unique key on skills, closing the last theoretical gap in the
     denormalised organization_id - today a version's org can only be wrong via a
     bug in one method, but the database cannot yet rule it out.
  3. Replace the self-contained JWT with the platform IdP (OIDC/JWKS, asymmetric
     keys, rotation, refresh). It is a change to one dependency function.
  4. Separation of duties on review: reviewer must not be the version's author.
  5. Cursor pagination and filtering on GET /skills and GET /audit, plus a
     retention and archival policy for audit_log.
  6. Concurrency tests inside the suite, which needs a second harness that
     commits rather than rolls back.
  7. An outbox table written in the same transaction as the audit row, drained
     separately, so downstream consumers get a reliable feed.
  8. Structured JSON logging with the correlation id already on request.state,
     plus metrics on activation and denial rates; and rate limiting on login.
  9. Per-tenant, data-driven tool allowlists, themselves versioned and audited,
     so adding a tool is an owner action rather than a deploy.
 10. An enable/restore path for disabled skills, and a redaction workflow for
     audit entries that must legally disappear - append-only is right until GDPR
     disagrees.

AI tools used, if any:
Claude Code
```
