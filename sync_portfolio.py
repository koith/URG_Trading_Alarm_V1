"""
KIS 계좌 → portfolio.json 자동 동기화 v1.0
============================================
- 한투 계좌에서 URG 보유량/평단가 자동 조회
- portfolio.json 자동 업데이트
- 수동 입력 불필요

실행: py sync_portfolio.py
"""
import os
import requests
from datetime import datetime
from pathlib import Path
from common import PORTFOLIO_PATH, BASE_DIR, read_json, write_json, now_iso, load_dotenv

load_dotenv()

APP_KEY     = os.environ.get("KIS_APP_KEY", "")
APP_SECRET  = os.environ.get("KIS_APP_SECRET", "")
ACCOUNT_NO  = os.environ.get("KIS_ACCOUNT_NO", "")   # 앞 8자리
ACCOUNT_CD  = os.environ.get("KIS_ACCOUNT_CODE", "01")  # 뒤 2자리
TARGET      = "URG"  # 조회할 종목

BASE_URL   = "https://openapi.koreainvestment.com:9443"
TOKEN_PATH = BASE_DIR / ".kis_token.json"

# ============================================================
# 토큰 관리 (하루 1회 발급 원칙)
# ============================================================
def get_token():
    # 캐시된 토큰 확인
    if TOKEN_PATH.exists():
        cached = read_json(TOKEN_PATH, default={})
        expires = cached.get("expires_at", "")
        if expires and datetime.fromisoformat(expires) > datetime.now():
            print("[KIS] 캐시 토큰 사용")
            return cached["access_token"]

    # 새 토큰 발급
    print("[KIS] 토큰 발급 중...")
    res = requests.post(
        f"{BASE_URL}/oauth2/tokenP",
        json={
            "grant_type": "client_credentials",
            "appkey": APP_KEY,
            "appsecret": APP_SECRET
        },
        headers={"content-type": "application/json"},
        timeout=10
    )
    data = res.json()
    if "access_token" not in data:
        raise RuntimeError(f"토큰 발급 실패: {data}")

    # 만료 23시간 후로 설정 (24시간 유효, 여유 1시간)
    from datetime import timedelta
    expires_at = (datetime.now() + timedelta(hours=23)).isoformat()
    write_json(TOKEN_PATH, {
        "access_token": data["access_token"],
        "expires_at": expires_at
    })
    print("[KIS] 토큰 발급 완료")
    return data["access_token"]


# ============================================================
# 해외주식 잔고 조회
# ============================================================
def get_overseas_balance(token):
    """
    해외주식 잔고 조회
    TR: JTTT3012R (해외주식 잔고)
    """
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "JTTT3012R",
        "custtype": "P"
    }
    params = {
        "CANO": ACCOUNT_NO,
        "ACNT_PRDT_CD": ACCOUNT_CD,
        "OVRS_EXCG_CD": "NASD",   # 나스닥 (URG 상장)
        "TR_CRCY_CD": "USD",
        "CTX_AREA_FK200": "",
        "CTX_AREA_NK200": ""
    }
    res = requests.get(
        f"{BASE_URL}/uapi/overseas-stock/v1/trading/inquire-balance",
        headers=headers,
        params=params,
        timeout=10
    )
    return res.json()


# ============================================================
# URG 포지션 추출
# ============================================================
def extract_urg(data):
    output = data.get("output1", [])
    for item in output:
        symb = item.get("ovrs_pdno", "").strip().upper()
        if symb == TARGET:
            qty  = int(item.get("ovrs_cblc_qty", 0))
            avg  = float(item.get("pchs_avg_pric", 0.0))
            eval_amt = float(item.get("ovrs_stck_evlu_amt", 0.0))
            return qty, avg, eval_amt
    return 0, 0.0, 0.0


# ============================================================
# portfolio.json 업데이트
# ============================================================
def update_portfolio(qty, avg, eval_amt):
    old = read_json(PORTFOLIO_PATH, default={})

    # 수동 입력 필드는 유지 (예산, 현금, 실현손익, 거래기록)
    old.update({
        "ticker": TARGET,
        "shares": qty,
        "avg_cost": round(avg, 6),
        "market_value_usd": round(eval_amt, 2),
        "synced_at": now_iso(),
        "sync_source": "KIS_API"
    })
    write_json(PORTFOLIO_PATH, old)


# ============================================================
# 메인
# ============================================================
def main():
    print("=" * 40)
    print("KIS 포트폴리오 동기화")
    print("=" * 40)

    if not APP_KEY or not ACCOUNT_NO:
        print("오류: .env에 KIS_APP_KEY / KIS_ACCOUNT_NO 확인")
        return

    token = get_token()
    data  = get_overseas_balance(token)

    rt_cd = data.get("rt_cd", "")
    msg   = data.get("msg1", "")

    if rt_cd != "0":
        print(f"API 오류: {rt_cd} / {msg}")
        print("상세:", data)
        return

    qty, avg, eval_amt = extract_urg(data)

    print(f"URG 보유: {qty}주 / 평단 ${avg:.4f} / 평가금액 ${eval_amt:.2f}")

    if qty == 0:
        print("→ 현재 한투 계좌에 URG 없음 (매수 후 다시 실행하세요)")
    else:
        update_portfolio(qty, avg, eval_amt)
        print("→ portfolio.json 업데이트 완료")

    print("=" * 40)


if __name__ == "__main__":
    main()
