#!/bin/bash
# Run tests on all supported architectures
# Usage: ./test-container/test-all.sh

set -e
cd "$(dirname "$0")/.."

echo "=========================================="
echo "Skip Intro Addon — Multi-Platform Tests"
echo "=========================================="
echo "Unit containers only. Run Kodi E2E separately with:"
echo "  ./test-container/run-e2e-container.sh"

PASS=0
FAIL=0

run_test() {
    local TAG=$1
    local PLATFORM=$2

    echo ""
    echo "--- $TAG ($PLATFORM) ---"

    # Build if needed
    if ! docker image inspect "skipintro-test:$TAG" >/dev/null 2>&1; then
        echo "  Building..."
        docker build --platform "$PLATFORM" -f test-container/Dockerfile.test \
            -t "skipintro-test:$TAG" test-container/ 2>&1 | tail -3
    fi

    # Run tests (don't pass --platform, some Docker runtimes can't resolve it)
    if docker run --rm -v "$(pwd):/addon" "skipintro-test:$TAG" 2>&1 | tail -5; then
        PASS=$((PASS + 1))
    else
        echo "  FAIL"
        FAIL=$((FAIL + 1))
    fi
}

run_test "arm64" "linux/arm64"
run_test "amd64" "linux/amd64"

echo ""
echo "=========================================="
echo "Results: $PASS passed, $FAIL failed"
echo "=========================================="

[ $FAIL -eq 0 ] && exit 0 || exit 1
