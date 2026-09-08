"""Point d'entrée WSGI pour gunicorn : ``flash.interface.wsgi:app``."""

from __future__ import annotations

from flash.interface.app import create_app

app = create_app()

__all__ = ["app"]
