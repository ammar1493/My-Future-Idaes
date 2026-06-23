"""Vercel serverless entry point.

Vercel's Python runtime serves the exported ASGI `app`. All HTTP routes
(/api/*, /health) are handled here. No persistent WebSockets are used, which is
why the backend fits the serverless model.
"""
import os
import sys

# Ensure the backend project root (parent of this api/ dir) is importable,
# regardless of Vercel's working directory, so `app` resolves.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402,F401
