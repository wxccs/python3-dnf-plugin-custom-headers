#!/bin/bash
# Smoke test: verify that the installed custom-headers plugin really
# sends the configured header_* options upstream.
#
# The test assumes the plugin is already installed (rpm install or a
# manual copy into dnf's pluginpath). It only:
#   1. starts a local HTTP server that records request headers
#   2. adds a repo pointing at it with header_* options
#   3. runs "dnf makecache" (the request fails with 404, which is fine -
#      we only care about the headers that were sent)
#   4. greps the recorded headers
#
# Usage: scripts/smoke-test.sh

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$HERE")"

PORT="${SMOKE_PORT:-18089}"
LOG="$(mktemp /tmp/custom-headers-smoke.XXXXXX.log)"
REPO_FILE="/etc/yum.repos.d/zzz-custom-headers-smoke.repo"

# rocky/rhel 10 systems default to dnf5; the plugin needs the dnf4 stack
DNF_BIN="$(command -v dnf4 || true)"
[ -n "$DNF_BIN" ] || DNF_BIN="$(command -v dnf)"
if [ -z "$DNF_BIN" ]; then
    echo "smoke-test: no dnf binary found" >&2
    exit 1
fi

cleanup() {
    rm -f "$REPO_FILE" "$LOG"
    if [ -n "${SERVER_PID:-}" ]; then
        disown "$SERVER_PID" 2>/dev/null || true
        kill "$SERVER_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

python3 "$HERE/header_echo_server.py" "$PORT" "$LOG" &
SERVER_PID=$!
sleep 1

cat > "$REPO_FILE" <<'EOF'
[custom-headers-smoke]
name=Custom Headers Smoke Test
baseurl=http://127.0.0.1:PORT/repo/
enabled=1
header_X-Smoke-Token = smoke-secret-123
header_X-Release = rel-$releasever
EOF
sed -i "s/PORT/$PORT/" "$REPO_FILE"

# 404 from the echo server makes makecache fail - expected, ignore it.
"$DNF_BIN" makecache --refresh --disablerepo='*' \
    --enablerepo=custom-headers-smoke >/dev/null 2>&1 || true

echo "--- headers recorded by the echo server ---"
sed -n '1,20p' "$LOG"

grep -q '^X-Smoke-Token: smoke-secret-123$' "$LOG"
grep -q '^X-Release: rel-' "$LOG"

echo
echo "SMOKE TEST PASSED"
