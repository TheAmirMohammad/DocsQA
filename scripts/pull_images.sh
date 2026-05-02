#!/usr/bin/env bash
# ==============================================================================
# DocsQA: Pull Required Docker Images
# ==============================================================================
set -euo pipefail

# ANSI color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}       DocsQA Docker Images Pull Script               ${NC}"
echo -e "${BLUE}======================================================${NC}"

# Check if Docker daemon is running
if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}[ERROR] Docker daemon is not running. Please start Docker first.${NC}"
    exit 1
fi

# List of required images
REQUIRED_IMAGES=(
    "pgvector/pgvector:pg17"
    "redis:7-alpine"
    "python:3.12-slim"
)

# List of optional observability images
OBSERVABILITY_IMAGES=(
    "prom/prometheus:v2.53.0"
    "grafana/grafana:11.0.0"
)

pull_image_if_missing() {
    local img="$1"
    if docker image inspect "$img" >/dev/null 2>&1; then
        echo -e "${GREEN}[ALREADY PRESENT]${NC} $img"
    else
        echo -e "${YELLOW}[PULLING]${NC} $img ..."
        docker pull "$img"
        echo -e "${GREEN}[DOWNLOADED]${NC} $img"
    fi
}

echo -e "\n${BLUE}--- 1. Pulling Core Services ---${NC}"
for img in "${REQUIRED_IMAGES[@]}"; do
    pull_image_if_missing "$img"
done

echo -e "\n${BLUE}--- 2. Pulling Monitoring Stack (Prometheus & Grafana) ---${NC}"
for img in "${OBSERVABILITY_IMAGES[@]}"; do
    pull_image_if_missing "$img"
done

echo -e "\n${GREEN}======================================================${NC}"
echo -e "${GREEN}  All images are ready! You can now run:              ${NC}"
echo -e "${GREEN}  docker compose up --build -d                        ${NC}"
echo -e "${GREEN}======================================================${NC}"
