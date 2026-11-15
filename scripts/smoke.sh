#!/bin/sh
# Read-only smoke test against a public URL: scripts/smoke.sh https://docly.example.com
# Add --write to also exercise signup/login/RLS-scoped reads (creates ONE throwaway clinic; use only locally/staging).
set -u
URL="${1:?usage: smoke.sh <base-url> [--write]}"
FAIL=0
check() { # name expected_status actual_status [body-substring-file substring]
  if [ "$2" = "$3" ]; then echo "PASS $1 ($3)"; else echo "FAIL $1: expected $2 got $3"; FAIL=1; fi
}
status() { curl -s -o /tmp/smoke.body -w '%{http_code}' "$@"; }

check "frontend /"                 200 "$(status "$URL/")"
check "api /health"                200 "$(status "$URL/api/health")"
check "api /ready (db+redis)"      200 "$(status "$URL/api/ready")"
check "unknown clinic -> 404"      404 "$(status "$URL/api/public/no-such-clinic-xyz")"
grep -q '"error"' /tmp/smoke.body && echo "PASS error format" || { echo "FAIL error format"; FAIL=1; }
check "protected route -> 401"     401 "$(status "$URL/api/clinic")"
check "frontend booking page"      200 "$(status "$URL/no-such-clinic-xyz")"
check "login page"                 200 "$(status "$URL/login")"

if [ "${2:-}" = "--write" ]; then
  TAG=$(date +%s)
  check "signup" 201 "$(status -X POST "$URL/api/auth/signup" -H 'content-type: application/json' \
    -d "{\"clinic_name\":\"Smoke $TAG\",\"slug\":\"smoke-$TAG\",\"full_name\":\"Smoke Test\",\"email\":\"smoke-$TAG@example.com\",\"password\":\"smoke-password-$TAG\"}")"
  TOKEN=$(sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p' /tmp/smoke.body)
  check "authenticated /clinic" 200 "$(status "$URL/api/clinic" -H "Authorization: Bearer $TOKEN")"
  check "public clinic page"    200 "$(status "$URL/api/public/smoke-$TAG")"
fi
[ "$FAIL" = 0 ] && echo "SMOKE OK" || { echo "SMOKE FAILED"; exit 1; }
