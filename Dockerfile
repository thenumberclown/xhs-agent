FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Copy project files
COPY pyproject.toml .
RUN uv pip install --system -e .

# Copy source code
COPY src/ src/
COPY .env* .

# Create data directories
RUN mkdir -p /app/data/cases /app/data/outputs

EXPOSE 8000

# Default: run API server
CMD ["python", "-m", "src.main", "serve", "start"]
