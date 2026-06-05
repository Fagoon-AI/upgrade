#!/bin/bash

VENV_DIR=".venv"

# Check virtual environment directory exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Virtual environment not found. Creating a new virtual environment..."

    # Create a virtual environment
    python3 -m venv "$VENV_DIR"
    echo "Virtual environment created."
fi

# Activate virtual environment
echo "Activating the virtual environment..."
source "$VENV_DIR/bin/activate"

echo "Syncing the project using uv..."
uv sync

echo "Virtual environment activated and project synced."
