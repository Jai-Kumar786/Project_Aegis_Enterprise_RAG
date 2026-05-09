"""
backend/main.py

Entry point for the Project Aegis FastAPI application.

Run locally:
    uvicorn backend.main:app --reload --port 8000

Or from the backend/ directory:
    uvicorn main:app --reload --port 8000
"""

from dotenv import load_dotenv

# Load .env before any other imports so os.environ is populated
load_dotenv()

from backend.api.routes import app  # noqa: E402 — must come after load_dotenv

__all__ = ["app"]
