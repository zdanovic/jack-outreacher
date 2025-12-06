#!/usr/bin/env bash
set -euo pipefail

# Bootstrap Keycloak users/roles from .env allowlists.
# Requires KEYCLOAK_ADMIN / KEYCLOAK_ADMIN_PASSWORD (or defaults admin/admin) and .env in repo root.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo ".env not found at $ENV_FILE" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required. Install jq (e.g., brew install jq) and retry." >&2
  exit 1
fi

# Read only the auth-related variables from .env to avoid invalid variable names.
read_env() {
  local key=$1
  grep -E "^${key}=" "$ENV_FILE" | head -n1 | cut -d= -f2-
}

AUTH_ALLOWED_ADMIN_EMAILS="$(read_env AUTH_ALLOWED_ADMIN_EMAILS)"
AUTH_ALLOWED_CLIENT_EMAILS="$(read_env AUTH_ALLOWED_CLIENT_EMAILS)"
KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN:-admin}"
KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
KC_URL="${KC_URL:-http://127.0.0.1:8080}"
KC_REALM="${KC_REALM:-internal}"
USER_PASSWORD_DEFAULT="${KEYCLOAK_DEFAULT_USER_PASSWORD:-ChangeMe123!}"

KC_URL="${KC_URL:-http://127.0.0.1:8080}"
KC_REALM="${KC_REALM:-internal}"
KC_USER="${KEYCLOAK_ADMIN:-admin}"
KC_PASS="${KEYCLOAK_ADMIN_PASSWORD:-admin}"

ADMIN_EMAILS=$(echo "$AUTH_ALLOWED_ADMIN_EMAILS" | tr ',' ' ')
CLIENT_EMAILS=$(echo "$AUTH_ALLOWED_CLIENT_EMAILS" | tr ',' ' ')

token() {
  curl -s \
    -d "client_id=admin-cli" \
    -d "username=${KC_USER}" \
    -d "password=${KC_PASS}" \
    -d "grant_type=password" \
    "${KC_URL}/realms/master/protocol/openid-connect/token" | jq -r '.access_token'
}

create_user() {
  local email="$1"
  local role="$2"
  local token="$3"
  local userid

  userid=$(curl -s -H "Authorization: Bearer $token" \
    "${KC_URL}/admin/realms/${KC_REALM}/users?email=${email}" | jq -r '.[0].id // empty')

  if [[ -z "$userid" ]]; then
    curl -s -o /dev/null -w "%{http_code}" \
      -H "Authorization: Bearer $token" \
      -H "Content-Type: application/json" \
      -d "{\"username\":\"${email}\",\"email\":\"${email}\",\"enabled\":true,\"emailVerified\":true}" \
      "${KC_URL}/admin/realms/${KC_REALM}/users" >/dev/null
    userid=$(curl -s -H "Authorization: Bearer $token" \
      "${KC_URL}/admin/realms/${KC_REALM}/users?email=${email}" | jq -r '.[0].id // empty')
    echo "Created user ${email} -> ${userid}"
  else
    echo "User ${email} already exists -> ${userid}"
  fi

  # Update basic profile fields to skip "update account information"
  local fname="${email%@*}"
  local lname="user"
  curl -s -o /dev/null \
    -X PUT \
    -H "Authorization: Bearer $token" \
    -H "Content-Type: application/json" \
    -d "{\"id\":\"${userid}\",\"email\":\"${email}\",\"enabled\":true,\"emailVerified\":true,\"firstName\":\"${fname}\",\"lastName\":\"${lname}\",\"requiredActions\":[]}" \
    "${KC_URL}/admin/realms/${KC_REALM}/users/${userid}"

  # Assign role
  curl -s -o /dev/null \
    -H "Authorization: Bearer $token" \
    -H "Content-Type: application/json" \
    -d "[{\"name\":\"${role}\"}]" \
    "${KC_URL}/admin/realms/${KC_REALM}/users/${userid}/role-mappings/realm"

  # Set password (non-temporary)
  curl -s -o /dev/null \
    -X PUT \
    -H "Authorization: Bearer $token" \
    -H "Content-Type: application/json" \
    -d "{\"type\":\"password\",\"value\":\"${USER_PASSWORD_DEFAULT}\",\"temporary\":false}" \
    "${KC_URL}/admin/realms/${KC_REALM}/users/${userid}/reset-password"
  echo "Password set for ${email} (value: ${USER_PASSWORD_DEFAULT})"
}

main() {
  local t
  echo "Obtaining admin token..."
  t=$(token)
  if [[ -z "$t" || "$t" == "null" ]]; then
    echo "Failed to get admin token. Is Keycloak running on ${KC_URL}?" >&2
    exit 1
  fi

  for e in $ADMIN_EMAILS; do
    [[ -n "$e" ]] && create_user "$e" "admin" "$t"
  done
  for e in $CLIENT_EMAILS; do
    [[ -n "$e" ]] && create_user "$e" "client" "$t"
  done

  echo "Bootstrap finished."
}

main "$@"
