# Use official slim Python 3.11 base image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PORT=5000

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . /app/

# Make entrypoint script executable
RUN chmod +x /app/entrypoint.sh

# Expose container port 5000
EXPOSE 5000

# Health check endpoint on port 5000
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=5 \
  CMD curl -f http://127.0.0.1:5000/health || exit 1

# Set entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]
