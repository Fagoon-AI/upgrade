#!/bin/bash
# =============================================================================
# Build the Python Sandbox Docker Image
# =============================================================================
#
# This script builds the secure sandbox image used for code execution.
#
# Usage:
#   ./docker/build-sandbox.sh [tag]
#
# Examples:
#   ./docker/build-sandbox.sh           # Builds workflow-sandbox-python:latest
#   ./docker/build-sandbox.sh v1.0.0    # Builds workflow-sandbox-python:v1.0.0
#
# =============================================================================

set -e

# Configuration
IMAGE_NAME="workflow-sandbox-python"
TAG="${1:-latest}"
DOCKERFILE="docker/Dockerfile.sandbox"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Building Sandbox Image${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Image: ${IMAGE_NAME}:${TAG}"
echo "Dockerfile: ${DOCKERFILE}"
echo ""

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed or not in PATH${NC}"
    exit 1
fi

# Check if Docker daemon is running
if ! docker info &> /dev/null; then
    echo -e "${RED}Error: Docker daemon is not running${NC}"
    exit 1
fi

# Change to project root
cd "$(dirname "$0")/.."

# Check if Dockerfile exists
if [ ! -f "$DOCKERFILE" ]; then
    echo -e "${RED}Error: Dockerfile not found at ${DOCKERFILE}${NC}"
    exit 1
fi

# Build the image
echo -e "${YELLOW}Building image...${NC}"
docker build \
    --tag "${IMAGE_NAME}:${TAG}" \
    --file "${DOCKERFILE}" \
    --build-arg BUILD_DATE="$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
    .

# Verify the build
echo ""
echo -e "${YELLOW}Verifying build...${NC}"

# Check image exists
if ! docker image inspect "${IMAGE_NAME}:${TAG}" &> /dev/null; then
    echo -e "${RED}Error: Image was not created${NC}"
    exit 1
fi

# Get image size
SIZE=$(docker image inspect "${IMAGE_NAME}:${TAG}" --format='{{.Size}}' | awk '{printf "%.1f MB", $1/1024/1024}')

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Build Successful!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Image: ${IMAGE_NAME}:${TAG}"
echo "Size: ${SIZE}"
echo ""

# Run a quick test
echo -e "${YELLOW}Running security test...${NC}"
docker run --rm \
    --network none \
    --read-only \
    --tmpfs /tmp:size=64m,mode=1777 \
    --memory 128m \
    --cpus 0.5 \
    --pids-limit 50 \
    --user sandbox \
    "${IMAGE_NAME}:${TAG}" \
    python3 -c "print('Sandbox test: OK')"

echo ""
echo -e "${GREEN}All tests passed!${NC}"
echo ""
echo "To use this image, ensure your .env has:"
echo "  SANDBOX_DOCKER_IMAGE=${IMAGE_NAME}:${TAG}"
echo ""
echo "Or run manually:"
echo "  docker run --rm --network none --read-only --tmpfs /tmp:size=64m ${IMAGE_NAME}:${TAG} python3 -c 'print(1+1)'"
