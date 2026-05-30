-- ============================================================================
-- POLARIS MariaDB 스키마 (시연 사이클)
-- 참조: Pipeline_최종설계/05_3DB_물리스키마.md §4
--
-- 적용:  scripts/db/init_mariadb.py 가 본 파일을 읽어 실행.
--        idempotent — IF NOT EXISTS / 중복 실행 안전.
-- ============================================================================

-- 1. active_run_manifest — 검색 active + 인입 standby 슬롯 (단일 진실 소스)
CREATE TABLE IF NOT EXISTS active_run_manifest (
  id                       INT PRIMARY KEY DEFAULT 1,
  -- active 슬롯 (검색)
  active_run_id            VARCHAR(64)  DEFAULT NULL,
  active_qdrant_collection VARCHAR(128) DEFAULT NULL,
  active_mariadb_schema    VARCHAR(64)  DEFAULT 'polaris',  -- 시연: 단일 schema, 운영 확장 옵션
  active_neo4j_run_id      VARCHAR(64)  DEFAULT NULL,
  -- standby 슬롯 (인입)
  standby_run_id            VARCHAR(64)  DEFAULT NULL,
  standby_qdrant_collection VARCHAR(128) DEFAULT NULL,
  standby_mariadb_schema    VARCHAR(64)  DEFAULT 'polaris',
  standby_neo4j_run_id      VARCHAR(64)  DEFAULT NULL,
  -- 메타
  switched_at        DATETIME     DEFAULT NULL,
  standby_started_at DATETIME     DEFAULT NULL,
  standby_status     ENUM('empty','ingesting','verifying','ready_to_promote','cleanup_pending') DEFAULT 'empty',
  notes              JSON         DEFAULT NULL,
  CHECK (id = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 단일 행 보장 (없으면 한 줄 삽입)
INSERT IGNORE INTO active_run_manifest (id, standby_status) VALUES (1, 'empty');


-- 2. document_index — 문서 메타 + LLM 요약 (b3 산출물의 RDB 미러)
CREATE TABLE IF NOT EXISTS document_index (
  rcept_no         VARCHAR(14) NOT NULL,
  run_id           VARCHAR(64) NOT NULL,
  corp_code        VARCHAR(8)  NOT NULL,
  corp_name        VARCHAR(64),
  doc_type         VARCHAR(128),
  date             DATE,
  title            VARCHAR(256),
  filer            VARCHAR(128),
  summary_short    TEXT,
  summary_method   VARCHAR(32),
  summary_verified TINYINT(1) DEFAULT 0,
  key_facts        JSON,
  snapshot_path    VARCHAR(256),
  hash16           VARCHAR(16),
  page_index       JSON,
  body_chars       INT,
  pipeline_version VARCHAR(32),
  PRIMARY KEY (rcept_no, run_id),
  KEY idx_run (run_id),
  KEY idx_corp_date (corp_code, date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- 3. chunk_index — Qdrant point ↔ raw 본문 join 진입점 (T4 룰의 RDB 측)
CREATE TABLE IF NOT EXISTS chunk_index (
  chunk_id         VARCHAR(16) NOT NULL,
  run_id           VARCHAR(64) NOT NULL,
  corp_code        VARCHAR(8)  NOT NULL,
  rcept_no         VARCHAR(14),
  chunk_type       VARCHAR(32) NOT NULL,    -- 'table_nl', 'text_micro', 'text_macro'
  endpoint         VARCHAR(128),
  variant          VARCHAR(32),
  bsns_year        SMALLINT NULL,
  reprt_code       VARCHAR(8) NULL,
  fs_div           VARCHAR(8) NULL,
  section_path     VARCHAR(256),
  token_count      INT,
  embedding_text   MEDIUMTEXT,                -- payload 분리 원칙. 의미 검색은 Qdrant.
  llm_context_text MEDIUMTEXT,
  pipeline_version VARCHAR(32),
  ingest_status    ENUM('pending','ready') DEFAULT 'pending',
  ready_at         DATETIME DEFAULT NULL,
  PRIMARY KEY (chunk_id, run_id),
  KEY idx_run (run_id),
  KEY idx_corp_type (corp_code, chunk_type),
  KEY idx_rcept (rcept_no),
  KEY idx_status (ingest_status, run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- 4. chunk_summary — text 청크 요약 sidecar (Claude 임시 → qwen 정식 교체 가능)
CREATE TABLE IF NOT EXISTS chunk_summary (
  chunk_id         VARCHAR(16) NOT NULL,
  run_id           VARCHAR(64) NOT NULL,
  corp_code        VARCHAR(8),
  summary          TEXT,
  summary_method   VARCHAR(32) NOT NULL,    -- 'claude_temp' | 'qwen_local_v1' | 'pending'
  summary_version  VARCHAR(16),
  pipeline_version VARCHAR(32),
  updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (chunk_id, run_id),
  KEY idx_method (summary_method)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- 5. news_matched — 뉴스 회사 매칭 (b4 산출물)
CREATE TABLE IF NOT EXISTS news_matched (
  news_id          VARCHAR(64) NOT NULL,
  run_id           VARCHAR(64) NOT NULL,
  url              VARCHAR(1024),
  title            VARCHAR(512),
  published        DATETIME,
  publisher        VARCHAR(128),
  matched_corps    JSON,             -- ["00126380","00164779"]
  rule_hits        JSON,
  llm_hits         JSON,
  method           VARCHAR(16),       -- rule | llm | none
  pipeline_version VARCHAR(32),
  PRIMARY KEY (news_id, run_id),
  KEY idx_run (run_id),
  KEY idx_published (published)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- 6. dart_raw_index — DART API 정형 JSON 원본 (SSOT).
--    raw_path = 상대 경로 (DATA_ROOT 기준, 'rawData/{cc}/dart/...').
--    body_json = JSON 본문 LONGTEXT. SSOT - 파일은 백업·캐시.
CREATE TABLE IF NOT EXISTS dart_raw_index (
  corp_code        VARCHAR(8)  NOT NULL,
  rcept_no         VARCHAR(14),
  endpoint         VARCHAR(128) NOT NULL,
  hash8            VARCHAR(8)  NOT NULL,  -- params_hash (sha1[:8])
  raw_path         VARCHAR(256) NOT NULL, -- 상대 경로 (DATA_ROOT 기준)
  body_json        LONGTEXT NULL,         -- DART JSON 본문 전체
  status           VARCHAR(16),
  collected_at     DATETIME,
  run_id           VARCHAR(64) NOT NULL,
  PRIMARY KEY (corp_code, endpoint, hash8, run_id),
  KEY idx_corp (corp_code),
  KEY idx_endpoint (endpoint),
  KEY idx_rcept (rcept_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- 기존 dart_raw_index 에 body_json 추가 (idempotent, MariaDB 10.5+).
ALTER TABLE dart_raw_index ADD COLUMN IF NOT EXISTS body_json LONGTEXT NULL;


-- 7. news_raw — 뉴스 원문 SSOT (파일 대신 DB 기준).
--    raw json (title, body, url 등) 전체 + 매칭 결과 (meta JSON).
CREATE TABLE IF NOT EXISTS news_raw (
  news_id      VARCHAR(64)  NOT NULL PRIMARY KEY,
  feed_id      VARCHAR(64),
  publisher    VARCHAR(64),
  category     VARCHAR(64),
  title        VARCHAR(500),
  url          VARCHAR(1024),
  published    DATETIME,
  fetched_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
  body         LONGTEXT,           -- 원문 전체 (readability 정제 후)
  meta         JSON,               -- {matched_corps, rule_hits, llm_hits, method, ...}
  KEY idx_feed (feed_id),
  KEY idx_pub (publisher, published),
  KEY idx_published (published)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
