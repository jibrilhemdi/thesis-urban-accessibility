"""Create a SQLAlchemy connection from local, uncommitted configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL

from src.ingestion.common import PROJECT_ROOT


def database_settings(env_path: Path | None = None) -> dict[str, str]:
    path = env_path or PROJECT_ROOT / ".env"
    if not path.is_file():
        raise RuntimeError("No .env file. Copy .env.example to .env and set DB_PASSWORD.")
    load_dotenv(path, override=False)
    names = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
    settings = {name: os.environ.get(name, "") for name in names}
    missing = [name for name, value in settings.items() if not value]
    if missing:
        raise RuntimeError(f"Missing database setting(s) in .env/environment: {', '.join(missing)}")
    try:
        port = int(settings["DB_PORT"])
    except ValueError as error:
        raise RuntimeError("DB_PORT must be an integer") from error
    if not 1 <= port <= 65535:
        raise RuntimeError("DB_PORT must be between 1 and 65535")
    return settings


def get_engine(env_path: Path | None = None) -> Engine:
    settings = database_settings(env_path)
    url = URL.create(
        "postgresql+psycopg2",
        username=settings["DB_USER"],
        password=settings["DB_PASSWORD"],
        host=settings["DB_HOST"],
        port=int(settings["DB_PORT"]),
        database=settings["DB_NAME"],
    )
    return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
