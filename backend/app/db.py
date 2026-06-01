"""3-DB 연결 헬퍼.

- MariaDB: 컨텍스트매니저 mariadb_conn() (요청마다 열고 닫음)
- Neo4j / Qdrant: 드라이버/클라이언트 싱글톤
"""
from __future__ import annotations

from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor
from neo4j import GraphDatabase
from qdrant_client import QdrantClient

from .config import settings

_neo4j_driver = None
_qdrant_client = None


@contextmanager
def mariadb_conn():
    conn = pymysql.connect(
        host=settings.mariadb_host,
        port=settings.mariadb_port,
        user=settings.mariadb_user,
        password=settings.mariadb_password,
        database=settings.mariadb_database,
        charset="utf8mb4",
        cursorclass=DictCursor,
    )
    try:
        yield conn
    finally:
        conn.close()


def neo4j():
    global _neo4j_driver
    if _neo4j_driver is None:
        _neo4j_driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
    return _neo4j_driver


def qdrant():
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    return _qdrant_client
