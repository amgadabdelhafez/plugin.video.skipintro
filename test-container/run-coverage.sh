#!/bin/bash
# Run the mocked unit suite with coverage for addon-owned runtime code.

set -e
cd "$(dirname "$0")/.."

if ! python3 -m coverage --version >/dev/null 2>&1; then
    echo "coverage.py is not installed for this Python."
    echo "Install it locally, or run the plain suite with: python3 test_video_metadata.py -v"
    exit 1
fi

python3 -m coverage erase
python3 -m coverage run test_video_metadata.py -v
python3 -m coverage report -m
