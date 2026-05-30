"""환경 설정 — .env 에서 로드 (pydantic-settings).

3DB 접속값은 pola docker 와 동일 기본값. 배포 시 .env 로 서버 DB 주소 주입.
"""
from __future__ import annotations

import logging
import os

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

# 운영(POLARIS_ENV=prod)인데 dev 기본 비밀번호면 경고 — 조용한 dev 크리덴셜 기동 방지.
if os.environ.get("POLARIS_ENV", "").lower() in ("prod", "production") and (
    "dev_only" in settings.mariadb_password or "dev_only" in settings.neo4j_password
):
    logging.getLogger("polaris.backend.config").warning(
        "[보안] POLARIS_ENV=prod 인데 DB 비밀번호가 dev 기본값입니다 — .env 로 실제 값을 주입하세요."
    )
