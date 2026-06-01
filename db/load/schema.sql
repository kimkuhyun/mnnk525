-- POLARIS MariaDB 스키마 (설계 SSOT: docs/DBdocs/01_mariadb.md)
-- 5테이블 전부 IF NOT EXISTS 로 생성. 모두 InnoDB / utf8mb4. 멱등.

CREATE TABLE IF NOT EXISTS dart_raw_index (
  corp_code    VARCHAR(8)   NOT NULL,
  endpoint     VARCHAR(128) NOT NULL,
  hash8        VARCHAR(8)   NOT NULL,
  rcept_no     VARCHAR(14)  NULL,
  body_json    LONGTEXT     NULL,
  status       VARCHAR(16)  NULL,
  collected_at DATETIME     NULL,
  PRIMARY KEY (corp_code, endpoint, hash8)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS document_index (
  rcept_no      VARCHAR(14)  NOT NULL,
  corp_code     VARCHAR(8)   NULL,
  corp_name     VARCHAR(64)  NULL,
  doc_type      VARCHAR(128) NULL,
  date          DATE         NULL,
  title         VARCHAR(256) NULL,
  summary_short TEXT         NULL,
  PRIMARY KEY (rcept_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS chunk_index (
  chunk_id       VARCHAR(16)  NOT NULL,
  corp_code      VARCHAR(8)   NULL,
  rcept_no       VARCHAR(14)  NULL,
  chunk_type     VARCHAR(32)  NULL,
  section_path   VARCHAR(256) NULL,
  embedding_text MEDIUMTEXT   NULL,
  token_count    INT          NULL,
  ingest_status  ENUM('pending','ready') NOT NULL DEFAULT 'pending',
  PRIMARY KEY (chunk_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS fin_metric (
  metric_id  VARCHAR(32)  NOT NULL,
  corp_code  VARCHAR(8)   NULL,
  rcept_no   VARCHAR(14)  NULL,
  bsns_year  SMALLINT     NULL,
  reprt_code VARCHAR(8)   NULL,
  account_id VARCHAR(255) NULL,
  value      DECIMAL(28,2) NULL,
  unit       VARCHAR(16)  NULL,
  fs_div     VARCHAR(8)   NULL,
  PRIMARY KEY (metric_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS extraction_provenance (
  prov_id      VARCHAR(32) NOT NULL,
  subject_id   VARCHAR(64) NULL,
  predicate    VARCHAR(32) NULL,
  object_id    VARCHAR(64) NULL,
  chunk_id     VARCHAR(16) NULL,
  rcept_no     VARCHAR(14) NULL,
  extracted_by VARCHAR(16) NULL,
  confidence   FLOAT       NULL,
  PRIMARY KEY (prov_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
