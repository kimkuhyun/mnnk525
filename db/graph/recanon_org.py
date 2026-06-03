"""회사(Organization) ER/캐논화 — 보수적. needs_er 대부분은 진짜 별개 법인이라
명시적 별칭(본사 표기 변형)만 corp_code 노드로 병합 + 모호·일반명사만 삭제.

- ORG_ALIASES: normalize_corp_name(변형) → corp_code. 정식 회사의 약칭/영문/SK↔에스케이만.
  해외자회사("SK hynix America")는 정규화하면 키가 달라 안 걸림(안전).
- ORG_BLOCK: 모호 단독명(삼성·현대)·일반명사(제조업체·고객) → detach delete.
APOC mergeNodes 로 엣지 보존. 멱등.
"""
from __future__ import annotations
import re
import sys
from collections import defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from db import neo4j_driver, normalize_corp_name  # noqa: E402

# 한↔영 동일 토큰(자회사 dedup용). normalize 후 적용.
_HANYEONG = [
    ("하이닉스", "hynix"), ("에스케이", "sk"), ("삼성", "samsung"),
    ("솔브레인", "soulbrain"), ("동진쎄미켐", "dongjin"), ("동진", "dongjin"),
    ("원익아이피에스", "wonikips"), ("원익", "wonik"), ("한미", "hanmi"),
    ("케이씨텍", "kctech"), ("케이씨", "kc"), ("에프에스티", "fst"),
]


def dedup_key(name: str) -> str:
    """구두점·공백·한영차이 무시한 dedup 키. 같은 키 = 같은 법인."""
    k = normalize_corp_name(name)
    for ko, en in _HANYEONG:
        k = k.replace(ko, en)
    return re.sub(r"[^a-z0-9가-힣]", "", k)

# 정식 31개사 본사 표기 변형 → corp_code (정규화 키)
ORG_ALIASES = {
    "skhynix": "00164779", "sk-hynix": "00164779", "하이닉스": "00164779",
    "에스케이하이닉스": "00164779", "sk하이닉스": "00164779",
    "삼성전자": "00126380", "samsungelectronics": "00126380", "삼성전자우": "00126380",
    "한미반도체": "00161383", "hanmisemiconductor": "00161383",
    "케이씨텍": "01261893", "kctech": "01261893",
    "솔브레인": "01489648", "soulbrain": "01489648",
    "동진쎄미켐": "00118804", "dongjinsemichem": "00118804",
    "에스앤에스텍": "00411048", "snstech": "00411048", "s&stech": "00411048", "sns": "00411048",
    "원익아이피에스": "01135941", "원익ips": "01135941", "wonikips": "01135941",
    "에프에스티": "00223434",
    "대덕전자": "01478712", "삼성전기": "00126371", "삼성에스디에스": "00126186",
    "삼성sdi": "00126362", "삼성바이오로직스": "00877059", "삼성디스플레이": "00912006",
    "에스케이스퀘어": "01596425", "sk스퀘어": "01596425", "sksquare": "01596425",
}

# 모호·일반명사 — 삭제(엣지째). 정규화 키.
ORG_BLOCK = {
    "삼성", "현대", "lg", "sk", "kt", "기아", "gm", "롯데", "한화", "포스코",
    "고객", "업체", "도매업체", "제조업체", "반도체칩제조업체", "tft-lcd제조업체",
    "공급사", "협력사", "거래처", "관계사", "계열사", "고객사", "수요자", "납품처",
    "당사", "회사", "기타", "메이커",
}


def _is_generic(name: str) -> bool:
    n = (name or "").strip()
    if normalize_corp_name(n) in ORG_BLOCK:
        return True
    if any(n.endswith(suf) for suf in ("제조업체", "업체", "도매업", "메이커")):
        return True
    return False


def main():
    d = neo4j_driver()
    with d.session() as s:
        nodes = s.run("MATCH (o:Organization) WHERE o.corp_code IS NULL RETURN o.name AS nm, o.er_name AS er").data()
        merged = dropped = 0
        for r in nodes:
            nm = r["nm"] or r["er"] or ""
            key = normalize_corp_name(nm)
            if key in ORG_ALIASES:
                cc = ORG_ALIASES[key]
                s.run("""
                    MATCH (corp:Organization {corp_code:$cc})
                    MATCH (x:Organization {er_name:$er, has_corp_code:false})
                    WHERE elementId(corp)<>elementId(x)
                    CALL apoc.refactor.mergeNodes([corp,x],{properties:'discard',mergeRels:true}) YIELD node
                    RETURN node
                """, cc=cc, er=r["er"])
                merged += 1
            elif _is_generic(nm):
                s.run("MATCH (x:Organization {er_name:$er, has_corp_code:false}) DETACH DELETE x", er=r["er"])
                dropped += 1
        print(f"[merge] 본사변형→corp 병합: {merged}")
        print(f"[drop]  모호·일반명사 삭제: {dropped}")

        # 3) 남은 needs_er 중 dedup_key 같은 것끼리 병합(자회사 구두점·한영 중복)
        remain = s.run("MATCH (o:Organization) WHERE o.corp_code IS NULL RETURN o.er_name AS er, o.name AS nm").data()
        groups = defaultdict(list)
        for r in remain:
            groups[dedup_key(r["nm"] or r["er"] or "")].append(r["er"])
        dedup = 0
        for key, ers in groups.items():
            if len(ers) < 2 or not key:
                continue
            keep = ers[0]
            for other in ers[1:]:
                s.run("""
                    MATCH (a:Organization {er_name:$keep, has_corp_code:false})
                    MATCH (b:Organization {er_name:$other, has_corp_code:false})
                    WHERE elementId(a)<>elementId(b)
                    CALL apoc.refactor.mergeNodes([a,b],{properties:'discard',mergeRels:true}) YIELD node
                    RETURN node
                """, keep=keep, other=other)
                dedup += 1
        print(f"[dedup] 자회사 구두점·한영 중복 병합: {dedup}")

        corp = s.run("MATCH (o:Organization) WHERE o.corp_code IS NOT NULL RETURN count(o)").single()[0]
        er = s.run("MATCH (o:Organization) WHERE o.corp_code IS NULL RETURN count(o)").single()[0]
        print(f"[검증] corp {corp}, needs_er {er}")
    d.close()


if __name__ == "__main__":
    main()
