"""에스앤에스텍 청크 조회 스크립트."""
import pymysql
import pymysql.cursors

conn = pymysql.connect(
    host='localhost', port=3307, user='polaris', password='polaris_dev_only',
    database='polaris', cursorclass=pymysql.cursors.DictCursor, charset='utf8mb4'
)
cur = conn.cursor()

# 1) 블랭크마스크/펠리클 제품 관련 청크
cur.execute("""
SELECT chunk_id, rcept_no, section_path, SUBSTRING(embedding_text, 1, 500) as txt
FROM chunk_index
WHERE corp_code='00411048' AND chunk_type='text_micro'
AND (embedding_text LIKE '%블랭크마스크%' OR embedding_text LIKE '%펠리클%'
     OR embedding_text LIKE '%블랭크 마스크%' OR embedding_text LIKE '%Blank Mask%'
     OR embedding_text LIKE '%EUV%')
ORDER BY chunk_id
""")
rows = cur.fetchall()
print(f"=== 제품(블랭크마스크/펠리클/EUV) 관련 text_micro {len(rows)}건 ===")
for r in rows:
    print(f"--- {r['chunk_id']} | {r['rcept_no']} | {r['section_path']}")
    print(r['txt'][:400])
    print()

# 2) 매출처/공급처 관련 청크 (삼성/SK/고객)
cur.execute("""
SELECT chunk_id, rcept_no, section_path, SUBSTRING(embedding_text, 1, 500) as txt
FROM chunk_index
WHERE corp_code='00411048' AND chunk_type='text_micro'
AND (embedding_text LIKE '%삼성전자%' OR embedding_text LIKE '%SK하이닉스%'
     OR embedding_text LIKE '%매출처%' OR embedding_text LIKE '%주요 고객%'
     OR embedding_text LIKE '%납품%')
ORDER BY chunk_id
""")
rows2 = cur.fetchall()
print(f"=== 매출처/고객사 관련 text_micro {len(rows2)}건 ===")
for r in rows2:
    print(f"--- {r['chunk_id']} | {r['rcept_no']} | {r['section_path']}")
    print(r['txt'][:400])
    print()

# 3) 기술 관련 청크
cur.execute("""
SELECT chunk_id, rcept_no, section_path, SUBSTRING(embedding_text, 1, 500) as txt
FROM chunk_index
WHERE corp_code='00411048' AND chunk_type='text_micro'
AND (embedding_text LIKE '%ArF%' OR embedding_text LIKE '%KrF%'
     OR embedding_text LIKE '%포토마스크%' OR embedding_text LIKE '%노광%'
     OR embedding_text LIKE '%반도체%' OR embedding_text LIKE '%LCD%')
AND section_path LIKE '%II%'
ORDER BY chunk_id LIMIT 40
""")
rows3 = cur.fetchall()
print(f"=== 기술(반도체/ArF/KrF/포토마스크) 관련 II섹션 {len(rows3)}건 ===")
for r in rows3:
    print(f"--- {r['chunk_id']} | {r['rcept_no']} | {r['section_path']}")
    print(r['txt'][:400])
    print()

# 4) 특수관계자 table_nl 청크
cur.execute("""
SELECT chunk_id, rcept_no, section_path, SUBSTRING(embedding_text, 1, 600) as txt
FROM chunk_index
WHERE corp_code='00411048' AND chunk_type='table_nl'
AND embedding_text LIKE '%특수관계%'
ORDER BY chunk_id
""")
rows4 = cur.fetchall()
print(f"=== 특수관계자 table_nl {len(rows4)}건 ===")
for r in rows4:
    print(f"--- {r['chunk_id']} | {r['rcept_no']} | {r['section_path']}")
    print(r['txt'][:500])
    print()

conn.close()
