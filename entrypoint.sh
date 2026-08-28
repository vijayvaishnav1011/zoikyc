#!/bin/sh
set -e

echo "🚀 Starting ZoiKYC Production Container..."

# Apply database migrations
echo "📦 Running database migrations..."
flask db upgrade || echo "⚠️ Migration check finished"

# Start Gunicorn WSGI Server
echo "🌐 Starting Gunicorn production server on port 5000..."
exec gunicorn --bind 0.0.0.0:5000 --workers 4 --threads 2 --timeout 120 "run:app"
