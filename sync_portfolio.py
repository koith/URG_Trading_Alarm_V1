"""
KIS 계좌 → portfolio.json 자동 동기화 v1.1
============================================
- 한투 계좌에서 URG 보유량/평단가 자동 조회
- portfolio.json 자동 업데이트
- 수동 입력 불필요

실행: py sync_portfolio.py
"""
import os
import requests
from datetime import datetime, timedelta
from common import PORTFOLIO_PATH, BASE_DIR, read_json, write_json, now_iso, load_dotenv

TARGET     = "URG"
BASE_URL   = "https://openapi.koreainvestment.com:9443"
TOKEN_PATH = BASE_DIR / ".kis_token.json"


# ============================================================
# 토큰 관리 (하루 1회 발급 원칙)
# ============================================================
def get_token(app_key, app_secret):
    if TOKEN_PATH.exists():
        cached = read_json(TOKEN_PATH, default={})
        expires = cached.get("expires_at", "")
        if expires and datetime.fromisoformat(expires) > datetime.now():
            print("[KIS] 캐시 토큰 사용")
            return cached["access_token"]

    print("[KIS] 토큰 발급 중...")
    res = requests.post(
        f"{BASE_URL}/oauth2/tokenP",
        json={
            "grant_type": "client_credentials",
            "appkey": app_key,
            "appsecret": app_secret
        },
        headers={"content-type": "application/json"},
        timeout=10
    )
    data = res.json()
    if "access_token" not in data:
        raise RuntimeError(f"토큰 발급 실패: {data}")

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
def get_overseas_balance(token, app_key, app_secret, account_no, account_cd):
    """TR: JTTT3012R (해외주식 잔고)"""
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "JTTT3012R",
        "custtype": "P"
    }
    params = {
        "CANO": account_no,
        "ACNT_PRDT_CD": account_cd,
        "OVRS_EXCG_CD": "NASD",
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
            qty      = int(item.get("ovrs_cblc_qty", 0))
            avg      = float(item.get("pchs_avg_pric", 0.0))
            eval_amt = float(item.get("ovrs_stck_evlu_amt", 0.0))
            return qty, avg, eval_amt
    return 0, 0.0, 0.0


# ============================================================
# portfolio.json 업데이트
# ============================================================
def update_portfolio(qty, avg, eval_amt):
    old = read_json(PORTFOLIO_PATH, default={})
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

    load_dotenv()
    app_key    = os.environ.get("KIS_APP_KEY", "")
    app_secret = os.environ.get("KIS_APP_SECRET", "")
    account_no = os.environ.get("KIS_ACCOUNT_NO", "")
    account_cd = os.environ.get("KIS_ACCOUNT_CODE", "01")

    if not app_key or not account_no:
        print("오류: .env에 KIS_APP_KEY / KIS_ACCOUNT_NO 확인")
        return

    token = get_token(app_key, app_secret)
    data  = get_overseas_balance(token, app_key, app_secret, account_no, account_cd)

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
