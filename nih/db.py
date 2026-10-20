"""PostgreSQL connection helper for the local warehouse."""

from __future__ import annotations

from nih.config import Settings, load_settings, postgres_kwargs


def connect(settings: Settings | None = None):
    import psycopg

    settings = settings or load_settings()
    return psycopg.connect(**postgres_kwargs(settings))
