#!/usr/bin/env bash
# Build and run the FundsPortfolio Docker image locally.
# Usage: ./scripts/run-docker.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

IMAGE_NAME="funds-portfolio-local"
CONTAINER_NAME="funds-portfolio-local"

echo "📦 Building Docker image ($IMAGE_NAME)"
docker build -t "$IMAGE_NAME" .

echo "🧪 Running Docker container ($CONTAINER_NAME)"
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
docker run --rm -d --name "$CONTAINER_NAME" -p 5000:5000 "$IMAGE_NAME"

echo "✅ Running at http://localhost:5000"

echo "🛑 Stop with: docker stop $CONTAINER_NAME"