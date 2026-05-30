"""DART API 영문 필드명 → 한국어 매핑 (B-4).

DART OpenAPI 공식 사양 + 실제 응답 빈도 top 200 기반.
nl_event_generic 등에서 raw "key=value" 출력 시 한국어로 변환.

매핑 누락 필드는 영문 그대로 (로그에 기록).
"""
from __future__ import annotations

# Top 200 핵심 필드 한국어 매핑
FIELD_KO: dict[str, str] = {
    # === 공통 메타 ===
    "corp_code": "회사코드", "corp_name": "회사명", "corp_cls": "법인구분",
    "stock_code": "종목코드", "rcept_no": "접수번호", "rcept_dt": "접수일자",
    "bsns_year": "사업연도", "reprt_code": "보고서코드", "stlm_dt": "결산일자",
    "report_nm": "보고서명", "flr_nm": "공시제출인", "repror": "보고자",
    "rm": "비고", "ord": "순번", "currency": "통화",

    # === DS003 재무제표 ===
    "sj_div": "재무제표구분", "sj_nm": "재무제표명",
    "account_id": "표준계정ID", "account_nm": "계정명", "account_detail": "계정상세",
    "fs_div": "재무제표구분(별도연결)", "fs_nm": "재무제표명(별도연결)",
    "thstrm_nm": "당기명", "thstrm_amount": "당기금액", "thstrm_add_amount": "당기누적금액",
    "frmtrm_nm": "전기명", "frmtrm_amount": "전기금액", "frmtrm_add_amount": "전기누적금액",
    "frmtrm_q_nm": "전기분기명", "frmtrm_q_amount": "전기분기금액",
    "bfefrmtrm_nm": "전전기명", "bfefrmtrm_amount": "전전기금액",
    # 재무지표
    "idx_cl_code": "지표분류코드", "idx_cl_nm": "지표분류명",
    "idx_code": "지표코드", "idx_nm": "지표명", "idx_val": "지표값",

    # === DS002 임원·주주·직원 ===
    "nm": "성명", "sexdstn": "성별", "birth_ym": "출생연월",
    "ofcps": "직위", "rgist_exctv_at": "등기임원여부", "fte_at": "상근여부",
    "chrg_job": "담당업무", "main_career": "주요경력",
    "mxmm_shrholdr_relate": "최대주주관계",
    "hffc_pd": "재직기간", "tenure_end_on": "임기만료일",
    "relate": "관계", "stock_knd": "주식종류",
    "bsis_posesn_stock_co": "기초보유주식수", "bsis_posesn_stock_qota_rt": "기초보유비율",
    "trmend_posesn_stock_co": "기말보유주식수", "trmend_posesn_stock_qota_rt": "기말보유비율",
    "mxmm_shrholdr_nm": "최대주주명", "posesn_stock_co": "보유주식수",
    "qota_rt": "비율", "change_on": "변동일", "change_cause": "변동사유",
    "shrholdr_co": "주주수", "shrholdr_tot_co": "총주주수",
    "shrholdr_rate": "주주비율", "hold_stock_co": "보유주식수",
    "stock_tot_co": "총주식수", "hold_stock_rate": "보유주식비율",
    "fo_bbm": "부문", "rgllbr_co": "정규직수", "cnttk_co": "계약직수",
    "sm": "합계", "avrg_cnwk_sdytrn": "평균근속연수",
    "fyer_salary_totamt": "연간급여총액", "jan_salary_am": "월급여",
    # 보수
    "nmpr": "인원", "mendng_totamt": "보수총액",
    "jan_avrg_mendng_am": "평균보수", "mendng_totamt_ct_incls_mendng": "보수총액(보수포함)",
    "fscl_year": "회계연도",
    "stk_bsd_pd_mendng_totamt": "주식기준보상총액",
    "stk_opt_exrcsbl_qty": "행사가능 주식수",
    "stk_opt_unexrcsbl_qty": "미행사 주식수",
    "stk_opt_rmn_blce": "잔여 주식수",
    "othr_stk_bsd_cmpn_unpyd_qty": "기타주식보상 미지급수량",
    "othr_stk_bsd_cmpn_mkt_vl": "기타주식보상 시장가치",

    # === DS002 배당 ===
    "se": "구분", "thstrm": "당기", "frmtrm": "전기", "lwfr": "전전기",

    # === DS002 자기주식 ===
    "acqs_mth1": "취득방법1", "acqs_mth2": "취득방법2", "acqs_mth3": "취득방법3",
    "bsis_qy": "기초수량", "change_qy_acqs": "취득수량", "change_qy_dsps": "처분수량",
    "change_qy_incnr": "소각수량", "trmend_qy": "기말수량", "remndr": "잔여",

    # === DS002 타법인 출자 ===
    "inv_prm": "투자기업", "frst_acqs_de": "최초취득일자",
    "invstmnt_purps": "투자목적", "frst_acqs_amount": "최초취득금액",
    "bsis_blce_qy": "기초잔액수량", "bsis_blce_qota_rt": "기초잔액비율",
    "bsis_blce_acntbk_amount": "기초잔액장부가액",
    "incrs_dcrs_acqs_dsps_qy": "증감취득처분수량",
    "incrs_dcrs_acqs_dsps_amount": "증감취득처분금액",
    "incrs_dcrs_evl_lstmn": "증감평가손익",
    "trmend_blce_qy": "기말잔액수량", "trmend_blce_qota_rt": "기말잔액비율",
    "trmend_blce_acntbk_amount": "기말잔액장부가액",
    "recent_bsns_year_fnnr_sttus_tot_assets": "최근사업연도총자산",
    "recent_bsns_year_fnnr_sttus_thstrm_ntpf": "최근사업연도순이익",

    # === DS002 증감자·자본금 ===
    "isu_dcrs_de": "발행감소일자", "isu_dcrs_stle": "발행감소방식",
    "isu_dcrs_stock_knd": "발행감소주식종류", "isu_dcrs_qy": "발행감소수량",
    "isu_dcrs_mstvdv_fval_amount": "발행감소액면가",
    "isu_dcrs_mstvdv_amount": "발행감소금액",

    # === DS002 공모자금 ===
    "se_nm": "구분명", "tm": "회차", "pay_de": "납입일자",
    "pay_amount": "납입금액", "on_dclrt_cptal_use_plan": "공시당시자금사용계획",
    "real_cptal_use_sttus": "실제자금사용현황",
    "rs_cptal_use_plan_useprps": "증권신고서자금사용목적",
    "rs_cptal_use_plan_prcure_amount": "증권신고서조달금액",
    "real_cptal_use_dtls_cn": "실제자금사용내역",
    "real_cptal_use_dtls_amount": "실제자금사용금액",
    "dffrnc_occrrnc_resn": "차액발생사유",

    # === DS002 감사 ===
    "adtor": "감사인", "adt_opinion": "감사의견",
    "core_adt_matter": "핵심감사사항", "emphs_matter": "강조사항",
    "adt_reprt_spcmnt_matter": "감사보고서특기사항",
    "non_adt_servc_cnclsv_cont": "비감사용역계약내용",
    "non_adt_servc_cnclsv_amount": "비감사용역계약금액",

    # === DS002 사외이사 ===
    "isu_exctv_rgist_at": "등기임원여부", "isu_exctv_ofcps": "직위",
    "isu_main_shrholdr": "주요주주여부",

    # === DS002 단기주식 옵션 ===
    "sp_stock_lmp_cnt": "특정주식수", "sp_stock_lmp_irds_cnt": "특정주식증감수",
    "sp_stock_lmp_rate": "특정주식비율", "sp_stock_lmp_irds_rate": "특정주식증감비율",

    # === DS005 결정공시 공통 ===
    "aqpln_stk_ostk": "취득예정 보통주", "aqpln_stk_etc": "취득예정 기타주",
    "aqpln_prc_ostk": "취득예정 보통주가격", "aqpln_prc_etc": "취득예정 기타주가격",
    "aq_pp": "취득목적", "aq_mth": "취득방법",
    "cs_iv_bk": "위탁투자중개업자",
    "aq_wtn_div_ostk": "취득 전 보유 보통주", "aq_wtn_div_ostk_rt": "취득 전 보통주비율",
    "aq_wtn_div_estk": "취득 전 보유 기타주", "aq_wtn_div_estk_rt": "취득 전 기타주비율",
    "eaq_ostk": "초과취득 보통주", "eaq_estk": "초과취득 기타주",
    "aq_de_strt_de": "취득기간 시작일", "aq_de_end_de": "취득기간 종료일",
    "hd_de_strt_de": "보유기간 시작일", "hd_de_end_de": "보유기간 종료일",
    "d1_slodlm_aq_qy_ostk": "1일주문 보통주", "d1_slodlm_aq_qy_estk": "1일주문 기타주",
    # M&A 등
    "scrits_knd": "증권종류", "scrits_kndn": "증권종류명",
    "iscmp": "발행회사", "atn_iscmp_relate": "발행회사관계",
    "fl_ltrt_pamt": "이자총액", "iscmpc_tot_eqt": "발행회사자본총계",
    "iscmpc_tot_lblt": "발행회사부채총계",
    # 자기주식 처분 결정 (dp_*)
    "dppln_stk_ostk": "처분예정 보통주", "dppln_stk_estk": "처분예정 기타주",
    "dpstk_prc_ostk": "처분예정 보통주가격", "dpstk_prc_estk": "처분예정 기타주가격",
    "dppln_prc_ostk": "처분예정 보통주금액", "dppln_prc_estk": "처분예정 기타주금액",
    "dpprpd_bgd": "처분예정기간 시작일", "dpprpd_edd": "처분예정기간 종료일",
    "dp_pp": "처분목적", "dp_m_otc": "처분방법(장외)", "dp_m_etc": "처분방법(기타)",
    "d1_prodlm_ostk": "1일주문 보통주", "d1_prodlm_estk": "1일주문 기타주",
    # 취득 신탁/예정 (aq_*)
    "aqexpd_bgd": "취득예정기간 시작일", "aqexpd_edd": "취득예정기간 종료일",
    "aqpln_stk_estk": "취득예정 기타주", "aqpln_prc_estk": "취득예정 기타주금액",
    "eaq_ostk_rt": "초과취득 보통주비율", "eaq_estk_rt": "초과취득 기타주비율",
    "d1_slodlm_aq_qy_ostk": "1일주문 보통주", "d1_slodlm_aq_qy_estk": "1일주문 기타주",
    # 미상환 채권·증권 (yy1~yy5 잔존만기 구간)
    "remndr_exprtn1": "잔존만기 1년이하", "remndr_exprtn2": "잔존만기 1~2년",
    "yy1_below": "1년이하", "yy1_excess_yy2_below": "1~2년",
    "yy2_excess_yy3_below": "2~3년", "yy3_excess_yy4_below": "3~4년",
    "yy4_excess_yy5_below": "4~5년", "yy5_excess_yy10_below": "5~10년",
    "facvalu_totamt": "권면총액", "isu_de": "발행일",
    "isu_mth_nm": "발행방법", "scrits_knd_nm": "증권종류명",
    "repy_at": "상환여부", "evl_grad_instt": "신용평가기관",
    "isu_cmpny": "발행회사", "mngt_cmpny": "관리회사",
    # 감사·비감사 용역
    "cntrct_cncls_de": "계약체결일", "servc_cn": "용역내용",
    "servc_exc_pd": "용역기간", "servc_mendng": "용역대가",
    "adt_cntrct_dtls_mendng": "감사계약 대가", "adt_cntrct_dtls_time": "감사계약 시간",
    "real_exc_dtls_mendng": "실제수행 대가", "real_exc_dtls_time": "실제수행 시간",
    # 보수 유형별
    "pymnt_totamt": "지급총액", "psn1_avrg_pymntamt": "1인당 평균지급액",
    "gmtsck_confm_amount": "주총승인 금액",
    # 회사분할·신주발행 등
    "od_a_at_t": "사외이사 참석", "od_a_at_b": "사외이사 불참",
    "adt_a_atn": "감사위원 참석", "gmtsck_prd": "주주총회 예정일",
    "popt_ctr_atn": "풋백옵션 약정여부", "ex_sm_r": "분할방식",
    "ffdtl_tast": "총자산", "rs_sm_atn": "주식매수청구권 여부",
    "cdobprpd_bgd": "채권자이의제출 시작일", "cdobprpd_edd": "채권자이의제출 종료일",
    "mtrpt_cptal_use_plan_useprps": "증권신고서 자금사용목적",
    "mtrpt_cptal_use_plan_prcure_amount": "증권신고서 조달금액",
    # 계약 (ctr_*)
    "ctr_prc": "계약금액", "ctr_pd_bgd": "계약기간 시작일",
    "ctr_pd_edd": "계약기간 종료일", "ctr_pp": "계약목적",
    "ctr_cns_int": "계약체결 기관", "ctr_cns_prd": "계약체결 예정일",
    "ctr_prc_bfcc": "변경전 계약금액", "ctr_pd_bfcc_bgd": "변경전 계약 시작일",
    "ctr_pd_bfcc_edd": "변경전 계약 종료일", "cc_int": "변경 사유", "cc_prd": "변경 일자",
    "tp_rm_atcc": "기타 비고",
}


def translate_field(field: str) -> str:
    """영문 필드명 → 한국어. 매핑 없으면 원본."""
    return FIELD_KO.get(field, field)


def translate_kv_pairs(item: dict, exclude: set | None = None) -> list[str]:
    """item dict → ["한글필드명=값", ...] 리스트. 빈값·제외 필드 스킵."""
    exclude = exclude or set()
    out = []
    for k, v in item.items():
        if k in exclude: continue
        if v is None or v == "" or v == "-": continue
        ko = translate_field(k)
        out.append(f"{ko}={v}")
    return out
