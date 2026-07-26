#!/usr/bin/env bash
# Copy this file to .github/scripts/container-smoke.sh in a target repository.
# Replace --version with a command that proves the image can start correctly.

set -euo pipefail

: "${IMAGE_REF:?IMAGE_REF is required}"
: "${PLATFORM:?PLATFORM is required}"

docker run --rm \
  --platform "$PLATFORM" \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --cap-drop ALL \
  --security-opt no-new-privileges=true \
  "$IMAGE_REF" \
  --version
