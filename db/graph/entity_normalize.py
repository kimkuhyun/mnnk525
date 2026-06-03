"""Product/Technology 캐논 정규화 + 별칭 레지스트리 (단어집).

목적: 같은 제품이 청크마다 다르게 추출돼 노드가 쪼개지는 문제(예: DDR5가
"256GB DDR5"·"1cnm DDR5"·"DDR5 3DS"로 분산)를 막는다.

2단:
  1) normalize_spec(): 기계적 스펙접두 제거(용량·공정노드·단수·파이 등). 안전·결정론.
  2) ALIASES: 사람이 시드한 별칭→캐논 맵(세대/표기 변형). extract 중 성장.

세대 구분(HBM3 vs HBM4 등)은 의미 있는 차이라 병합하지 않는다 — 캐논만 통일.
"""
from __future__ import annotations

import re

# ── 1) 기계적 스펙접두/수식어 제거 ─────────────────────────
# 제품 정체성과 무관한 스펙 토큰 (앞/중간에 붙는 것)
_SPEC_PATTERNS = [
    r"\b\d+\s*GB\b", r"\b\d+\s*Gb\b", r"\b\d+\s*TB\b", r"\b\d+\s*Tb\b",  # 용량
    r"\b\d+\s*나노급?\b", r"\b\d+\s*nm\b", r"\b1[abc]nm\b",               # 공정노드
    r"\b\d+\s*단\b",                                                       # 적층 단수
    r"\b\d+\s*파이\b",                                                     # 셀 지름
    r"\b\d+\s*세대\b",                                                     # 세대
    r"\b\d+(\.\d+)?\s*Gbps\b",                                            # 속도
    r"\b\d+(\.\d+)?\s*MB/s\b",
]
_SPEC_RE = re.compile("|".join(_SPEC_PATTERNS), re.IGNORECASE)


# 스펙 제거 후 이것만 남으면 = 스펙이 정체성이었다는 뜻 → 원본 유지(과병합 방지)
_GENERIC_REMAINS = {
    "공정", "기술", "장비", "솔루션", "서비스", "제품", "모듈", "소재",
    "공정용 장비", "제조용 장비", "공정 장비",
}


# ── 일반어 블록리스트(엔티티 가치 없음 → 버림) ────────────
_BLOCKLIST = {
    "제품", "상품", "생산품", "소재", "장비", "부품", "용역", "제품군", "상품군",
    "주변기술", "주변 기술", "솔루션", "서비스", "시스템", "기술", "원소재", "원자재",
    "주문생산 장비", "주문장비", "주문제작 장비", "반제품", "재공품", "제품 및 상품",
    # 일반명사·도메인어·스펙 (단독으로는 식별 가치 없음)
    "회사", "옵션", "통신", "전장", "박막", "반도체", "메모리반도체", "디스플레이",
    "8K", "8k", "4K", "4k", "HF", "부문", "사업", "제품 및 서비스", "전자제품", "Set제품",
    "set제품", "완제품", "중간재", "원재료", "상품 및 제품",
}
# 회사명 접미사(Product로 잘못 들어온 조직 식별 → 버림)
_ORG_SUFFIX = ("Inc", "Inc.", "Ltd", "Ltd.", "Co.", "Co.,", "LLC", "Corp", "Corp.",
               "주식회사", "(주)", "㈜", "유한공사", "Pte", "GmbH")
# 일반 수식 접미사 제거(언어 무관 동일화): "CMP 장비"="CMP Equipment"="CMP장비"→"CMP"
_SUFFIX_STRIP = [
    r"\s*(장비|설비)$", r"\s+Equipment$", r"\s+equipment$",
    r"\s*모듈$", r"\s+[Mm]odule$", r"\s*부품$",
]
_SUFFIX_RE = re.compile("|".join(_SUFFIX_STRIP))


def is_blocklisted(name: str) -> bool:
    n = (name or "").strip()
    if not n or n in _BLOCKLIST:
        return True
    # 회사명 접미사로 끝나면 조직 → Product/Tech 아님
    if any(n.endswith(s) or f" {s}" in n for s in _ORG_SUFFIX):
        return True
    return False


def normalize_spec(name: str) -> str:
    """스펙접두 제거 + 공백/구두점 정리. 캐논 키 산출의 1단계.
    단, 제거 후 남는 게 일반어뿐이면(예: '2나노 공정'→'공정') 원본 유지."""
    s = name or ""
    stripped = _SPEC_RE.sub(" ", s)
    stripped = re.sub(r"\s{2,}", " ", stripped).strip().strip(" -·,")
    if not stripped or stripped in _GENERIC_REMAINS:
        # 스펙이 식별자였음 → 원본의 공백/구두점만 정리해서 반환
        return re.sub(r"\s{2,}", " ", (name or "").strip()).strip(" -·,")
    return stripped


# ── 2) 별칭 → 캐논 (사람 시드, 성장) ───────────────────────
# key = normalize_spec 후 소문자, value = (캐논표기, 타입)
# 타입 충돌(Product/Technology 양쪽 등장) 해소도 여기서.
ALIASES: dict[str, tuple[str, str]] = {
    # DRAM 계열
    "dram": ("DRAM", "Product"),
    "dram 모듈": ("DRAM", "Product"),
    "dram(메모리반도체)": ("DRAM", "Product"),
    "메모리": ("DRAM", "Product"),
    "ai 메모리": ("DRAM", "Product"),
    # DDR/LPDDR/GDDR — 세대는 유지, 표기만 통일
    "ddr5 3ds": ("DDR5", "Product"),
    "ddr5 mcr dimm": ("DDR5", "Product"),
    "cmm-ddr": ("CMM-DDR5", "Product"),
    "lpddr4 dram": ("LPDDR4", "Product"),
    "lpddr5t": ("LPDDR5", "Product"),
    "lpddr5x": ("LPDDR5", "Product"),
    # NAND
    "4d nand flash": ("4D NAND", "Product"),
    "4d nand": ("4D NAND", "Product"),
    "3d-v4 nand flash": ("NAND", "Product"),
    "v9 nand": ("NAND", "Product"),
    "nand(메모리반도체)": ("NAND", "Product"),
    "ain(ai-nand) family": ("AIN", "Product"),
    # UFS
    "mobile ufs": ("UFS", "Product"),
    "ufs4.0": ("UFS", "Product"),
    "zufs": ("UFS", "Product"),
    "zufs 4.0": ("UFS", "Product"),
    # SSD — 세대 SSD는 SSD로
    "pcie gen4 ssd": ("SSD", "Product"),
    "pcie gen5 ssd": ("SSD", "Product"),
    "pcie gen6 ssd": ("SSD", "Product"),
    "client ssd": ("SSD", "Product"),
    "qlc ssd": ("SSD", "Product"),
    "csssd": ("SSD", "Product"),
    "cssd": ("SSD", "Product"),
    "엔터프라이즈 ssd(essd)": ("eSSD", "Product"),
    "ps1012 essd": ("eSSD", "Product"),
    # HBM — 세대 유지(HBM/HBM3/HBM3E/HBM4 별개), Base-Die만 정리
    "hbm base-die": ("HBM", "Product"),
    "hbm4 base-die": ("HBM4", "Product"),
    # CIS 표기 변형
    "cmos 이미지 센서(cis)": ("CIS", "Product"),
    "cmos 이미지센서(cis)": ("CIS", "Product"),
    "cis(cmos image sensor)": ("CIS", "Product"),
    "이미지 센서": ("CIS", "Product"),
    # 타입 충돌 해소(Technology로 고정)
    "foundry": ("Foundry", "Technology"),
    "cxl": ("CXL", "Technology"),
    "cxl 메모리": ("CXL", "Technology"),
    "qlc": ("QLC", "Technology"),
    # ── 케이씨텍(반도체 소부장) 도메인 별칭 ──
    "cmp": ("CMP 장비", "Product"),
    "cmp equipment": ("CMP 장비", "Product"),
    "cmp 연마 장비": ("CMP 장비", "Product"),
    "new type cmp": ("CMP 장비", "Product"),
    "co2 cleaner": ("CO2 세정기", "Product"),
    "co2 극저온 세정기": ("CO2 세정기", "Product"),
    "co2극저온 세정기": ("CO2 세정기", "Product"),
    "co2 cleaning": ("CO2 세정기", "Product"),
    "co2 cryogenic cleaning": ("CO2 세정기", "Product"),
    "co2 extreme low temperature cleaner": ("CO2 세정기", "Product"),
    "co2 세정": ("CO2 세정기", "Product"),
    "wet station": ("Wet Station", "Product"),
    "single bath auto wet station": ("Wet Station", "Product"),
    "single spin processor": ("Spin Processor", "Product"),
    "hybrid spin scrubber": ("Spin Scrubber", "Product"),
    "wet cleaning system": ("Wet Cleaning System", "Product"),
    "wet cleaning": ("Wet Cleaning System", "Product"),
    "batch type wet cleaning": ("Wet Cleaning System", "Product"),
    "batch type wet cleaner": ("Wet Cleaning System", "Product"),
    "slurry": ("Slurry", "Product"),
    "cmp slurry": ("Slurry", "Product"),
    "ceria slurry": ("Ceria Slurry", "Product"),
    "wet ceria slurry": ("Ceria Slurry", "Product"),
    "ceria 슬러리": ("Ceria Slurry", "Product"),
    "wet ceria 슬러리": ("Ceria Slurry", "Product"),
    "silica slurry": ("Silica Slurry", "Product"),
    "지르코니아": ("Zirconia", "Product"),
    "zirconia optical material": ("Zirconia", "Product"),
    "지르코니아 광학소재": ("Zirconia", "Product"),
    "고기능성 지르코니아 광학소재": ("Zirconia", "Product"),
    "air knife": ("Air Knife", "Product"),
    "광학소재": ("Optical Material", "Product"),
    "optical material": ("Optical Material", "Product"),
    "high-refractive optical material": ("Optical Material", "Product"),
    "고굴절 광학소재": ("Optical Material", "Product"),
    "dry pump": ("Dry Pump", "Product"),
    "디스플레이 장비": ("디스플레이 장비", "Product"),
    "display manufacturing equipment": ("디스플레이 장비", "Product"),
    "디스플레이 제조장비": ("디스플레이 장비", "Product"),
    "디스플레이 생산장비": ("디스플레이 장비", "Product"),
    "디스플레이장비": ("디스플레이 장비", "Product"),
    "반도체 장비": ("반도체 장비", "Product"),
    "반도체장비": ("반도체 장비", "Product"),
    "반도체 제조 장비": ("반도체 장비", "Product"),
    "반도체 제조용 장비": ("반도체 장비", "Product"),
    "반도체제조용 장비": ("반도체 장비", "Product"),
    "반도체 생산장비": ("반도체 장비", "Product"),
    "반도체 소재": ("반도체 소재", "Product"),
    "반도체소재": ("반도체 소재", "Product"),
}


# ── 패밀리 정규화(정규식) — 세대수식·변형을 한 캐논으로 ────
# 3개사 도메인: 삼성 Galaxy/가전/디스플레이 · 한미 본더/검사 · 삼성+하닉 메모리.
# 세대 구분이 의미있는 건(DDR4≠DDR5, HBM3≠HBM4) 패밀리규칙 안 씀 — ALIASES로 변형만.
_FAMILY_RULES = [
    # 삼성 Galaxy/가전/디스플레이
    (r"(?i)^galaxy\s*s\s*\d+", "Galaxy S"),
    (r"(?i)^갤럭시\s*s\s*\d+", "Galaxy S"),
    (r"(?i)^galaxy\s*a\s*\d+", "Galaxy A"),
    (r"(?i)^(galaxy|갤럭시)\s*z\s*(fold|폴드)", "Galaxy Z Fold"),
    (r"(?i)^(galaxy|갤럭시)\s*z\s*(flip|플립)", "Galaxy Z Flip"),
    (r"(?i)^(galaxy|갤럭시)\s*(book|북)", "Galaxy Book"),
    (r"(?i)^galaxy\s*watch", "Galaxy Watch"),
    (r"(?i)^galaxy\s*tab", "Galaxy Tab"),
    (r"(?i)^bespoke", "BESPOKE 가전"),
    (r"(?i)^neo\s*qled", "Neo QLED"),
    (r"(?i)^the\s*frame", "The Frame"),
    # 한미 본더/검사 (FC/DIE 먼저 — TC보다 구체)
    (r"(?i)(flip\s*chip|fc)\s*(bonder|본더)", "FLIP CHIP BONDER"),
    (r"(?i)boc\s*cob\s*(bonder|본더)", "BOC COB BONDER"),
    (r"(?i)die\s*(bonder|본더)", "DIE BONDER"),
    (r"(?i)(hybrid|하이브리드)\s*본?더?", "Hybrid Bonder"),
    (r"(?i)tc\s*(bonder|본더)", "TC BONDER"),
    (r"(?i)^6-?\s*side\s*inspection", "6-SIDE INSPECTION"),
    (r"(?i)^3d\s*vision\s*inspection", "3D VISION INSPECTION"),
    (r"(?i)^micro\s*saw", "micro SAW"),
    (r"(?i)emi\s*shield", "EMI Shield"),
    # 메모리 변형 (세대 유지)
    (r"(?i)^cxl", "CXL"),
    (r"(?i)^cmm-?ddr", "CMM-DDR5"),
    # ── 신규 5개사 도메인 ──
    # 에스앤에스텍·에프에스티: 마스크/펠리클 (장비는 소모품과 구분 — 장비 규칙 먼저)
    (r"(?i)pellicle.*(mount|demount)|펠리클.*(마운트|장착)", "EUV Pellicle Mounter"),
    (r"(?i)pellicle.*(inspection|검사)", "EUV Pellicle Inspection"),
    (r"(?i)(deep\s*uv|duv)\s*(pellicle|펠리클)", "DUV Pellicle"),
    (r"(?i)^euv\s*(pellicle|펠리클)", "EUV Pellicle"),
    (r"(?i)^euv\s*blank\s*?mask|^euv\s*블랭크\s*마스크", "EUV Blank Mask"),
    (r"(?i)^blank\s*?mask|^블랭크\s*마스크", "Blank Mask"),
    (r"(?i)^(co2\s*)?(칠러|chiller)", "Chiller"),
    # 동진: 감광액/식각
    (r"(?i)photoresist", "감광액"),
    (r"(?i)^(반도체\s*)?감광액", "감광액"),
    # 원익IPS: 증착 (CVD-SiC 소재는 장비 아님 — 먼저)
    (r"(?i)cvd-?sic", "CVD-SiC"),
    (r"(?i)pe-?cvd", "CVD"),
    (r"(?i)pe-?ald", "ALD"),
    # 솔브레인: 전해액
    (r"(?i)전해액", "전해액"),
]
_FAMILY_RE = [(re.compile(p), r) for p, r in _FAMILY_RULES]


def _apply_family(spec: str) -> str:
    for rx, repl in _FAMILY_RE:
        if rx.search(spec):
            return repl
    return spec


def canonical(name: str, label: str):
    """(표면형, 추출타입) → (캐논표기, 캐논타입). 블록리스트면 None.
    패밀리정규화 → 별칭 → 접미사제거 후 별칭 재시도 → 스펙정규화 결과."""
    if is_blocklisted(name):
        return None
    spec = _apply_family(normalize_spec(name))
    key = spec.lower()
    if key in ALIASES:
        return ALIASES[key]
    # 일반 접미사(장비/Equipment/모듈/부품) 제거 후 재시도
    stripped = _SUFFIX_RE.sub("", spec).strip()
    if stripped and stripped.lower() in ALIASES:
        return ALIASES[stripped.lower()]
    if is_blocklisted(stripped):  # 접미사 떼니 일반어
        return None
    return (stripped or spec or name, label)


if __name__ == "__main__":
    # 덤프에 적용해 병합 효과 측정
    import json
    from pathlib import Path

    dump = json.loads((Path(__file__).parent / "_entity_dump.json").read_text(encoding="utf-8"))
    for lbl_key, lbl in [("product", "Product"), ("technology", "Technology")]:
        names = dump[lbl_key]
        canon = {}
        for n in names:
            c, t = canonical(n, lbl)
            canon.setdefault(c, []).append(n)
        merged = {c: v for c, v in canon.items() if len(v) > 1}
        print(f"\n=== {lbl}: {len(names)}개 → 캐논 {len(canon)}개 (병합 {len(names)-len(canon)}건) ===")
        for c, v in sorted(merged.items(), key=lambda x: -len(x[1]))[:15]:
            print(f"  {c}  ←  {', '.join(v)}")
