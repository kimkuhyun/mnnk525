"""DART JSON → 자연어 변환 휴리스틱 (chunk_table.py fork).

옛 polaris/pipeline/chunk_table.py 의 변환 함수들을 그대로 가져옴 + B-4 영문 한국어화.
출력 wrapping은 run_stage_c1.py에서 hash16 + 3 필드 분리로 처리.
"""
from __future__ import annotations
import re
from typing import Callable
from .field_names import translate_field, translate_kv_pairs


# =========================================================================
# 단위·날짜 헬퍼 (chunk_table.py 43~95)
# =========================================================================

def to_int(v) -> int | None:
    if v is None: return None
    s = str(v).strip().replace(",", "")
    if not s or s in ("-", "—"): return None
    if s.startswith("(") and s.endswith(")"): s = "-" + s[1:-1]
    try: return int(float(s))
    except: return None


def format_krw(v) -> str:
    n = to_int(v)
    if n is None: return "(공시되지 않음)"
    abs_n = abs(n)
    base = f"{n:,}원"
    if abs_n >= 10**12: scale = f"{n/1e12:.1f}조원"
    elif abs_n >= 10**8: scale = f"{n/1e8:.1f}억원"
    elif abs_n >= 10**4: scale = f"{n/1e4:.1f}만원"
    else: return base
    return f"{base} (약 {scale})"


def yoy_pct(cur, prev) -> str:
    cn = to_int(cur); pn = to_int(prev)
    if cn is None or pn is None or pn == 0: return "전년 자료 없음"
    pct = (cn - pn) / abs(pn) * 100
    return f"{abs(pct):.1f}% {'증가' if pct >= 0 else '감소'}"


def normalize_date(s) -> str:
    if not s: return ""
    s = str(s).strip()
    m = re.match(r"^(\d{4})[.\-/]?(\d{2})[.\-/]?(\d{2})", s)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else s


def safe_year(item: dict) -> int:
    raw = str(item.get("bsns_year") or "").strip()
    m = re.search(r"\b(20\d{2})\b", raw)
    if m: return int(m.group(1))
    stlm = str(item.get("stlm_dt") or "")
    m = re.search(r"\b(20\d{2})\b", stlm)
    if m: return int(m.group(1))
    rcept = item.get("rcept_no") or ""
    if rcept and rcept[:4].isdigit(): return int(rcept[:4])
    return 0


# doc_type → reprt_code 매핑 (월 → 분기 보고서 코드).
# 11011 사업보고서(연간) / 11012 반기 / 11013 1분기 / 11014 3분기
_REPRT_BY_MONTH = {"03": "11013", "06": "11012", "09": "11014", "12": "11011"}


def parse_doc_type(doc_type: str) -> dict:
    """문서 종류 문자열에서 bsns_year·reprt_code 추출.

    예시:
      "사업보고서 (2025.12)"  → {"bsns_year": 2025, "reprt_code": "11011"}
      "반기보고서 (2025.06)" → {"bsns_year": 2025, "reprt_code": "11012"}
      "분기보고서 (2025.03)" → {"bsns_year": 2025, "reprt_code": "11013"}
      "분기보고서 (2025.09)" → {"bsns_year": 2025, "reprt_code": "11014"}
      "자기주식취득결과보고서" → {"bsns_year": None, "reprt_code": None}

    결정공시·이벤트성 doc_type 은 보고서 연도 개념이 없어 None 반환.
    """
    if not doc_type:
        return {"bsns_year": None, "reprt_code": None}
    m = re.search(r"\((20\d{2})[.\-/](\d{2})\)", doc_type)
    if not m:
        return {"bsns_year": None, "reprt_code": None}
    year = int(m.group(1))
    month = m.group(2)
    reprt = _REPRT_BY_MONTH.get(month)
    return {"bsns_year": year, "reprt_code": reprt}


SJ_MAP = {"BS":"재무상태표","IS":"손익계산서","CIS":"포괄손익계산서","CF":"현금흐름표","SCE":"자본변동표"}

KEY_FINANCIAL_ACCOUNTS = {
    "ifrs-full_Revenue", "ifrs-full_RevenueFromSaleOfGoods",
    "ifrs-full_GrossProfit",
    "ifrs-full_ProfitLossFromOperatingActivities", "dart_OperatingIncomeLoss",
    "ifrs-full_ProfitLoss", "ifrs-full_ComprehensiveIncome",
    "ifrs-full_Assets", "ifrs-full_Liabilities", "ifrs-full_Equity",
    "ifrs-full_CashFlowsFromUsedInOperatingActivities",
}


# =========================================================================
# converter — 각 함수는 list[dict] 반환 (variant·content·meta)
# dict: {variant: str, content: str, section_path: list[str], extra_meta: dict}
# =========================================================================

def nl_fin_account_all(corp_name: str, item: dict) -> list[dict]:
    fs = "연결" if item.get("fs_div") == "CFS" else "별도"
    sj = SJ_MAP.get(item.get("sj_div", ""), item.get("sj_nm", ""))
    acc_nm = item.get("account_nm", "?")
    acc_id = item.get("account_id", "")
    bsns_year = safe_year(item)

    cur = item.get("thstrm_amount"); prev = item.get("frmtrm_amount"); prev2 = item.get("bfefrmtrm_amount")
    cur_fmt = format_krw(cur); prev_fmt = format_krw(prev)
    yoy = yoy_pct(cur, prev)

    out = []
    full = (f"{corp_name}({item.get('corp_code','')})의 {bsns_year}년 사업보고서 "
            f"{fs}재무제표 {sj} 항목 '{acc_nm}'(account_id={acc_id})은 "
            f"{cur_fmt}이며, 전년 {prev_fmt} 대비 {yoy}.")
    out.append({"variant":"full","content":full,"section_path":["III."],
                "extra_meta":{"fs_div":item.get("fs_div"),"sj_div":item.get("sj_div"),
                              "account_id":acc_id}})
    if acc_id in KEY_FINANCIAL_ACCOUNTS:
        n_cur = to_int(cur)
        if n_cur is not None:
            key_text = f"{corp_name} {bsns_year}년 {fs} {acc_nm} {n_cur:,}원"
            out.append({"variant":"key","content":key_text,"section_path":["III."],
                        "extra_meta":{"fs_div":item.get("fs_div"),"sj_div":item.get("sj_div"),
                                      "account_id":acc_id}})
    if prev2 is not None and to_int(prev2) is not None:
        yoy2 = yoy_pct(prev, prev2)
        prev2_fmt = format_krw(prev2)
        comp = (f"{corp_name} {fs} {acc_nm} 3기 추이: {prev2_fmt} → {prev_fmt} → {cur_fmt} "
                f"(직전년 {yoy2}, 당기년 {yoy}).")
        out.append({"variant":"comparison","content":comp,"section_path":["III."],
                    "extra_meta":{"fs_div":item.get("fs_div"),"sj_div":item.get("sj_div"),
                                  "account_id":acc_id}})
    return out


def nl_single_indx(corp_name: str, item: dict) -> list[dict]:
    bsns_year = safe_year(item)
    idx_nm = item.get("idx_nm", "?")
    idx_val = item.get("idx_val")
    out = []
    full = f"{corp_name}({item.get('corp_code','')})의 {bsns_year}년 재무지표 '{idx_nm}'은 {idx_val}."
    out.append({"variant":"full","content":full,"section_path":["III."],
                "extra_meta":{"idx_cd":item.get("idx_cd"),"idx_cl_code":item.get("idx_cl_code")}})
    if idx_val is not None and str(idx_val).strip():
        out.append({"variant":"key","content":f"{corp_name} {bsns_year}년 {idx_nm} {idx_val}",
                    "section_path":["III."],
                    "extra_meta":{"idx_cd":item.get("idx_cd")}})
    return out


def nl_audit_opinion(corp_name: str, item: dict) -> list[dict]:
    bsns_year = safe_year(item)
    adtor = item.get("adtor", "?")
    opinion = item.get("adt_opinion", "?")
    kam = item.get("core_adt_matter") or "공시되지 않음"
    emph = item.get("emphs_matter") or "없음"
    spc = item.get("adt_reprt_spcmnt_matter") or "없음"
    content = (f"{corp_name}({item.get('corp_code','')})의 {bsns_year}년 사업보고서 "
               f"회계감사인은 {adtor}이며, 감사의견은 '{opinion}'이다. "
               f"강조사항: {emph}. 감사보고서 특기사항: {spc}. 핵심감사사항(KAM): {kam}")
    return [{"variant":"full","content":content,"section_path":["V."],"extra_meta":{}}]


def nl_executive(corp_name: str, item: dict) -> list[dict]:
    bsns_year = safe_year(item)
    nm = item.get("nm", "?"); sex = item.get("sexdstn", ""); birth = item.get("birth_ym", "")
    ofcps = item.get("ofcps", ""); rgist = item.get("rgist_exctv_at", "")
    fte = item.get("fte_at", ""); chrg = item.get("chrg_job", "")
    career = (item.get("main_career") or "")[:200]
    relate = item.get("mxmm_shrholdr_relate") or "해당 없음"
    tenure_end = normalize_date(item.get("tenure_end_on"))
    content = (f"{corp_name}({item.get('corp_code','')}) {bsns_year}년 임원 '{nm}'"
               f"({sex}, {birth}생)은 {ofcps}({rgist}, {fte}). "
               f"담당: {chrg}. 주요 경력: {career}. "
               f"최대주주와의 관계: {relate}. 임기만료: {tenure_end}.")
    return [{"variant":"full","content":content,"section_path":["VIII."],
             "extra_meta":{"nm":nm,"birth_ym":birth}}]


def nl_largest_shareholder(corp_name: str, item: dict) -> list[dict]:
    bsns_year = safe_year(item)
    nm = item.get("nm", "?"); relate = item.get("relate", "")
    stock_knd = item.get("stock_knd", "")
    bsis_stock = _safe(item.get("bsis_posesn_stock_co"))
    bsis_rate = _safe(item.get("bsis_posesn_stock_qota_rt"))
    trmend_stock = _safe(item.get("trmend_posesn_stock_co"))
    trmend_rate = _safe(item.get("trmend_posesn_stock_qota_rt"))
    content = (f"{corp_name}({item.get('corp_code','')}) {bsns_year}년 최대주주 '{nm}'(관계: {relate}) "
               f"{stock_knd} 보유주식 기초 {bsis_stock} ({bsis_rate}%) → 기말 {trmend_stock} ({trmend_rate}%).")
    return [{"variant":"full","content":content,"section_path":["VII."],
             "extra_meta":{"nm":nm,"relate":relate}}]


def _safe(v, fallback="(공시되지 않음)") -> str:
    """None·공백·'-' → fallback. 그 외는 str(v)."""
    if v is None: return fallback
    s = str(v).strip()
    if s in ("", "-", "—", "None", "null", "N/A"): return fallback
    return s


def nl_dividend(corp_name: str, item: dict) -> list[dict]:
    bsns_year = safe_year(item)
    se = item.get("se", ""); stock_knd = item.get("stock_knd", "보통주")
    thstrm = _safe(item.get("thstrm")); frmtrm = _safe(item.get("frmtrm")); lwfr = _safe(item.get("lwfr"))
    full = f"{corp_name} {bsns_year}년 {stock_knd} 항목 '{se}': 당기 {thstrm}, 전기 {frmtrm}, 전전기 {lwfr}."
    comp = f"{corp_name} {stock_knd} '{se}' 3기 추이: {lwfr} → {frmtrm} → {thstrm}."
    return [
        {"variant":"full","content":full,"section_path":["I."],"extra_meta":{"se":se,"stock_knd":stock_knd}},
        {"variant":"comparison","content":comp,"section_path":["I."],"extra_meta":{"se":se,"stock_knd":stock_knd}},
    ]


def nl_treasury_status(corp_name: str, item: dict) -> list[dict]:
    bsns_year = safe_year(item)
    stock_knd = item.get("stock_knd", "")
    bsis = _safe(item.get("bsis_qy")); chg_acqs = _safe(item.get("change_qy_acqs"))
    chg_dsps = _safe(item.get("change_qy_dsps")); trmend = _safe(item.get("trmend_qy"))
    # 모든 값이 공시X면 빈 청크 → skip
    if all(v == "(공시되지 않음)" for v in [bsis, chg_acqs, chg_dsps, trmend]):
        return []
    content = (f"{corp_name} {bsns_year}년 자기주식 {stock_knd}: "
               f"기초 {bsis} → 취득 {chg_acqs}, 처분 {chg_dsps} → 기말 {trmend}.")
    return [{"variant":"full","content":content,"section_path":["I."],"extra_meta":{"stock_knd":stock_knd}}]


def nl_other_invest(corp_name: str, item: dict) -> list[dict]:
    """타법인 출자 (otrCprInvstmntSttus)."""
    bsns_year = safe_year(item)
    inv = item.get("inv_prm", "?")
    purp = item.get("invstmnt_purps", "")
    qty = item.get("trmend_blce_qy", ""); rate = item.get("trmend_blce_qota_rt", "")
    book = format_krw(item.get("trmend_blce_acntbk_amount"))
    content = (f"{corp_name} {bsns_year}년 타법인 출자 — '{inv}' (목적: {purp}). "
               f"기말 잔액 {qty}주 ({rate}%), 장부가액 {book}.")
    return [{"variant":"full","content":content,"section_path":["XII."],
             "extra_meta":{"inv_prm":inv}}]


def nl_employee(corp_name: str, item: dict) -> list[dict]:
    """직원 현황 (empSttus)."""
    bsns_year = safe_year(item)
    sex = item.get("sexdstn", "")
    fo = item.get("fo_bbm", "")
    reg = item.get("rgllbr_co", "")
    contract = item.get("cnttk_co", "")
    avg = item.get("avrg_cnwk_sdytrn", "")
    content = (f"{corp_name} {bsns_year}년 직원 현황 ({sex}, 부문 {fo}): "
               f"정규직 {reg}, 계약직 {contract}, 평균 근속 {avg}년.")
    return [{"variant":"full","content":content,"section_path":["VIII."],
             "extra_meta":{"fo_bbm":fo,"sexdstn":sex}}]


def nl_compensation(corp_name: str, item: dict) -> list[dict]:
    """이사·감사 보수 (hmvAuditAllSttus / hmvAuditIndvdlBySttus / indvdlByPay)."""
    bsns_year = safe_year(item)
    nm = item.get("nm", "") or item.get("nmpr", "")
    ofcps = item.get("ofcps", "")
    total = format_krw(item.get("mendng_totamt"))
    avg = format_krw(item.get("jan_avrg_mendng_am")) if item.get("jan_avrg_mendng_am") else ""
    content = (f"{corp_name} {bsns_year}년 보수 — '{nm}' {ofcps}: 총액 {total}{('; 평균 '+avg) if avg else ''}.")
    return [{"variant":"full","content":content,"section_path":["VIII."],"extra_meta":{"nm":nm}}]


def nl_event_generic(label: str, section: str) -> Callable:
    """DS005 결정공시 등 일반 이벤트. 영문 필드 → 한국어 자동 변환."""
    EXCLUDE = {"rcept_no","corp_code","corp_name","corp_cls","rcept_dt"}
    def converter(corp_name: str, item: dict) -> list[dict]:
        rcept_dt = normalize_date(item.get("rcept_dt"))
        kv = translate_kv_pairs(item, exclude=EXCLUDE)
        flat = ", ".join(kv)
        content = (f"{corp_name}({item.get('corp_code','')})는 {rcept_dt} {label} 결정. "
                   f"세부: {flat[:800]}")
        return [{"variant":"full","content":content,"section_path":[section],"extra_meta":{}}]
    return converter


def nl_generic_table(label: str, section: str) -> Callable:
    """기타 정형 endpoint 일반 변환. 영문 필드 → 한국어 자동 변환.

    section_path = section (예: 'VIII.', 'II.')
    """
    EXCLUDE = {"rcept_no","corp_code","corp_name","corp_cls","stlm_dt"}
    def converter(corp_name: str, item: dict) -> list[dict]:
        bsns_year = safe_year(item)
        kv = translate_kv_pairs(item, exclude=EXCLUDE)
        flat = ", ".join(kv)
        if not flat:
            return []
        content = (f"{corp_name}({item.get('corp_code','')}) {bsns_year}년 {label}: "
                   f"{flat[:800]}")
        return [{"variant":"full","content":content,"section_path":[section],"extra_meta":{}}]
    return converter


# =========================================================================
# Endpoint → converter 매핑
# =========================================================================

CONVERTERS: dict[str, Callable] = {
    # DS003 재무
    "fnlttSinglAcntAll": nl_fin_account_all,
    "fnlttSinglIndx": nl_single_indx,
    "fnlttSinglAcnt": nl_fin_account_all,  # 주요계정 (구조 유사)
    # DS002 정기보고서 주요
    "accnutAdtorNmNdAdtOpinion": nl_audit_opinion,
    "exctvSttus": nl_executive,
    "outcmpnyDrctrNdChangeSttus": nl_executive,  # 사외이사
    "hyslrSttus": nl_largest_shareholder,
    "hyslrChgSttus": nl_largest_shareholder,
    "alotMatter": nl_dividend,
    "tesstkAcqsDspsSttus": nl_treasury_status,
    "otrCprInvstmntSttus": nl_other_invest,
    "empSttus": nl_employee,
    "hmvAuditAllSttus": nl_compensation,
    "hmvAuditIndvdlBySttus": nl_compensation,
    "indvdlByPay": nl_compensation,
    # DS005 이벤트 (결정공시)
    "piicDecsn": nl_event_generic("유상증자", "I."),
    "fricDecsn": nl_event_generic("무상증자", "I."),
    "pifricDecsn": nl_event_generic("유무상증자", "I."),
    "crDecsn": nl_event_generic("감자", "I."),
    "tsstkAqDecsn": nl_event_generic("자기주식 취득", "I."),
    "tsstkDpDecsn": nl_event_generic("자기주식 처분", "I."),
    "tsstkAqTrctrCcDecsn": nl_event_generic("자기주식취득 신탁계약 체결", "I."),
    "tsstkAqTrctrCnsDecsn": nl_event_generic("자기주식취득 신탁계약 해지", "I."),
    "otcprStkInvscrInhDecsn": nl_event_generic("타법인 주식·출자증권 양수 (M&A)", "XII."),
    "otcprStkInvscrTrfDecsn": nl_event_generic("타법인 주식·출자증권 양도", "XII."),
    "bsnInhDecsn": nl_event_generic("영업양수", "XII."),
    "bsnTrfDecsn": nl_event_generic("영업양도", "XII."),
    "cmpDvDecsn": nl_event_generic("회사분할", "XII."),
    "cmpDvmgDecsn": nl_event_generic("회사분할합병", "XII."),
    "othcmpMrgDecsn": nl_event_generic("회사합병", "XII."),
    "stkExtrDecsn": nl_event_generic("주식교환·이전", "XII."),
    "exbdIsDecsn": nl_event_generic("교환사채권 발행", "II."),
    "bdwtIsDecsn": nl_event_generic("신주인수권부사채 발행", "II."),
    "cvbdIsDecsn": nl_event_generic("전환사채 발행", "II."),
    "wdCocobdIsDecsn": nl_event_generic("상각형 조건부자본증권 발행", "II."),
    "lwstLg": nl_event_generic("소송 등 제기", "XII."),
    "tgastInhDecsn": nl_event_generic("유형자산 양수", "XII."),
    "tgastTrfDecsn": nl_event_generic("유형자산 양도", "XII."),
    "asignInhDecsn": nl_event_generic("주식양수도", "XII."),
    "astInhtrfEtcPtbkOpt": nl_event_generic("자산양수도·풋백옵션", "XII."),
    "bsnSp": nl_event_generic("영업정지", "XII."),
    "dfOcr": nl_event_generic("부도발생", "XII."),
    "ctrcvsBgrq": nl_event_generic("회생절차 개시신청", "XII."),
    "dsRsOcr": nl_event_generic("해산사유 발생", "XII."),
    "ovLstDecsn": nl_event_generic("해외증권시장 상장", "XII."),
    "bnkMngtPcbg": nl_event_generic("채권은행 관리절차 개시", "XII."),

    # === F3 추가 — 미매핑 18 endpoint generic 처리 (한국어 자동 변환) ===
    # DS002 정기보고서 주요 (기타)
    "mrhlSttus": nl_generic_table("소액주주현황", "VII."),
    "irdsSttus": nl_generic_table("증감자(자본금) 변동", "I."),
    "pssrpCptalUseDtls": nl_generic_table("공모자금 사용내역", "XI."),
    "prvsrpCptalUseDtls": nl_generic_table("사모자금 사용내역", "XI."),
    # DS002 채권·증권
    "detScritsIsuAcmslt": nl_generic_table("채무증권 발행실적", "II."),
    "entrprsBilScritsNrdmpBlce": nl_generic_table("회사채 미상환 잔액", "II."),
    "srtpdPsndbtNrdmpBlce": nl_generic_table("단기사채 미상환 잔액", "II."),
    "cprndNrdmpBlce": nl_generic_table("기업어음 미상환 잔액", "II."),
    "newCaplScritsNrdmpBlce": nl_generic_table("신종자본증권 미상환 잔액", "II."),
    "cndlCaplScritsNrdmpBlce": nl_generic_table("조건부자본증권 미상환 잔액", "II."),
    # DS002 감사·보수 보조
    "adtServcCnclsSttus": nl_generic_table("감사용역 체결현황", "V."),
    "accnutAdtorNonAdtServcCnclsSttus": nl_generic_table("비감사용역 계약체결", "V."),
    "drctrAdtAllMendngSttusGmtsckConfmAmount": nl_generic_table("이사·감사 보수 주총승인 금액", "VIII."),
    "drctrAdtAllMendngSttusMendngPymntamtTyCl": nl_generic_table("이사·감사 보수 유형별 지급금액", "VIII."),
    "unrstExctvMendngSttus": nl_generic_table("미등기임원 보수현황", "VIII."),
}
