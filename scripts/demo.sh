#!/usr/bin/env bash
# Live verification of every claim this submission makes, in about 20 seconds.
#
#   docker compose up --build -d      # then, once healthy:
#   ./scripts/demo.sh
#
# Runs the full skill lifecycle against the running stack, then attacks it five
# ways and shows each attack failing correctly. Every step prints the request,
# the real response status, and a PASS/FAIL verdict. Exits non-zero if any
# verdict fails, so it doubles as a smoke test.
#
# Needs: curl, jq, and the compose stack running.

set -uo pipefail

API="${API:-http://localhost:8080}"
PASS_WORD="${SEED_PASSWORD:-dev-only-not-a-secret}"
DB_SERVICE="${DB_SERVICE:-db}"
DB_APP_USER="${DB_APP_USER:-jarvis_app}"
DB_NAME="${DB_NAME:-jarvis}"
DB_PASSWORD="${APP_DB_PASSWORD:-dev-only-not-a-secret}"

if [ -t 1 ]; then
  BOLD=$'\e[1m'; DIM=$'\e[2m'; GREEN=$'\e[32m'; RED=$'\e[31m'; CYAN=$'\e[36m'; RESET=$'\e[0m'
else
  BOLD=''; DIM=''; GREEN=''; RED=''; CYAN=''; RESET=''
fi

FAILURES=0
STEP=0

need() { command -v "$1" >/dev/null 2>&1 || { echo "${RED}missing dependency: $1${RESET}"; exit 2; }; }
need curl; need jq

section() { printf '\n%s%s%s\n' "$BOLD" "$1" "$RESET"; printf '%s%s%s\n' "$DIM" "$(printf '─%.0s' $(seq 1 76))" "$RESET"; }

# verdict <expected> <actual> <what>
verdict() {
  local expected="$1" actual="$2" what="$3"
  if [ "$expected" = "$actual" ]; then
    printf '   %sPASS%s  %s %s(expected %s, got %s)%s\n' "$GREEN" "$RESET" "$what" "$DIM" "$expected" "$actual" "$RESET"
  else
    printf '   %sFAIL%s  %s %s(expected %s, got %s)%s\n' "$RED" "$RESET" "$what" "$BOLD" "$expected" "$actual" "$RESET"
    FAILURES=$((FAILURES + 1))
  fi
}

# call <METHOD> <path> <token> [json-body]  -> body in $BODY, status in $STATUS
call() {
  local method="$1" path="$2" token="$3" body="${4:-}"
  STEP=$((STEP + 1))
  printf '\n%s%2d.%s %s%s %s%s\n' "$BOLD" "$STEP" "$RESET" "$CYAN" "$method" "$path" "$RESET"
  [ -n "$body" ] && printf '   %s-> %s%s\n' "$DIM" "$(echo "$body" | jq -c . 2>/dev/null || echo "$body")" "$RESET"

  local out
  if [ -n "$body" ]; then
    out=$(curl -sS -X "$method" "$API$path" \
      -H "Authorization: Bearer $token" -H 'Content-Type: application/json' \
      -d "$body" -w $'\n%{http_code}')
  else
    out=$(curl -sS -X "$method" "$API$path" -H "Authorization: Bearer $token" -w $'\n%{http_code}')
  fi
  STATUS="${out##*$'\n'}"
  BODY="${out%$'\n'*}"
}

show() { printf '   %s<- %s%s\n' "$DIM" "$(echo "$BODY" | jq -c "$1" 2>/dev/null || echo "$BODY")" "$RESET"; }

login() {
  curl -sS -X POST "$API/auth/login" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$1\",\"password\":\"$PASS_WORD\"}" | jq -r '.access_token // empty'
}

psql_as_app() {
  docker compose exec -T -e PGPASSWORD="$DB_PASSWORD" "$DB_SERVICE" \
    psql -U "$DB_APP_USER" -d "$DB_NAME" -c "$1" 2>&1
}

# ---------------------------------------------------------------------------
printf '%s\n' "${BOLD}Jarvis Skill Registry — live verification${RESET}"
printf '%starget: %s%s\n' "$DIM" "$API" "$RESET"

if ! curl -fsS -m 5 "$API/health" >/dev/null 2>&1; then
  printf '\n%sThe API is not answering at %s.%s\n' "$RED" "$API" "$RESET"
  printf 'Start it with:  docker compose up --build -d\n'
  exit 2
fi

section "Authentication — three identities, two organizations"
ABC_OWNER=$(login owner@abc-construction.test)
ABC_MEMBER=$(login member@abc-construction.test)
XYZ_OWNER=$(login owner@xyz-builders.test)
for pair in "ABC owner:$ABC_OWNER" "ABC member:$ABC_MEMBER" "XYZ owner:$XYZ_OWNER"; do
  name="${pair%%:*}"; tok="${pair#*:}"
  if [ -n "$tok" ]; then
    printf '   %sPASS%s  %-12s token acquired\n' "$GREEN" "$RESET" "$name"
  else
    printf '   %sFAIL%s  %-12s could not log in\n' "$RED" "$RESET" "$name"; FAILURES=$((FAILURES + 1))
  fi
done
[ -z "$ABC_OWNER" ] && { printf '\n%sCannot continue without a token. Was the database seeded?%s\n' "$RED" "$RESET"; exit 2; }

SKILL_NAME="Demo Skill $(date +%s)"

section "PART 1 — the happy path: draft → review → activate → retrieve → audit"

call POST /skills "$ABC_MEMBER" "{\"name\":\"$SKILL_NAME\",\"department\":\"operations\",\"description\":\"Summarises the day's site schedule.\",\"prompt_body\":\"You are the ABC Construction scheduling assistant.\",\"requested_tools\":[\"query_schedule\",\"read_project\"]}"
verdict 201 "$STATUS" "member creates a skill draft"
SKILL_ID=$(echo "$BODY" | jq -r .id)
show '{status, versions: [.versions[] | {version_number, status, tool_grants: [.tool_grants[] | {tool_name, granted}]}]}'
GRANTED=$(echo "$BODY" | jq '[.versions[0].tool_grants[] | select(.granted)] | length')
verdict 0 "$GRANTED" "requested tools are NOT auto-granted"

call GET "/skills/active" "$ABC_OWNER"
verdict 200 "$STATUS" "runtime selection responds"
verdict "[]" "$(echo "$BODY" | jq -c 'map(select(.skill_id=="'"$SKILL_ID"'"))')" "a draft skill does NOT load as active"

call POST "/skills/$SKILL_ID/versions/1/activate" "$ABC_OWNER"
verdict 409 "$STATUS" "activation is refused before review"
show '.error.code'

call POST "/skills/$SKILL_ID/versions/1/review" "$ABC_MEMBER"
verdict 200 "$STATUS" "version 1 is reviewed"
show '{version_number, status, reviewed_by}'

call POST "/skills/$SKILL_ID/versions/1/tool-grants" "$ABC_OWNER" '{"tools":["query_schedule"]}'
verdict 200 "$STATUS" "owner grants one of the two requested tools"
show '[.tool_grants[] | {tool_name, granted}]'

call POST "/skills/$SKILL_ID/versions/1/activate" "$ABC_OWNER"
verdict 200 "$STATUS" "owner activates the reviewed version"
show '{version_number, status, activated_by}'

call GET "/skills/active?department=operations" "$ABC_OWNER"
verdict 200 "$STATUS" "runtime selection returns the active skill"
show 'map(select(.skill_id=="'"$SKILL_ID"'")) | .[0] | {name, version_number, content_hash, granted_tools}'
RUNTIME_TOOLS=$(echo "$BODY" | jq -c 'map(select(.skill_id=="'"$SKILL_ID"'"))[0].granted_tools')
verdict '["query_schedule"]' "$RUNTIME_TOOLS" "runtime sees ONLY the granted tool"

call POST "/skills/$SKILL_ID/versions/1/activate" "$ABC_OWNER"
verdict 200 "$STATUS" "re-activating the same version is idempotent (200, unchanged)"
AUDIT_ACTIVATIONS=$(curl -sS "$API/audit" -H "Authorization: Bearer $ABC_OWNER" \
  | jq '[.[] | select(.event=="skill_version.activated" and .skill_id=="'"$SKILL_ID"'")] | length')
verdict 1 "$AUDIT_ACTIVATIONS" "…and wrote NO duplicate audit row"

call GET "/audit" "$ABC_OWNER"
verdict 200 "$STATUS" "audit log for this organization"
echo "$BODY" | jq -r '[.[] | select(.skill_id=="'"$SKILL_ID"'")] | reverse | .[]
  | "      \(.event)  v\(.version_number // "-")  org=\(.organization_id[0:8])…  actor=\(.actor_user_id[0:8])…"'
COMPLETE=$(echo "$BODY" | jq '[.[] | select(.skill_id=="'"$SKILL_ID"'" and (.organization_id==null or .actor_user_id==null or .event==null))] | length')
verdict 0 "$COMPLETE" "every audit row carries organization, actor and event"

section "PART 2 — the attacks: each of these MUST fail"

call GET "/skills/$SKILL_ID" "$XYZ_OWNER"
verdict 404 "$STATUS" "cross-org READ is denied — 404, not 403 (no existence oracle)"
show '.error.code'
call GET "/skills/00000000-0000-0000-0000-000000000000" "$XYZ_OWNER"
verdict 404 "$STATUS" "…and a nonexistent id looks identical"

call PATCH "/skills/$SKILL_ID" "$XYZ_OWNER" '{"description":"taken over"}'
verdict 404 "$STATUS" "cross-org UPDATE is denied"

call POST "/skills/$SKILL_ID/versions/1/activate" "$XYZ_OWNER"
verdict 404 "$STATUS" "cross-org ACTIVATION is denied — 404 (role check never reached)"

call POST "/skills/$SKILL_ID/versions/1/activate" "$ABC_MEMBER"
verdict 403 "$STATUS" "non-owner activation is denied — 403 (they CAN see it; the role is wrong)"
show '.error'

call POST /skills "$ABC_OWNER" '{"name":"Malicious","department":"ops","prompt_body":"p","requested_tools":["shell_exec"]}'
verdict 422 "$STATUS" "destructive tool 'shell_exec' is rejected"
show '.error | {code, message}'

call POST /skills "$ABC_OWNER" '{"name":"Malicious","department":"ops","prompt_body":"p","requested_tools":["read_*"]}'
verdict 422 "$STATUS" "wildcard tool 'read_*' is rejected"
show '.error.detail'

call POST /skills "$ABC_OWNER" "{\"name\":\"Smuggled\",\"department\":\"ops\",\"prompt_body\":\"p\",\"requested_tools\":[],\"organization_id\":\"00000000-0000-0000-0000-000000000000\"}"
verdict 422 "$STATUS" "a smuggled organization_id in the body is rejected"
show '.error.code'

STEP=$((STEP + 1))
printf '\n%s%2d.%s %sdirect SQL, bypassing the application entirely%s\n' "$BOLD" "$STEP" "$RESET" "$CYAN" "$RESET"
printf '   %s-> UPDATE skill_versions SET prompt_body = %s WHERE status = %s;%s\n' "$DIM" "'hacked'" "'active'" "$RESET"
SQL_OUT=$(psql_as_app "UPDATE skill_versions SET prompt_body = 'hacked' WHERE status = 'active';")
printf '   %s<- %s%s\n' "$DIM" "$(echo "$SQL_OUT" | head -1)" "$RESET"
if echo "$SQL_OUT" | grep -qi 'immutable'; then
  verdict blocked blocked "the DB trigger blocks mutation of an ACTIVE version"
else
  verdict blocked "allowed" "the DB trigger blocks mutation of an ACTIVE version"
fi

STEP=$((STEP + 1))
printf '\n%s%2d.%s %sdirect SQL against the audit log%s\n' "$BOLD" "$STEP" "$RESET" "$CYAN" "$RESET"
printf '   %s-> DELETE FROM audit_log;%s\n' "$DIM" "$RESET"
SQL_OUT=$(psql_as_app "DELETE FROM audit_log;")
printf '   %s<- %s%s\n' "$DIM" "$(echo "$SQL_OUT" | head -1)" "$RESET"
if echo "$SQL_OUT" | grep -qiE 'permission denied|append-only'; then
  verdict blocked blocked "the audit log is append-only for the application role"
else
  verdict blocked "allowed" "the audit log is append-only for the application role"
fi

section "Result"
if [ "$FAILURES" -eq 0 ]; then
  printf '%s  All %d checks passed.%s\n' "$GREEN$BOLD" "$STEP" "$RESET"
  printf '  Every guarantee in README.md was just demonstrated against a live stack.\n\n'
  exit 0
else
  printf '%s  %d check(s) FAILED.%s\n\n' "$RED$BOLD" "$FAILURES" "$RESET"
  exit 1
fi
