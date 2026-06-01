# 엔티티 해소(Entity Resolution) — `needs_er` 노트

> 그래프(Neo4j)에 적재된 회사 노드 중 아직 공식 회사코드로 확정되지 않은 것들에 대한 메모. 다음 ER 단계 전까지 보존.

## `needs_er` 가 뭔가

Claude가 청크 본문에서 관계를 추출할 때 **회사 이름**(예: "Qualcomm", "삼성전기㈜", "Apple", "Micron")이 등장한다. 우리 시스템의 회사 노드는 **`corp_code`(DART 8자리)** 로 식별하는데:

- 3사(삼성전자 `00126380` · SK하이닉스 `00164779` · 한미반도체 `00161383`)는 코드를 알아 해당 노드에 바로 연결.
- 그 외 이름들은 corp_code를 모름 → **이름(`er_name`)으로 임시 Organization 노드 생성 + 속성 `needs_er=true`** 부여.

즉 `needs_er=true` = "이 회사 노드는 아직 진짜 회사코드로 확정(해소)되지 않은 이름 기반 임시 노드"라는 꼬리표다.

## 왜 생겼고 왜 지금은 괜찮은가

- 대부분 **수집 범위 밖**: Qualcomm·Apple·Micron·TSMC 등 해외사(애초에 DART corp_code 없음), 또는 삼성전기·삼성SDI 등 국내 계열사(코드는 있으나 아직 매핑 안 함).
- 관계(엣지)와 근거(`extraction_provenance`)는 **정상 적재**됨. 이름 노드가 공식 엔티티로 확정만 안 된 상태이며 **데이터 손상이 아니다.**
- 현재 약 **650개** 노드가 `needs_er=true`.

## 다음 ER 단계에서 할 일

1. **이름 변형 통합**: `삼성전기㈜` = `삼성전기` = `Samsung Electro-Mechanics` 를 한 엔티티로 병합.
2. **국내사 corp_code 연결**: 설계의 Qdrant `polaris-org-er` 컬렉션(회사명 임베딩 매칭)으로 DART corp_code 부여.
3. **해외사 확정**: corp_code 없는 외부 회사로 라벨링(예: `is_foreign=true`).
4. **쓰레기 제거**: 표 합계행이 이름으로 잘못 들어간 `계`·`합계` 2개 노드 삭제(Opus 검증에서 발견).

→ 해소 후 회사 이름이 여러 노드로 쪼개지지 않아 멀티홉 질의가 깔끔해진다.

## 관련
- 설계: `docs/DBdocs/03_neo4j.md`(Organization 노드), `docs/DBdocs/02_qdrant.md`(`polaris-org-er`).
- 적재 코드: `db/graph/extract_helpers.py`(`resolve_org` — 3사 corp_code / 그 외 needs_er).
