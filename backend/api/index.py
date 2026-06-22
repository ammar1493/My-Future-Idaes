"""Vercel serverless entry point.

Vercel's Python runtime serves the exported ASGI `app`. All HTTP routes
(/api/*, /health) are handled here. Persistent WebSockets are NOT used in the
LiveKit configuration, which is why the backend fits the serverless model.
"""
from app.main import app  # noqa: F401
