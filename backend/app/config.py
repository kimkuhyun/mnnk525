"""환경 설정 — .env 에서 로드 (pydantic-settings).

3DB 접속값은 pola docker 와 동일 기본값. 배포 시 .env 로 서버 DB 주소 주입.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # MariaDB
    mariadb_host: str = "localhost"
    mariadb_port: int = 3307
    mariadb_user: str = "polaris"
    mariadb_password: str = "polaris_dev_only"
    mariadb_database: str = "polaris"

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "polaris_dev_only"

    # CORS (프론트 주소)
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
