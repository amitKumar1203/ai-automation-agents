#!/usr/bin/env bash
# Start the FastAPI API. Run the Next.js dashboard separately from frontend/.
cd "$(dirname "$0")"
echo "Starting server at http://127.0.0.1:8000"
echo "Press Ctrl+C to stop"
exec python3 -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
