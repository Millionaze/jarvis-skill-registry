```
Repository URL:
https://github.com/Millionaze/jarvis-skill-registry (private)

Start time:
<FILL IN>   (first commit 08f75d5, authored 2026-08-26T14:08:17Z)

Finish time:
<FILL IN>

Approximate hours:
<FILL IN>

Final commit SHA:
fd78ee6ad337840f679a0317852a3fb966750db1   (the commit that added this report)

  A commit cannot contain its own hash, so this line was written by the single
  commit that follows it. That commit is the current tip of `main` and changes
  nothing but these four lines; `git rev-parse origin/main` is authoritative.
  The complete implementation, tests and documentation were finished at
  948fb7038054e4b385cc8730618f76fc120409d8, 26 commits in.

Goal achieved:
Yes - complete and verified end to end.

A multi-tenant, organization-scoped skill registry: FastAPI (async) on Python
3.12, PostgreSQL 16 with SQLAlchemy 2.0 (asyncpg) and Alembic, Pydantic v2
throughout, pytest + httpx against a real database. `docker compose up --build`
from a clean state brings up the stack with zero manual steps: the api container
waits for Postgres to be healthy, applies both migrations, seeds ABC Construction
and XYZ Builders with an owner and a member each, and serves on :8080. Verified
from scratch with `docker compose down -v && docker compose up --build` - the api
container reported healthy 6 seconds after start, and every one of the 144 tests
passed against that fresh instance.

The full workflow works and is documented as a runnable curl walkthrough in
README.md (17 steps, every one executed against a freshly built stack before
being written down): authenticate -> create skill draft -> review -> owner
activates -> retrieve active skill -> exact version recorded in the audit log by
version number and content hash.

Architecture decisions:
Written up with trade-offs in ARCHITECTURE.md. In brief:

* PostgreSQL, because the invariants worth protecting are data invariants. One
  active version per skill, immutable active content and an append-only audit log
  are all enforced by the database itself, so they survive a bug in the service,
  a future second writer, or an operator with psql.
* `organization_id` as the canonical ownership key on every tenant table,
  denormalised onto `skill_versions` and `tool_grants` on purpose. Every table is
  scoped by the same single predicate with no join, so there is no query that is
  only safe because someone remembered to join.
* 404 over 403 for cross-tenant access, because a 403 confirms a row exists and
  turns the status code into an existence oracle. Resources outside the caller's
  organization are not forbidden, they are invisible: the scoped repository
  filters before the row is fetched, so the service genuinely does not know. 403
  is reserved for the case where the caller CAN see the resource and the role is
  insufficient (a member activating). The ordering - resolve, then role, then
  state - is written identically in every service method and is pinned by tests.
* Three-layer immutability, because each layer has a different bypass: the API
  has no mutating route (bypassed by anything not going through HTTP), a
  SQLAlchemy `before_update` listener (bypassed by raw SQL), and a PL/pgSQL
  BEFORE UPDATE trigger (bypassed by nothing short of dropping it). All three
  agree on one definition of "content", named once in
  `SkillVersion.CONTENT_COLUMNS` and mirrored in the trigger.
* Tool requests decoupled from grants, because the person who writes a prompt and
  the person who widens an agent's blast radius should not be the same act.
  `granted` defaults to false in the model, the migration and the column's server
  default; granting is separate, owner-only and individually audited; runtime
  selection reads granted tools only.
* Self-contained HS256 JWT, scoped for this evaluation and replaced by the
  platform IdP in production - the rest of the system only asks authentication
  for a user with an `organization_id` and a `role`, produced by one dependency.
  `JWT_SECRET` has no default, so a deployment that omits it fails at startup.
  The token is not trusted alone: the (user, organization) pair is re-checked
  against the database on every request and `role` is read from the row, so a
  forged `org` claim or a self-promoted `role` claim buys nothing.
* Services cannot express an unfiltered query. They reach the database only
  through `ScopedRepository`, which is constructed with an organization id and
  exposes no raw session and no unscoped select. The one deliberate exception,
  the pre-authentication user lookup, is named `UnscopedAuthRepository` so its
  unscoped-ness is greppable rather than accidental.

Tests passed:
============================= 144 passed in 24.08s =============================

100% statement coverage (TOTAL 899 statements, 0 missed). Raw, unedited output of
`docker compose run --rm api pytest -v --cov` is in TEST_OUTPUT.md.

All 13 mandatory tests exist and pass:
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

Nothing is faked. There is no `assert True`, no test that passes on a 500, and
the authorization layer is never mocked - overriding it would delete the thing
under test. The only substitution is the database session, swapped for one bound
to a transaction that is rolled back after each test, so the application's own
commits are real: triggers fire, constraints are checked, audit rows land.

The isolation suite was mutation-tested: with the tenancy predicate removed from
`ScopedRepository.select()`, 6 tests fail (cross-org read, cross-org update,
cross-org activation, listing, per-tenant name uniqueness, audit scoping) and
pass again once it is restored. The tests detect the failure they claim to.

Security/isolation evidence:

Tenant isolation
* `app/api/deps.py::get_current_user` is the only source of tenancy. It reads the
  signed `org` claim, then re-validates the (user, organization) pair against the
  database via `UnscopedAuthRepository.get_user_in_organization`.
* `app/db/repository.py::ScopedRepository` - every statement is built by
  `select()`/`owned()`, which bake in `organization_id == <token's org>`.
  `add()` overwrites any organization_id on an incoming object.
  Proved by test_lifecycle_edges.py::test_the_repository_overwrites_any_organization_id_it_is_handed
  and ::test_the_repository_refuses_a_model_that_is_not_tenant_owned.
* `app/schemas/common.py::StrictModel` sets `extra="forbid"`, so a smuggled
  `organization_id` is a 422, not a silently ignored field.
  Proved by test_isolation.py::test_organization_id_in_the_request_body_is_rejected.
* Forged tokens: test_token_tampering.py::test_a_token_claiming_another_organization_is_rejected
  and ::test_a_self_promoted_role_claim_does_not_grant_owner_powers.
* Structural enforcement: test_structure.py::test_no_service_builds_an_unscoped_query
  scans every module under app/services for `select(`, `session.execute`,
  `session.add` and engine construction; ::test_no_request_schema_accepts_an_organization_id
  walks the generated OpenAPI document; ::test_there_is_no_cross_tenant_escape_hatch
  asserts the role set is exactly {owner, member} and that no /admin, /organizations
  or list-all route exists.

Database constraints and triggers, by name
* `trg_skill_versions_immutable_active` (function
  `skill_versions_forbid_active_mutation`, alembic 0002) - BEFORE UPDATE on
  skill_versions. Raises 23514 if the row was ACTIVE and prompt_body,
  requested_tools, content_hash or version_number changes; if organization_id or
  skill_id changes; or if status leaves 'active' for anything but 'superseded' or
  'disabled'. Proved by raw SQL, one case per content column:
  test_immutability.py::test_db_trigger_blocks_raw_sql_mutation_of_an_active_version
  plus ::test_db_trigger_blocks_raw_sql_reassignment_of_an_active_version_to_another_org.
  ::test_db_trigger_permits_the_legal_supersede_transition proves the guard is not
  so blunt that the lifecycle stops working.
* `uq_skill_versions_one_active_per_skill` - partial unique index on
  skill_versions (skill_id) WHERE status = 'active'. Proved by
  test_immutability.py::test_only_one_active_version_per_skill_is_possible, which
  reads the index definition out of pg_indexes and then forces a second active
  row and asserts the constraint name in the error.
* `trg_audit_log_append_only` (function `audit_log_forbid_mutation`) - BEFORE
  UPDATE OR DELETE on audit_log, always raises. Plus
  `REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM jarvis_app`. The API connects
  as `jarvis_app`, a non-owning role, precisely so the revocation actually binds -
  a table owner would bypass the privilege check. Proved by
  test_audit.py::test_the_audit_log_cannot_be_updated_by_the_application_role,
  ::test_the_audit_log_cannot_be_deleted_by_the_application_role and
  ::test_the_append_only_trigger_is_installed. Verified manually as well: the app
  role gets "permission denied for table audit_log"; the schema owner, who
  bypasses privileges, still gets "audit_log is append-only; DELETE is not
  permitted" from the trigger.
* `uq_skills_organization_id_name` - skill names are tenant-local, not global.
  Proved by test_isolation.py::test_the_same_skill_name_may_exist_in_both_organizations.
* `uq_skill_versions_skill_id_version_number` - monotonic version numbering,
  backstopping the FOR UPDATE row lock taken in SkillRepository.lock_skill.
* `ck_skill_versions_status_valid`, `ck_skills_status_valid`, `ck_users_role_valid`,
  `ck_skill_versions_version_number_positive` - lifecycle values cannot be
  arbitrary strings.
* `tool_grants.granted` - NOT NULL, server_default false, so no code path can
  create a pre-granted row.

Error hygiene
* One envelope everywhere: {"error": {"code", "message", "detail"}}, with
  machine-readable codes. Handlers for validation errors, domain errors, HTTP
  exceptions and unexpected exceptions.
* test_error_handlers.py::test_an_unexpected_error_becomes_an_opaque_500 raises a
  RuntimeError containing a fake connection string and asserts the response
  contains no traceback, no exception class and no connection string.
* test_errors.py::test_error_responses_never_leak_internals asserts the same for
  ordinary 404s.

Known limitations:
Listed in full and unhidden in README.md. The ones that matter:

* No Postgres row-level security. Isolation is enforced by the repository and
  proved by tests, not by the database. RLS policies keyed on organization_id,
  with a per-request `SET LOCAL app.organization_id`, would move the guarantee
  into Postgres itself. This is the single highest-value hardening step and the
  schema is already shaped for it.
* No rate limiting or brute-force protection on login.
* No refresh tokens, no revocation list, no key rotation. HS256 with one shared
  secret; a stolen token is valid for its 60-minute lifetime. Deleting the user
  does kill it, because the (user, org) pair is re-checked per request.
* No pagination anywhere. GET /skills returns everything; GET /audit is capped at
  500 rows with no cursor.
* No soft delete or restore. `disable` is one-way; there is no `enable`.
* No separation of duties on review - a version's author may review it.
* Single region, single writer. No replicas, no partitioning, and audit_log grows
  forever by design with no archival strategy.
* The tool allowlist is a code constant, so adding a tool needs a deploy.
* docker-compose.yml carries dev-only placeholder credentials behind ${VAR:-...}
  fallbacks so the stack starts with zero steps. .env.example contains
  placeholders only, and the application has no default for JWT_SECRET.
* `git log -p | grep -iE "(secret|password|api[_-]?key|token)="` over the whole
  history returns only .env.example placeholders, the documented dev-only compose
  values, and Python source lines. No real secret is in history, and no .env file
  was ever committed.

What I would implement next:
In the order I would actually do it.

 1. Postgres row-level security as a second, independent enforcement of the thing
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
 6. Concurrency tests that exercise the FOR UPDATE lock and the partial unique
    index under genuine parallel activation, rather than relying on reasoning.
 7. Per-tenant, data-driven tool allowlists, themselves versioned and audited, so
    adding a tool is an owner action rather than a deploy.
 8. Rate limiting on login, structured JSON request logging with a correlation id
    already carried on request.state, and metrics on activation and denial rates.
 9. An `enable`/restore path for disabled skills, and a redaction workflow for
    audit entries that must legally disappear - append-only is right until GDPR
    disagrees.
10. Contract tests for the runtime consumer, pinning the shape of
    GET /skills/active so the agent runtime cannot be broken silently.

AI tools used, if any:
Claude Code (Anthropic), used as the primary implementation tool for the whole
build - schema and migrations, application code, the test suite and the
documentation. I directed the architecture, made the design calls recorded in
ARCHITECTURE.md, and verified the result independently: the stack was rebuilt
from scratch with `docker compose down -v && docker compose up --build`, the
17-step curl walkthrough in README.md was executed against that fresh stack
before being documented, the database triggers and privilege revocations were
checked by hand through psql as both the application role and the schema owner,
and the isolation suite was mutation-tested by deliberately removing the tenancy
predicate to confirm the tests fail when they should.
```
