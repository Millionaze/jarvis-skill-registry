$ docker compose run --rm api pytest -v --cov=app --cov-report=term-missing
============================= test session starts ==============================
platform linux -- Python 3.12.14, pytest-8.3.4, pluggy-1.6.0 -- /usr/local/bin/python3.12
cachedir: .pytest_cache
rootdir: /app
configfile: pytest.ini
testpaths: tests
plugins: anyio-4.14.2, cov-6.0.0, asyncio-0.25.0
asyncio: mode=Mode.AUTO, asyncio_default_fixture_loop_scope=function
collecting ... collected 153 items

tests/test_activation.py::test_member_cannot_activate_and_gets_403 PASSED [  0%]
tests/test_activation.py::test_an_unreviewed_version_cannot_be_activated PASSED [  1%]
tests/test_activation.py::test_a_freshly_created_skill_is_never_automatically_active PASSED [  1%]
tests/test_activation.py::test_owner_activates_a_reviewed_version PASSED [  2%]
tests/test_activation.py::test_duplicate_activation_is_idempotent_and_writes_no_duplicate_audit PASSED [  3%]
tests/test_activation.py::test_activating_a_second_version_supersedes_the_first_atomically PASSED [  3%]
tests/test_activation.py::test_a_superseded_version_cannot_be_reactivated PASSED [  4%]
tests/test_activation.py::test_activating_a_missing_version_is_404 PASSED [  5%]
tests/test_audit.py::test_an_audit_record_carries_organization_actor_event_and_version_number PASSED [  5%]
tests/test_audit.py::test_the_exact_activated_version_is_recorded PASSED [  6%]
tests/test_audit.py::test_every_lifecycle_step_is_audited PASSED         [  7%]
tests/test_audit.py::test_a_failed_state_change_writes_no_audit_row PASSED [  7%]
tests/test_audit.py::test_the_audit_log_cannot_be_updated_by_the_application_role PASSED [  8%]
tests/test_audit.py::test_the_audit_log_cannot_be_deleted_by_the_application_role PASSED [  9%]
tests/test_audit.py::test_the_append_only_trigger_is_installed PASSED    [  9%]
tests/test_audit.py::test_the_application_role_cannot_truncate_the_audit_log PASSED [ 10%]
tests/test_audit.py::test_the_audit_log_cannot_be_truncated_even_by_the_schema_owner PASSED [ 11%]
tests/test_audit.py::test_the_truncate_guard_is_a_statement_level_trigger PASSED [ 11%]
tests/test_auth.py::test_login_returns_a_token_scoped_to_the_users_organization PASSED [ 12%]
tests/test_auth.py::test_login_with_a_wrong_password_is_rejected PASSED  [ 13%]
tests/test_auth.py::test_unknown_email_is_rejected_with_the_same_code PASSED [ 13%]
tests/test_auth.py::test_endpoints_require_a_token[/skills] PASSED       [ 14%]
tests/test_auth.py::test_endpoints_require_a_token[/skills/active] PASSED [ 15%]
tests/test_auth.py::test_endpoints_require_a_token[/audit] PASSED        [ 15%]
tests/test_auth.py::test_endpoints_require_a_token[/auth/me] PASSED      [ 16%]
tests/test_auth.py::test_a_garbage_token_is_rejected PASSED              [ 16%]
tests/test_error_handlers.py::test_an_unexpected_error_becomes_an_opaque_500 PASSED [ 17%]
tests/test_error_handlers.py::test_the_application_immutability_guard_surfaces_as_409 PASSED [ 18%]
tests/test_error_handlers.py::test_an_unanticipated_constraint_violation_becomes_a_409_not_a_500 PASSED [ 18%]
tests/test_error_handlers.py::test_a_domain_error_can_override_its_status_and_code PASSED [ 19%]
tests/test_error_handlers.py::test_an_unauthenticated_response_advertises_the_bearer_scheme PASSED [ 20%]
tests/test_error_handlers.py::test_the_real_engine_and_sessionmaker_work PASSED [ 20%]
tests/test_error_handlers.py::test_the_session_dependency_rolls_back_on_an_escaping_exception PASSED [ 21%]
tests/test_errors.py::test_validation_failures_return_422_with_the_validation_error_code[body0-missing name] PASSED [ 22%]
tests/test_errors.py::test_validation_failures_return_422_with_the_validation_error_code[body1-missing department] PASSED [ 22%]
tests/test_errors.py::test_validation_failures_return_422_with_the_validation_error_code[body2-missing prompt_body] PASSED [ 23%]
tests/test_errors.py::test_validation_failures_return_422_with_the_validation_error_code[body3-empty name] PASSED [ 24%]
tests/test_errors.py::test_validation_failures_return_422_with_the_validation_error_code[body4-wrong type] PASSED [ 24%]
tests/test_errors.py::test_validation_failures_return_422_with_the_validation_error_code[body5-unmodelled field] PASSED [ 25%]
tests/test_errors.py::test_a_malformed_uuid_in_the_path_is_a_422 PASSED  [ 26%]
tests/test_errors.py::test_an_out_of_range_query_parameter_is_a_422 PASSED [ 26%]
tests/test_errors.py::test_every_error_uses_the_same_envelope[404-SKILL_NOT_FOUND-missing_skill] PASSED [ 27%]
tests/test_errors.py::test_every_error_uses_the_same_envelope[401-AUTH_REQUIRED-no_token] PASSED [ 28%]
tests/test_errors.py::test_every_error_uses_the_same_envelope[409-VERSION_NOT_REVIEWED-activate_unreviewed] PASSED [ 28%]
tests/test_errors.py::test_every_error_uses_the_same_envelope[422-UNKNOWN_TOOL-unknown_tool] PASSED [ 29%]
tests/test_errors.py::test_error_responses_never_leak_internals PASSED   [ 30%]
tests/test_immutability.py::test_no_route_exists_to_mutate_a_version[put] PASSED [ 30%]
tests/test_immutability.py::test_no_route_exists_to_mutate_a_version[patch] PASSED [ 31%]
tests/test_immutability.py::test_no_route_exists_to_mutate_a_version[delete] PASSED [ 32%]
tests/test_immutability.py::test_an_active_version_cannot_be_re_reviewed PASSED [ 32%]
tests/test_immutability.py::test_editing_an_active_skill_creates_a_new_version_and_leaves_the_active_one_alone PASSED [ 33%]
tests/test_immutability.py::test_orm_guard_blocks_mutation_of_an_active_version PASSED [ 33%]
tests/test_immutability.py::test_orm_guard_blocks_an_illegal_status_transition_out_of_active PASSED [ 34%]
tests/test_immutability.py::test_orm_guard_permits_the_two_legal_transitions_out_of_active PASSED [ 35%]
tests/test_immutability.py::test_db_trigger_blocks_raw_sql_mutation_of_an_active_version[prompt_body-'silently mutated'] PASSED [ 35%]
tests/test_immutability.py::test_db_trigger_blocks_raw_sql_mutation_of_an_active_version[content_hash-'0000000000000000000000000000000000000000000000000000000000000000'] PASSED [ 36%]
tests/test_immutability.py::test_db_trigger_blocks_raw_sql_mutation_of_an_active_version[requested_tools-'["read_invoice"]'::jsonb] PASSED [ 37%]
tests/test_immutability.py::test_db_trigger_blocks_raw_sql_mutation_of_an_active_version[version_number-42] PASSED [ 37%]
tests/test_immutability.py::test_db_trigger_blocks_raw_sql_reassignment_of_an_active_version_to_another_org PASSED [ 38%]
tests/test_immutability.py::test_db_trigger_permits_the_legal_supersede_transition PASSED [ 39%]
tests/test_immutability.py::test_only_one_active_version_per_skill_is_possible PASSED [ 39%]
tests/test_isolation.py::test_same_org_create_then_read_succeeds PASSED  [ 40%]
tests/test_isolation.py::test_cross_org_read_returns_404_not_403 PASSED  [ 41%]
tests/test_isolation.py::test_cross_org_update_is_denied PASSED          [ 41%]
tests/test_isolation.py::test_cross_org_activation_is_denied_with_404 PASSED [ 42%]
tests/test_isolation.py::test_listing_only_ever_shows_the_callers_own_organization PASSED [ 43%]
tests/test_isolation.py::test_the_same_skill_name_may_exist_in_both_organizations PASSED [ 43%]
tests/test_isolation.py::test_organization_id_in_the_request_body_is_rejected PASSED [ 44%]
tests/test_isolation.py::test_audit_log_is_scoped_to_the_callers_organization PASSED [ 45%]
tests/test_lifecycle_edges.py::test_health_is_open PASSED                [ 45%]
tests/test_lifecycle_edges.py::test_the_application_lifespan_starts_and_stops_cleanly PASSED [ 46%]
tests/test_lifecycle_edges.py::test_updating_skill_metadata_records_the_change PASSED [ 47%]
tests/test_lifecycle_edges.py::test_an_empty_metadata_update_changes_nothing_and_is_not_audited PASSED [ 47%]
tests/test_lifecycle_edges.py::test_a_superseded_version_cannot_be_reviewed PASSED [ 48%]
tests/test_lifecycle_edges.py::test_disabling_an_already_disabled_skill_is_idempotent PASSED [ 49%]
tests/test_lifecycle_edges.py::test_a_version_of_a_disabled_skill_cannot_be_activated PASSED [ 49%]
tests/test_lifecycle_edges.py::test_disabling_a_draft_skill_touches_no_version PASSED [ 50%]
tests/test_lifecycle_edges.py::test_the_repository_refuses_a_model_that_is_not_tenant_owned PASSED [ 50%]
tests/test_lifecycle_edges.py::test_the_repository_overwrites_any_organization_id_it_is_handed PASSED [ 51%]
tests/test_lifecycle_edges.py::test_a_lost_race_on_a_duplicate_skill_name_is_a_409_not_a_500 PASSED [ 52%]
tests/test_lifecycle_edges.py::test_an_unrelated_constraint_violation_is_not_mislabelled_as_a_name_conflict PASSED [ 52%]
tests/test_runtime_selection.py::test_a_draft_skill_never_loads_as_active PASSED [ 53%]
tests/test_runtime_selection.py::test_a_reviewed_but_unactivated_version_still_does_not_load PASSED [ 54%]
tests/test_runtime_selection.py::test_an_active_skill_loads_for_its_department PASSED [ 54%]
tests/test_runtime_selection.py::test_a_disabled_skill_is_excluded_from_runtime_selection PASSED [ 55%]
tests/test_runtime_selection.py::test_a_disabled_skill_cannot_be_reactivated_or_edited PASSED [ 56%]
tests/test_runtime_selection.py::test_only_an_owner_can_disable_a_skill PASSED [ 56%]
tests/test_runtime_selection.py::test_runtime_selection_never_crosses_organizations PASSED [ 57%]
tests/test_seed.py::test_the_fixtures_are_the_two_organizations_the_brief_names PASSED [ 58%]
tests/test_seed.py::test_seeding_creates_both_organizations_with_an_owner_and_a_member PASSED [ 58%]
tests/test_seed.py::test_seeding_twice_is_idempotent PASSED              [ 59%]
tests/test_structure.py::test_the_services_package_is_not_empty PASSED   [ 60%]
tests/test_structure.py::test_no_service_builds_an_unscoped_query[__init__.py] PASSED [ 60%]
tests/test_structure.py::test_no_service_builds_an_unscoped_query[activation.py] PASSED [ 61%]
tests/test_structure.py::test_no_service_builds_an_unscoped_query[audit.py] PASSED [ 62%]
tests/test_structure.py::test_no_service_builds_an_unscoped_query[hashing.py] PASSED [ 62%]
tests/test_structure.py::test_no_service_builds_an_unscoped_query[skills.py] PASSED [ 63%]
tests/test_structure.py::test_no_router_reads_an_organization_id_from_the_request[__init__.py] PASSED [ 64%]
tests/test_structure.py::test_no_router_reads_an_organization_id_from_the_request[audit.py] PASSED [ 64%]
tests/test_structure.py::test_no_router_reads_an_organization_id_from_the_request[auth.py] PASSED [ 65%]
tests/test_structure.py::test_no_router_reads_an_organization_id_from_the_request[skills.py] PASSED [ 66%]
tests/test_structure.py::test_no_request_schema_accepts_an_organization_id PASSED [ 66%]
tests/test_structure.py::test_there_is_no_cross_tenant_escape_hatch PASSED [ 67%]
tests/test_structure.py::test_every_tenant_table_carries_organization_id[audit_log] PASSED [ 67%]
tests/test_structure.py::test_every_tenant_table_carries_organization_id[skill_versions] PASSED [ 68%]
tests/test_structure.py::test_every_tenant_table_carries_organization_id[skills] PASSED [ 69%]
tests/test_structure.py::test_every_tenant_table_carries_organization_id[tool_grants] PASSED [ 69%]
tests/test_structure.py::test_every_tenant_table_carries_organization_id[users] PASSED [ 70%]
tests/test_structure.py::test_skill_versions_and_tool_grants_denormalise_organization_id PASSED [ 71%]
tests/test_token_tampering.py::test_a_token_claiming_another_organization_is_rejected PASSED [ 71%]
tests/test_token_tampering.py::test_a_token_for_an_unknown_user_is_rejected PASSED [ 72%]
tests/test_token_tampering.py::test_a_self_promoted_role_claim_does_not_grant_owner_powers PASSED [ 73%]
tests/test_token_tampering.py::test_malformed_uuid_claims_are_rejected[bad-sub] PASSED [ 73%]
tests/test_token_tampering.py::test_malformed_uuid_claims_are_rejected[bad-org] PASSED [ 74%]
tests/test_token_tampering.py::test_a_token_missing_required_claims_is_rejected[no-org] PASSED [ 75%]
tests/test_token_tampering.py::test_a_token_missing_required_claims_is_rejected[no-sub] PASSED [ 75%]
tests/test_token_tampering.py::test_a_token_missing_required_claims_is_rejected[empty] PASSED [ 76%]
tests/test_token_tampering.py::test_a_token_signed_with_the_wrong_secret_is_rejected PASSED [ 77%]
tests/test_token_tampering.py::test_an_expired_token_is_rejected PASSED  [ 77%]
tests/test_tools.py::test_an_unknown_tool_is_rejected_with_422[read_everything] PASSED [ 78%]
tests/test_tools.py::test_an_unknown_tool_is_rejected_with_422[list_all_orgs] PASSED [ 79%]
tests/test_tools.py::test_an_unknown_tool_is_rejected_with_422[admin_panel] PASSED [ 79%]
tests/test_tools.py::test_an_unknown_tool_is_rejected_with_422[no_such_tool] PASSED [ 80%]
tests/test_tools.py::test_a_destructive_or_malformed_tool_is_rejected_with_422[shell_exec] PASSED [ 81%]
tests/test_tools.py::test_a_destructive_or_malformed_tool_is_rejected_with_422[drop_table] PASSED [ 81%]
tests/test_tools.py::test_a_destructive_or_malformed_tool_is_rejected_with_422[delete_all] PASSED [ 82%]
tests/test_tools.py::test_a_destructive_or_malformed_tool_is_rejected_with_422[sudo] PASSED [ 83%]
tests/test_tools.py::test_a_destructive_or_malformed_tool_is_rejected_with_422[rm] PASSED [ 83%]
tests/test_tools.py::test_a_destructive_or_malformed_tool_is_rejected_with_422[read_*] PASSED [ 84%]
tests/test_tools.py::test_a_destructive_or_malformed_tool_is_rejected_with_422[../../etc/passwd] PASSED [ 84%]
tests/test_tools.py::test_a_destructive_or_malformed_tool_is_rejected_with_422[read_project; rm -rf /] PASSED [ 85%]
tests/test_tools.py::test_a_destructive_or_malformed_tool_is_rejected_with_422[tools/read_project] PASSED [ 86%]
tests/test_tools.py::test_a_destructive_or_malformed_tool_is_rejected_with_422[read project] PASSED [ 86%]
tests/test_tools.py::test_a_destructive_or_malformed_tool_is_rejected_with_422[`whoami`] PASSED [ 87%]
tests/test_tools.py::test_a_rejected_tool_creates_nothing_at_all PASSED  [ 88%]
tests/test_tools.py::test_a_requested_tool_is_never_auto_granted PASSED  [ 88%]
tests/test_tools.py::test_only_an_owner_can_grant_tools PASSED           [ 89%]
tests/test_tools.py::test_an_owner_from_another_org_cannot_grant_tools PASSED [ 90%]
tests/test_tools.py::test_a_tool_that_was_never_requested_cannot_be_granted PASSED [ 90%]
tests/test_tools.py::test_runtime_selection_only_ever_exposes_granted_tools PASSED [ 91%]
tests/test_tools.py::test_granting_twice_is_idempotent_and_writes_one_audit_row PASSED [ 92%]
tests/test_tools.py::test_a_malformed_tool_name_is_rejected_with_a_reason[-empty or non-string] PASSED [ 92%]
tests/test_tools.py::test_a_malformed_tool_name_is_rejected_with_a_reason[   -empty or non-string] PASSED [ 93%]
tests/test_tools.py::test_a_malformed_tool_name_is_rejected_with_a_reason[a-malformed identifier] PASSED [ 94%]
tests/test_tools.py::test_a_malformed_tool_name_is_rejected_with_a_reason[9tool-malformed identifier] PASSED [ 94%]
tests/test_tools.py::test_a_malformed_tool_name_is_rejected_with_a_reason[Read_Project!-malformed identifier] PASSED [ 95%]
tests/test_versions.py::test_version_numbers_are_monotonic_per_skill PASSED [ 96%]
tests/test_versions.py::test_version_numbering_is_independent_per_skill PASSED [ 96%]
tests/test_versions.py::test_the_content_hash_covers_the_canonical_payload PASSED [ 97%]
tests/test_versions.py::test_requested_tools_are_canonicalised_and_deduplicated PASSED [ 98%]
tests/test_versions.py::test_the_same_content_in_different_organizations_hashes_differently PASSED [ 98%]
tests/test_versions.py::test_a_reviewed_version_cannot_be_reviewed_twice PASSED [ 99%]
tests/test_versions.py::test_review_records_who_reviewed_and_when PASSED [100%]

---------- coverage: platform linux, python 3.12.14-final-0 ----------
Name                          Stmts   Miss  Cover   Missing
-----------------------------------------------------------
app/__init__.py                   0      0   100%
app/api/__init__.py               0      0   100%
app/api/deps.py                  40      0   100%
app/api/errors.py                39      0   100%
app/api/routers/__init__.py       0      0   100%
app/api/routers/audit.py          9      0   100%
app/api/routers/auth.py          20      0   100%
app/api/routers/skills.py        50      0   100%
app/core/__init__.py              0      0   100%
app/core/config.py               17      0   100%
app/core/enums.py                24      0   100%
app/core/errors.py               50      0   100%
app/core/security.py             27      0   100%
app/core/tools.py                26      0   100%
app/db/__init__.py                0      0   100%
app/db/base.py                   15      0   100%
app/db/repository.py             87      0   100%
app/db/session.py                27      0   100%
app/main.py                      27      0   100%
app/models/__init__.py            6      0   100%
app/models/audit.py              21      0   100%
app/models/events.py             20      0   100%
app/models/organization.py       14      0   100%
app/models/skill.py              56      0   100%
app/models/user.py               22      0   100%
app/schemas/__init__.py           0      0   100%
app/schemas/audit.py             16      0   100%
app/schemas/auth.py              18      0   100%
app/schemas/common.py            11      0   100%
app/schemas/skill.py             67      0   100%
app/seed.py                      45      0   100%
app/services/__init__.py          0      0   100%
app/services/activation.py       43      0   100%
app/services/audit.py            17      0   100%
app/services/hashing.py          12      0   100%
app/services/skills.py          143      0   100%
-----------------------------------------------------------
TOTAL                           969      0   100%


============================= 153 passed in 26.24s =============================
