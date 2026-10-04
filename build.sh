#!/bin/bash
# Build the python3-dnf-plugin-custom-headers RPM on the current system.
#
# Requirements: rpm-build, python3 (and python3-dnf for %check).
# The resulting rpms land in ./dist/.
#
# Usage: ./build.sh [extra rpmbuild options...]

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

SPEC="SPECS/python3-dnf-plugin-custom-headers.spec"
VERSION="$(awk '/^Version:/ {print $2; exit}' "$SPEC")"
NAME="$(awk '/^Name:/ {print $2; exit}' "$SPEC")"
TARNAME="dnf-plugin-custom-headers-${VERSION}"

BUILD=".build"
DIST="dist"
TOPDIR="$(pwd)/${BUILD}/topdir"

rm -rf "${BUILD}"
mkdir -p "${BUILD}/staging/${TARNAME}" \
         "${TOPDIR}"/{BUILD,RPMS,SOURCES,SPECS,SRPMS} \
         "${DIST}"
rm -f "${DIST}"/*.rpm

# --- assemble a clean source tree -----------------------------------------
cp -a dnf-plugins conf tests scripts README.md LICENSE \
      "${BUILD}/staging/${TARNAME}/"
find "${BUILD}/staging" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "${BUILD}/staging" -name '*.pyc' -delete 2>/dev/null || true

# --- source tarball --------------------------------------------------------
tar -C "${BUILD}/staging" -czf "${TOPDIR}/SOURCES/${TARNAME}.tar.gz" "${TARNAME}"

# --- build -----------------------------------------------------------------
# (%{?dist} is kept in the Release tag so artifacts are clearly tied to
# the distro they were built on)
rpmbuild -ba \
    --define "_topdir ${TOPDIR}" \
    "$@" \
    "$SPEC"

# --- collect artifacts -----------------------------------------------------
cp -a "${TOPDIR}/RPMS"/*/*.rpm "${TOPDIR}/SRPMS"/*.rpm "${DIST}/"
echo
echo "Artifacts:"
ls -l "${DIST}"/*.rpm
