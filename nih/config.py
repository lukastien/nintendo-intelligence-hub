"""Runtime settings. Environment variables override config/settings.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from nih.errors import ConfigurationError


def project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    raise ConfigurationError("pyproject.toml was not found")


class Settings(BaseSettings):
    """Warehouse connection settings.

    The default target is local PostgreSQL. BigQuery is optional and fails
    closed until a project id is configured.
    """

    warehouse_target: Literal["postgres", "bigquery"] = "postgres"
    postgres_host: str = "localhost"
    postgres_port: int = 54329
    postgres_db: str = "nintendo_intel"
    postgres_user: str = "nih"
    postgres_password: str = "nih_local_only"
    postgres_sslmode: str | None = None
    bigquery_project: str | None = None
    bigquery_dataset: str = "nintendo_intel"
    bigquery_location: str = "US"

    model_config = SettingsConfigDict(
        env_prefix="NIH_",
        env_file=str(project_root() / ".env"),
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(
                settings_cls,
                yaml_file=project_root() / "config" / "settings.yaml",
            ),
            file_secret_settings,
        )


def load_settings() -> Settings:
    return Settings()


def describe_target(settings: Settings | None = None) -> str:
    settings = settings or load_settings()
    if settings.warehouse_target == "postgres":
        return (
            f"postgres://{settings.postgres_user}@{settings.postgres_host}:"
            f"{settings.postgres_port}/{settings.postgres_db}"
        )
    if not settings.bigquery_project:
        raise ConfigurationError(
            "BigQuery requires NIH_BIGQUERY_PROJECT. "
            "The local warehouse target is postgres, which needs no cloud credentials."
        )
    return (
        f"bigquery://{settings.bigquery_project}.{settings.bigquery_dataset}"
        f"?location={settings.bigquery_location}"
    )


def postgres_kwargs(settings: Settings | None = None) -> dict:
    settings = settings or load_settings()
    if settings.warehouse_target != "postgres":
        raise ConfigurationError(
            "This foundation connects to local PostgreSQL. "
            "BigQuery is an optional later target and is not opened from here."
        )
    payload = {
        "host": settings.postgres_host,
        "port": settings.postgres_port,
        "dbname": settings.postgres_db,
        "user": settings.postgres_user,
        "password": settings.postgres_password,
        "connect_timeout": 5,
    }
    if settings.postgres_sslmode:
        payload["sslmode"] = settings.postgres_sslmode
    return payload
