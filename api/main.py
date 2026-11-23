"""ASGI entry point. Run with: python -m uvicorn api.main:app"""

from api.bootstrap import create_app

app = create_app()
