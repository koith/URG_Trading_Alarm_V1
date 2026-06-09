"""
URG Box Trading Assistant v1.3
================================
변경: data_logger 연동 (매 실행마다 price_snapshot 저장)

실행: py urg_alert.py
"""
import os
from datetime import datetime, timedelta

import requests
import yfinance as yf

from common import (
    PORTFOLIO_PATH, SETTINGS_PATH, STATE_PATH,
    load_dotenv, read_json, write_json, now_iso,
    get_db_connection, get_placeholder, is_postgres,
)
from trailing import (
    check_trailing, check_reentry,
    activate_trailing, load_trail
)
from data_logger import init_tables, save_snapshot


def init_db():
    pk = "SERIAL PRIMARY KEY" if is_postgres() else "INTEGER PRIMARY KEY AUTOINCREMENT"
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS alert_log (
            id {pk},
            timestamp TEXT,
            ticker TEXT,
            price REAL,
            action TEXT,
            label TEXT,
            qty INTEGER,
            message TEXT
        )
    """)
    conn.commit()
    conn.close()
    # data_logger 테이블도 초기화
    init_tables()


def save_log(ticker, price, action, label, qty, message):
    p = get_placeholder()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        f"INSERT INTO alert_log (timestamp,ticker,price,action,label,qty,message) VALUES ({p},{p},{p},{p},{p},{p},{p})",
        (now_iso(), ticker, price, action, label, qty, message)
    )
    conn.commit()
    conn.close()


def get_price(ticker):
    yf_ticker = yf.Ticker(ticker)
    data = yf_ticker.history(period="1d", interval="1m", prepost=True)
    if data.empty:
        data = yf_ticker.history(period="5d", interval="1d", prepost=True)
    if data.empty:
        raise RuntimeError(f"{ticker} 가격 조회 실패")
    return round(float(data["Close"].iloc[-1]), 4)


def send_telegram(message):
    load_dotenv()
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("텔레그램 설정 없음: .env 확인")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=10)
    if not r.ok:
        print(f"텔레그램 오류: {r.status_code}")
    return r.ok


def load_state():
    return read_json(STATE_PATH, default={"last_alerts": {}})


def save_state(state):
    write_json(STATE_PATH, state)


def is_in_cooldown(action, label, cooldown_hours):
    state = load_state()
    key = f"{action}:{label}"
    raw = state.get("last_alerts", {}).get(key)
    if not raw:
        return False
    return datetime.now() - datetime.fromisoformat(raw) < timedelta(hours=cooldown_hours)


def mark_alert(action, label):
    state = load_state()
    state.setdefault("last_alerts", {})[f"{action}:{label}"] = now_iso()
    save_state(state)


def unrealized_pnl(price, portfolio):
    shares = int(portfolio.get("shares", 0))
    avg = float(portfolio.get("avg_cost", 0.0))
    if shares <= 0 or avg <= 0:
        return 0.0, 0.0
    return (price - avg) * shares, (price / avg - 1) * 100


def get_daily_counts():
    """오늘 날짜 기준 alert_log에서 매수/매도 신호 횟수 반환 (BUY+REENTRY, SELL+TRAIL_STOP)"""
    today = datetime.now().strftime("%Y-%m-%d")
    p = get_placeholder()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        f"SELECT action, COUNT(*) FROM alert_log WHERE timestamp LIKE {p} AND action != 'TEST' GROUP BY action",
        (f"{today}%",)
    )
    raw = {action: cnt for action, cnt in c.fetchall()}
    conn.close()
    buy_count  = raw.get("BUY", 0) + raw.get("REENTRY", 0)
    sell_count = raw.get("SELL", 0) + raw.get("TRAIL_STOP", 0)
    return buy_count, sell_count


def dynamic_sell_pct(pnl_pct: float, base_pct: float) -> float:
    bonus = 0.0
    if pnl_pct >= 45:
        bonus = 0.20
    elif pnl_pct >= 35:
        bonus = 0.10
    return min(base_pct + bonus, 1.0)


def evaluate(price, settings, portfolio):
    risk      = settings.get("risk_rules", {})
    cooldown  = int(risk.get("alert_cooldown_hours", 24))
    max_buy   = int(risk.get("max_daily_buy", 99))
    max_sell  = int(risk.get("max_daily_sell", 99))
    shares    = int(portfolio.get("shares", 0))
    avg_cost  = float(portfolio.get("avg_cost", 0.0))
    cash      = float(portfolio.get("cash_usd", 0.0))
    budget    = float(portfolio.get("total_budget_usd", 0.0))
    ticker    = settings["ticker"]
    pnl, pnl_pct = unrealized_pnl(price, portfolio)

    daily_buy, daily_sell = get_daily_counts()

    # 1순위: 트레일링 스탑 (매도 계열)
    trail = check_trailing(price, shares)
    if trail:
        action, qty, msg = trail
        if daily_sell >= max_sell:
            print(f"[리스크] 일일 매도 한도 도달 ({daily_sell}/{max_sell}) → {action} 차단")
        elif not is_in_cooldown(action, "트레일링스탑", cooldown):
            return action, "트레일링스탑", qty, msg

    # 2순위: 매도 구간 (매도 계열)
    if shares > 0 and avg_cost > 0:
        sell_candidates = []
        for level in settings["sell_levels"]:
            min_profit_price = avg_cost * (1 + float(level.get("min_profit_pct", 0.0)))
            if price >= level["price"] and price >= min_profit_price:
                if not is_in_cooldown("SELL", level["label"], cooldown):
                    sell_candidates.append(level)

        if sell_candidates:
            if daily_sell >= max_sell:
                print(f"[리스크] 일일 매도 한도 도달 ({daily_sell}/{max_sell}) → SELL 차단")
            else:
                level   = sell_candidates[-1]
                adj_pct = dynamic_sell_pct(pnl_pct, float(level["hold_pct"]))
                qty     = min(max(1, int(shares * adj_pct)), shares)
                msg     = make_sell_msg(ticker, price, level, qty, portfolio, pnl, pnl_pct, adj_pct)
                return "SELL", level["label"], qty, msg

    # 3순위: 재진입 (매수 계열)
    reentry = check_reentry(price)
    if reentry:
        action, qty, msg = reentry
        if daily_buy >= max_buy:
            print(f"[리스크] 일일 매수 한도 도달 ({daily_buy}/{max_buy}) → {action} 차단")
        elif not is_in_cooldown(action, "재진입", cooldown):
            return action, "재진입", qty, msg

    # 4순위: 매수 (매수 계열)
    if daily_buy >= max_buy:
        print(f"[리스크] 일일 매수 한도 도달 ({daily_buy}/{max_buy}) → 매수 신호 차단")
        return None

    for level in settings["buy_levels"]:
        if price <= level["price"] and not is_in_cooldown("BUY", level["label"], cooldown):
            basis = cash if cash > 0 else budget
            qty   = int(basis * float(level["budget_pct"]) / price)
            if qty > 0:
                msg = make_buy_msg(ticker, price, level, qty, portfolio)
                return "BUY", level["label"], qty, msg

    return None


def make_buy_msg(ticker, price, level, qty, p):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f"🟢 <b>[{ticker} 매수 신호]</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {now}\n"
        f"💰 현재가: <b>${price:.4f}</b>\n"
        f"📌 신호: <b>{level['label']}</b>  (기준 ${level['price']:.4f})\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📋 현재 포지션\n"
        f"  보유 {p.get('shares', 0)}주  |  평단 ${float(p.get('avg_cost', 0)):.4f}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✅ 매수 가이드\n"
        f"  예산 {int(level['budget_pct']*100)}%  →  <b>{qty}주</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ 지정가 주문만  /  추격 금지\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📲 <b>체결 후 실행:</b>\n"
        f"<code>py portfolio.py buy {qty} {price:.4f}</code>"
    )


def make_sell_msg(ticker, price, level, qty, p, pnl, pnl_pct, adj_pct):
    now       = datetime.now().strftime("%Y-%m-%d %H:%M")
    base_pct  = float(level["hold_pct"]) * 100
    bonus     = adj_pct * 100 - base_pct
    bonus_str = f"  (+{bonus:.0f}% 수익 보너스)" if bonus > 0 else ""
    return (
        f"🔴 <b>[{ticker} 매도 신호]</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {now}\n"
        f"💰 현재가: <b>${price:.4f}</b>\n"
        f"📌 신호: <b>{level['label']}</b>  (기준 ${level['price']:.4f})\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📦 현재 포지션\n"
        f"  보유 {int(p.get('shares', 0))}주  |  평단 ${float(p.get('avg_cost', 0)):.4f}\n"
        f"  미실현: <b>${pnl:,.2f}</b>  ({pnl_pct:+.2f}%)\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✅ 매도 가이드\n"
        f"  {adj_pct*100:.0f}% 매도{bonus_str}  →  <b>{qty}주</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ 지정가 주문만  /  추격 금지\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📲 <b>체결 후 실행:</b>\n"
        f"<code>py portfolio.py sell {qty} {price:.4f}</code>"
    )


def main(market_segment="regular"):
    """
    market_segment: 'regular' | 'premarket'
      - 'regular'   : 정상 평가 → 조건 충족 시 텔레그램 + alert_log 저장
      - 'premarket' : allow_alerts_in_premarket=false 이면 snapshot만 저장, 알림 차단
    """
    init_db()
    settings  = read_json(SETTINGS_PATH)
    portfolio = read_json(PORTFOLIO_PATH)
    ticker    = settings["ticker"]

    print(f"[{datetime.now().strftime('%H:%M:%S')}] {ticker} 가격 조회 중...")
    try:
        price = get_price(ticker)
    except Exception as e:
        print(f"가격 조회 오류: {e}")
        return

    print(f"현재가: ${price:.4f}")
    if settings.get("test_mode", False):
        save_log(ticker, price, "TEST", "MANUAL", 1, "manual test")

    # ── 스냅샷 저장 (매 실행마다) ──────────────────────────
    try:
        save_snapshot(price)
    except Exception as e:
        print(f"[DataLogger] 스냅샷 저장 오류: {e}")

    # ── 프리마켓 알림 차단 ─────────────────────────────────────
    market_rules = settings.get("market_rules", {})
    allow_alerts_in_premarket = market_rules.get("allow_alerts_in_premarket", False)
    if market_segment == "premarket" and not allow_alerts_in_premarket:
        print(f"[PREMARKET] 알림 차단: snapshot만 저장 완료 (가격: ${price:.4f})")
        return

    shares = int(portfolio.get("shares", 0))

    # 보유 중이면 고점 갱신
    if shares > 0:
        activate_trailing(price)

    pnl, pnl_pct = unrealized_pnl(price, portfolio)
    trail_state   = load_trail()
    high          = trail_state.get("high_price", 0)
    print(f"보유: {shares}주 / 평단 ${portfolio.get('avg_cost',0):.4f} / 손익 ${pnl:,.2f} ({pnl_pct:+.2f}%) / 고점 ${high:.4f}")

    signal = evaluate(price, settings, portfolio)
    if not signal:
        print("→ 신호 없음")
        return

    action, label, qty, msg = signal
    print(f"→ {action} [{label}] {qty}주")
    if send_telegram(msg):
        print("텔레그램 전송 완료 ✓")
        save_log(ticker, price, action, label, qty, msg)
        mark_alert(action, label)
    else:
        print("텔레그램 전송 실패 ✗")


if __name__ == "__main__":
    main()
