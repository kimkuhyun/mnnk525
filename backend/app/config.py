"""환경 설정 — .env 에서 로드 (pydantic-settings).

3-DB 접속값은 저장소 루트 docker-compose.yml 의 기본값과 동일.
배포 시 .env 로 실제 값 주입.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # MariaDB (원본·재무·청크·근거)
    mariadb_host: str = "localhost"
    mariadb_port: int = 3307
    mariadb_user: str = "polaris"
    mariadb_password: str = "polaris_dev_only"
    mariadb_database: str = "polaris"

    # Qdrant (벡터 의미검색)
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333

    # Neo4j (관계 그래프)
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "polaris_dev_only"

    # Ollama (임베딩 bge-m3)
    ollama_base: str = "http://localhost:11434"
    ollama_embed_model: str = "bge-m3"

    # Claude (GraphRAG 에이전트)
    anthropic_api_key: str = ""

    # CORS (프론트 주소)
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
