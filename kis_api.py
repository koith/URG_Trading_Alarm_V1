import os
import time
import requests
from dotenv import load_dotenv

# =========================================================
# ENV
# =========================================================
load_dotenv()

APP_KEY = os.getenv("KIS_APP_KEY")
APP_SECRET = os.getenv("KIS_APP_SECRET")

BASE_URL = "https://openapi.koreainvestment.com:9443"

ACCESS_TOKEN = None
TOKEN_TIME = 0

TOKEN_FILE = "token_cache.txt"
TOKEN_TTL = 60 * 60 * 23  # 23시간


# =========================================================
# TOKEN LOAD FROM FILE
# =========================================================
def load_token_from_file():
    global ACCESS_TOKEN, TOKEN_TIME

    if not os.path.exists(TOKEN_FILE):
        return None

    try:
        with open(TOKEN_FILE, "r") as f:
            token, ts = f.read().split("|")

        if time.time() - float(ts) < TOKEN_TTL:
            ACCESS_TOKEN = token
            TOKEN_TIME = float(ts)
            print("[KIS] 토큰 파일 캐시 사용")
            return token
    except:
        return None

    return None


# =========================================================
# SAVE TOKEN
# =========================================================
def save_token(token):
    with open(TOKEN_FILE, "w") as f:
        f.write(f"{token}|{time.time()}")


# =========================================================
# TOKEN GET (절대 1분 제한 안 걸리게 구조 분리)
# =========================================================
def get_access_token(force=False):
    global ACCESS_TOKEN, TOKEN_TIME

    # 1. 파일 캐시 먼저
    if not force:
        cached = load_token_from_file()
        if cached:
            return cached

    # 2. API 호출 (최소화)
    url = f"{BASE_URL}/oauth2/tokenP"

    headers = {"content-type": "application/json"}

    body = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    }

    res = requests.post(url, json=body, headers=headers)
    data = res.json()

    if "access_token" not in data:
        raise Exception(f"Token Error: {data}")

    ACCESS_TOKEN = data["access_token"]
    TOKEN_TIME = time.time()

    save_token(ACCESS_TOKEN)

    print("[KIS] Access Token 발급 완료 (파일 저장)")
    return ACCESS_TOKEN


# =========================================================
# HEADERS
# =========================================================
def get_headers():
    if ACCESS_TOKEN is None:
        get_access_token()

    return {
        "content-type": "application/json",
        "authorization": f"Bearer {ACCESS_TOKEN}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    }


# =========================================================
# PRICE
# =========================================================
def get_price(exchange_code="NAS", symbol="AAPL"):
    url = f"{BASE_URL}/uapi/overseas-price/v1/quotations/price"

    headers = get_headers()
    headers["tr_id"] = "HHDFS00000300"

    params = {
        "AUTH": "",
        "EXCD": exchange_code,
        "SYMB": symbol
    }

    res = requests.get(url, headers=headers, params=params)
    data = res.json()

    try:
        output = data.get("output", {})

        # ✔ 핵심 수정
        price = output.get("last") or output.get("stck_prpr")

        if not price:
            print("[KIS EMPTY]", data)
            return None

        print(f"[KIS] PRICE OK → {symbol}: {price}")
        return float(price)

    except Exception:
        print("[KIS ERROR]", data)
        return None


# =========================================================
# TEST
# =========================================================
if __name__ == "__main__":
    get_access_token()
    print("TOKEN OK")
    print(get_price())