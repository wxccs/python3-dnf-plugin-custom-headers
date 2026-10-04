#!/bin/bash
# Full integration test: build a tiny local repository (one dummy rpm),
# serve it through the header echo server and run "dnf install
# --downloadonly" against it. Verifies that BOTH metadata downloads and
# package downloads carry the configured header_* options.
#
# Requires on the host: rpm-build, createrepo_c, python3 and the plugin
# installed (rpm install or manual copy into dnf's pluginpath).
#
# Usage: scripts/integration-test.sh

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

PORT="${INTEGRATION_PORT:-18091}"
WORK="$(mktemp -d /tmp/custom-headers-integration.XXXXXX)"
LOG="$WORK/headers.log"
REPO_FILE="/etc/yum.repos.d/zzz-custom-headers-integration.repo"

DNF_BIN="$(command -v dnf4 || true)"
[ -n "$DNF_BIN" ] || DNF_BIN="$(command -v dnf)"
if [ -z "$DNF_BIN" ]; then
    echo "integration-test: no dnf binary found" >&2
    exit 1
fi

cleanup() {
    rm -f "$REPO_FILE"
    if [ -n "${SERVER_PID:-}" ]; then
        disown "$SERVER_PID" 2>/dev/null || true
        kill "$SERVER_PID" 2>/dev/null || true
    fi
    rm -rf "$WORK"
}
trap cleanup EXIT

# --- 1. build a dummy rpm -------------------------------------------------
mkdir -p "$WORK"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
cat > "$WORK/SPECS/dummy.spec" <<'EOF'
Name:           ch-integration-dummy
Version:        1.0
Release:        1
Summary:        Dummy package for the custom-headers integration test
License:        Public Domain
BuildArch:      noarch

%description
Dummy package for the custom-headers integration test.

%install
mkdir -p %{buildroot}/usr/share/ch-integration-dummy
echo hello > %{buildroot}/usr/share/ch-integration-dummy/hello.txt

%files
/usr/share/ch-integration-dummy/hello.txt
EOF
rpmbuild -bb --quiet --define "_topdir $WORK" "$WORK/SPECS/dummy.spec" \
    > /dev/null 2>&1

# --- 2. build a yum repository out of it ----------------------------------
mkdir -p "$WORK/repo/Packages"
cp "$WORK"/RPMS/noarch/*.rpm "$WORK/repo/Packages/"
createrepo_c --quiet "$WORK/repo"

# --- 3. serve it with the header echo server ------------------------------
python3 "$HERE/header_echo_server.py" "$PORT" "$LOG" "$WORK/repo" &
SERVER_PID=$!
sleep 1

# --- 4. point dnf at it, with header_* options ----------------------------
cat > "$REPO_FILE" <<EOF
[ch-integration]
name=Custom Headers Integration Test
baseurl=http://127.0.0.1:$PORT/
enabled=1
gpgcheck=0
header_X-Integration-Token = integration-secret-456
header_X-Release = rel-\$releasever
EOF

# --downloadonly keeps the host rpmdb untouched; the downloaded package
# lands in the host dnf cache, which is fine for the test.
"$DNF_BIN" --releasever=10 makecache --refresh --disablerepo='*' \
    --enablerepo=ch-integration > /dev/null 2>&1
rm -rf /var/cache/dnf/ch-integration-*
"$DNF_BIN" --releasever=10 install -y --downloadonly --disablerepo='*' \
    --enablerepo=ch-integration ch-integration-dummy > /dev/null 2>&1

echo "--- headers seen by the server ---"
grep -E '^(===|X-)' "$LOG"

# every request must carry the token header
TOTAL=$(grep -c '^=== ' "$LOG")
WITH_TOKEN=$(grep -c '^X-Integration-Token: integration-secret-456$' "$LOG")
[ "$TOTAL" -gt 0 ]
if [ "$TOTAL" -ne "$WITH_TOKEN" ]; then
    echo "integration-test: only $WITH_TOKEN/$TOTAL requests carried the header" >&2
    exit 1
fi
# a package download must have happened at all
grep -q '^=== GET /Packages/.*\.rpm$' "$LOG"
grep -q '^X-Release: rel-10$' "$LOG"

echo
echo "INTEGRATION TEST PASSED ($WITH_TOKEN/$TOTAL requests carried the headers)"
