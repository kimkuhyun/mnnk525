"""3DB 커넥션 — pola 와 동일한 DB를 읽는다 (적재는 pola CLI, 조회는 여기).

향후 검색·GraphRAG 로직은 pola 의 polaris 패키지를 재사용할 수 있음
(예: `pip install -e ../pola` 후 `from polaris.retrieve import ...`). 지금은 직접 쿼리.
"""
from __future__ import annotations

import pymysql
from neo4j import GraphDatabase
from qdrant_client import QdrantClient

from .config import settings


def mariadb() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=settings.mariadb_host, port=settings.mariadb_port,
        user=settings.mariadb_user, password=settings.mariadb_password,
        database=settings.mariadb_database, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def qdrant() -> QdrantClient:
    return QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)


_neo4j_driver = None


def neo4j():
    global _neo4j_driver
    if _neo4j_driver is None:
        _neo4j_driver = GraphDatabase.driver(
            settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
        )
    return _neo4j_driver
