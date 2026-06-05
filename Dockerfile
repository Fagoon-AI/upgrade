# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python package globally (will be copied later)
RUN pip install --no-cache-dir uv

# Copy project files
COPY . .

# Make scripts executable
RUN chmod +x scripts/run.sh


# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Copy installed Python packages from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv

# Copy only your app files (no build dependencies needed)
COPY --from=builder /app /app

# Make sure the script is executable
RUN chmod +x scripts/run.sh

ENTRYPOINT ["scripts/run.sh"]
