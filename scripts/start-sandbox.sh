#!/usr/bin/env bash
set -euo pipefail
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
docker build -t simple-ai-harness-runner "$root_dir/sandbox-service/sandbox"
docker build -t simple-ai-harness-sandbox "$root_dir/sandbox-service"
docker run --rm -p 8001:8001 -e SANDBOX_TOKEN="${SANDBOX_TOKEN:-local-sandbox-token}" \
  -v /var/run/docker.sock:/var/run/docker.sock simple-ai-harness-sandbox
