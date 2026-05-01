"""
app/config.py

Single source of truth for all configuration.
Reads from environment variables or a .env file.
"""

from enum import Enum
from pydantic import Field
from pydantic_settings import BaseSettings


class DBType(str, Enum):
    SQLITE     = "sqlite"
    POSTGRESQL = "postgresql"
    MYSQL      = "mysql"
    MONGODB    = "mongodb"


class Settings(BaseSettings):

    # ------------------------------------------------------------------
    # LLM — must be present in .env as GEMINI_API_KEY
    # ------------------------------------------------------------------
    gemini_api_key: str = Field("", alias="GEMINI_API_KEY")

    # ------------------------------------------------------------------
    # Which database engine to use
    # Valid values: sqlite | postgresql | mysql | mongodb
    # ------------------------------------------------------------------
    db_type: DBType = Field(DBType.SQLITE, alias="DB_TYPE")

    # ------------------------------------------------------------------
    # Relational DB (PostgreSQL / MySQL)
    # ------------------------------------------------------------------
    db_host:     str = Field("localhost", alias="DB_HOST")
    db_port:     int = Field(5432,        alias="DB_PORT")
    db_name:     str = Field("dashboard", alias="DB_NAME")
    db_user:     str = Field("",          alias="DB_USER")
    db_password: str = Field("",          alias="DB_PASSWORD")

    # ------------------------------------------------------------------
    # SQLite — matches your existing project path
    # ------------------------------------------------------------------
    db_path: str = Field("database/sales.db", alias="DB_PATH")

    # ------------------------------------------------------------------
    # MongoDB
    # ------------------------------------------------------------------
    mongo_uri: str = Field("mongodb://localhost:27017", alias="MONGO_URI")

    # ------------------------------------------------------------------
    # Connection pool (PostgreSQL / MySQL only)
    # ------------------------------------------------------------------
    db_pool_min: int = Field(2,  alias="DB_POOL_MIN")
    db_pool_max: int = Field(10, alias="DB_POOL_MAX")

    # ------------------------------------------------------------------
    # Query timeout in seconds
    # ------------------------------------------------------------------
    db_query_timeout_seconds: int = Field(30, alias="DB_QUERY_TIMEOUT")

    def dsn(self) -> str:
        """Returns a connection string for the configured database."""
        if self.db_type == DBType.SQLITE:
            return f"sqlite:///{self.db_path}"
        if self.db_type == DBType.POSTGRESQL:
            return (
                f"postgresql://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        if self.db_type == DBType.MYSQL:
            return (
                f"mysql://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        if self.db_type == DBType.MONGODB:
            return self.mongo_uri
        raise ValueError(f"Unknown db_type: {self.db_type}")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "populate_by_name": True,
    }


# Module-level singleton — import this everywhere
settings = Settings()