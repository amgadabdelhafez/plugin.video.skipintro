#!/bin/bash
# Build and run the headless Kodi E2E suite without requiring docker compose.

set -e
cd "$(dirname "$0")/.."

PLATFORM="${1:-linux/arm64}"
TAG="${2:-arm64}"
IMAGE="kodi-skipintro-test:${TAG}"

docker build --platform "$PLATFORM" -f test-container/Dockerfile -t "$IMAGE" test-container
docker run --rm --platform "$PLATFORM" -v "$(pwd):/addon" "$IMAGE" e2e
