#!/usr/bin/env bash
set -euo pipefail

echo "Checking Keycloak..."
curl -fsI http://127.0.0.1:8080/.well-known/openid-configuration >/dev/null && echo "Keycloak OK"

echo "Checking API /auth/config..."
curl -fs http://127.0.0.1:8000/auth/config && echo -e "\nAPI OK"

echo "Checking UI..."
curl -fsI http://127.0.0.1:5173 >/dev/null && echo "UI OK"
