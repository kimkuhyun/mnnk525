"""연관어 추출 — 뉴스 본문에서 회사별 자주 함께 나온 명사 Top N (썸트렌드식).

kiwi 형태소분석 → 일반/고유명사(NNG/NNP) 빈도 집계 → 회사명·불용어 제외 → keyword_top 적재.
로컬 재현 가능(순수 파이썬, LLM 불필요). 멱등(회사별 DELETE+INSERT).

실행:  uv run python -m polaris.analyze.keywords
"""
from __future__ import annotations

import re
from collections import Counter

from polaris.config import mariadb_conn

TOP_N = 20
MIN_LEN = 2

# 너무 흔하거나 회사 분석에 의미 없는 명사 (불용어)
STOP = {
    "기자", "사진", "지난해", "올해", "내년", "관련", "이번", "지난", "당시", "최근", "이후", "이상", "이하",
    "위해", "통해", "대한", "오전", "오후", "현재", "예정", "계획", "발표", "진행", "추진", "확대", "강화",
    "기업", "회사", "시장", "사업", "분야", "업계", "국내", "글로벌", "세계", "지역", "고객", "제품", "기술",
    "서비스", "부문", "대표", "사장", "부사장", "대비", "기록", "전망", "예상", "보도", "설명", "강조", "밝혀",
    "경우", "가능", "필요", "중요", "다양", "지원", "제공", "운영", "구축", "개발", "출시", "공개", "도입",
    "한국", "미국", "중국", "일본", "유럽", "달러", "억원", "조원", "만원", "퍼센트", "수준", "규모", "정도",
}


def main() -> None:
    from kiwipiepy import Kiwi
    kiwi = Kiwi()

    conn = mariadb_conn(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS keyword_top (
        corp_code VARCHAR(8) NOT NULL,
        rank      INT         NOT NULL,
        term      VARCHAR(64) NOT NULL,
        freq      INT         NOT NULL,
        PRIMARY KEY (corp_code, rank)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    conn.commit()

    # 회사별 뉴스 본문 모으기
    cur.execute("""SELECT corp_code, GROUP_CONCAT(CONCAT(IFNULL(title,''),' ',IFNULL(body,'')) SEPARATOR ' ')
                   FROM document_unified WHERE source_type='news' GROUP BY corp_code""")
    rows = cur.fetchall()

    for corp, text in rows:
        if not text:
            continue
        # 회사 자체 토큰(예: 삼성전자→삼성,전자,삼성전자)도 제외 — kiwi 로 쪼개 제외
        self_toks = SELF_EXCLUDE.get(corp, set())
        nouns = Counter()
        for tok in kiwi.tokenize(text[:2_000_000]):
            if tok.tag in ("NNG", "NNP") and len(tok.form) >= MIN_LEN:
                w = tok.form
                if w in STOP or w in self_toks:
                    continue
                nouns[w] += 1
        top = nouns.most_common(TOP_N)
        cur.execute("DELETE FROM keyword_top WHERE corp_code=%s", (corp,))
        for rank, (term, freq) in enumerate(top, 1):
            cur.execute("INSERT INTO keyword_top (corp_code, rank, term, freq) VALUES (%s,%s,%s,%s)",
                        (corp, rank, term[:64], freq))
        conn.commit()
        print(f"  {corp}: {len(top)} 연관어 (top3: {[t for t,_ in top[:3]]})")

    cur.close(); conn.close()
    print("완료. keyword_top 적재 (회사별 Top20).")


# 자기언급 제외용 — 회사명 + 흔한 약칭 (kiwi 가 "삼성전자"를 통째로 봐서 약칭은 따로 명시)
SELF_EXCLUDE = {
    "00126380": {"삼성전자", "삼성", "전자"},
    "00164779": {"SK하이닉스", "SK", "하이닉스", "에스케이", "에스케이하이닉스"},
    "00161383": {"한미반도체", "한미"},
}


def corp_name_of(cur, corp: str) -> str:
    NAMES = {"00126380": "삼성전자", "00164779": "SK하이닉스", "00161383": "한미반도체"}
    return NAMES.get(corp, "")


if __name__ == "__main__":
    main()
