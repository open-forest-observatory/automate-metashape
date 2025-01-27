#!/bin/bash

# Simple script to build and push a Docker image
# Usage: ./build_and_push.sh

# Exit on any error
set -e

# Variables
IMAGE_NAME="ghcr.io/arnavakula/hello-world-ghcr"

# Build the Docker image
echo "Building Docker image: $IMAGE_NAME..."
sudo docker build -t $IMAGE_NAME .

# Push the Docker image
echo "Pushing Docker image: $IMAGE_NAME..."
sudo docker push $IMAGE_NAME

echo "Docker image built and pushed successfully!"