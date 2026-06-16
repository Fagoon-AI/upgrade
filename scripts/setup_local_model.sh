#!/bin/bash
# Check if ollama is installed
if ! command -v ollama &> /dev/null
then
    echo "=========================================="
    echo "ERROR: Ollama is not installed!"
    echo "Please download and install Ollama from https://ollama.com"
    echo "Once installed, rerun this script to pull the local fallback model."
    echo "=========================================="
    exit 1
fi

echo "=========================================="
echo "Ollama is installed. Fetching Gemma 2B model..."
echo "=========================================="
ollama pull gemma:2b
echo "=========================================="
echo "Success! Gemma 2B fallback model is ready."
echo "=========================================="
