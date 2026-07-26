#!/usr/bin/env bash
# Copy this file to .github/scripts/container-smoke.sh in a target repository.
# Change CONTAINER_PORT, HEALTH_PATH and any required environment variables.

set -euo pipefail

: "${IMAGE_REF:?IMAGE_REF is required}"
: "${PLATFORM:?PLATFORM is required}"

container_port="${CONTAINER_PORT:-8080}"
health_path="${HEALTH_PATH:-/health}"
container_name="container-smoke-${GITHUB_RUN_ID:-local}-${RANDOM}"

cleanup() {
  status=$?
  trap - EXIT
  if (( status != 0 )); then
    echo "Container logs:" >&2
    docker logs "$container_name" >&2 || true
  fi
  docker rm --force --volumes "$container_name" >/dev/null 2>&1 || true
  exit "$status"
}
trap cleanup EXIT

docker run --detach \
  --name "$container_name" \
  --platform "$PLATFORM" \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=128m \
  --cap-drop ALL \
  --security-opt no-new-privileges=true \
  --publish "127.0.0.1::${container_port}" \
  "$IMAGE_REF" >/dev/null

host_port="$(docker port "$container_name" "${container_port}/tcp" | awk -F: 'NR == 1 { print $NF }')"
if [[ -z "$host_port" ]]; then
  echo "Unable to resolve the published container port." >&2
  exit 1
fi

for attempt in $(seq 1 60); do
  if curl --fail --silent --show-error "http://127.0.0.1:${host_port}${health_path}" >/dev/null; then
    echo "Container health check passed."
    exit 0
  fi

  running="$(docker inspect --format '{{ .State.Running }}' "$container_name" 2>/dev/null || true)"
  if [[ "$running" != "true" ]]; then
    echo "The container exited before becoming healthy." >&2
    exit 1
  fi

  sleep 2
done

echo "The container did not become healthy." >&2
exit 1
