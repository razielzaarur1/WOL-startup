FROM python:3.11-slim

# Install system dependencies including iputils-ping for network reachability checks
RUN apt-get update && \
    apt-get install -y --no-install-recommends iputils-ping && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Upgrade pip first so it can download modern pre-built binary wheels (manylinux)
RUN pip install --no-cache-dir --upgrade pip

# Copy dependency specifications
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY app/ ./app/

# Create data directory for volume mounting
RUN mkdir -p /app/data

# Environment configuration
ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/app/data

# Expose non-standard web management port
EXPOSE 7892

# Start server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7892"]
