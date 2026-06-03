"""
Data Logger - 실시간 데이터 누적 저장 레이어
=============================================
역할: Data Layer (logging)

매 5분 체크 시마다:
- 가격 스냅샷 저장
- equity 계산 + 저장
- 포지션 상태 저장

저장소: urg_log.db (기존 DB 확장)

직접 실행 불필요 — urg_alert.py에서 import해서 씀
"""
import sqlite3
from datetime import datetime
from common import LOG_DB_PATH, PORTFOLIO_PATH, read_json, now_iso


def init_tables():
    """DB 테이블 초기화 (없으면 생성)"""
    conn = sqlite3.connect(LOG_DB_PATH)
    c = conn.cursor()

    # 기존 alert_log 유지하고 새 테이블 추가
    c.execute("""
        CREATE TABLE IF NOT EXISTS price_snapshot (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            price     REAL,
            shares    INTEGER,
            avg_cost  REAL,
            cash      REAL,
            equity    REAL,
            unrealized_pnl REAL,
            unrealized_pnl_pct REAL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS trade_event (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            action    TEXT,
            label     TEXT,
            price     REAL,
            qty       INTEGER,
            avg_cost  REAL,
            cash_after REAL,
            shares_after INTEGER,
            equity_after REAL,
            realized_pnl REAL,
            reason    TEXT
        )
    """)

    conn.commit()
    conn.close()


def save_snapshot(price: float):
    """
    5분마다 호출 — 가격 + 포지션 + equity 저장
    """
    portfolio = read_json(PORTFOLIO_PATH, default={})
    shares   = int(portfolio.get("shares", 0))
    avg_cost = float(portfolio.get("avg_cost", 0.0))
    cash     = float(portfolio.get("cash_usd", 0.0))

    # equity = 현금 + 보유주식 평가금액
    position_value = shares * price
    equity = cash + position_value

    # 미실현 손익
    if shares > 0 and avg_cost > 0:
        unrealized_pnl     = (price - avg_cost) * shares
        unrealized_pnl_pct = (price / avg_cost - 1) * 100
    else:
        unrealized_pnl     = 0.0
        unrealized_pnl_pct = 0.0

    conn = sqlite3.connect(LOG_DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO price_snapshot
        (timestamp, price, shares, avg_cost, cash, equity, unrealized_pnl, unrealized_pnl_pct)
        VALUES (?,?,?,?,?,?,?,?)
    """, (
        now_iso(), price, shares, avg_cost,
        round(cash, 2), round(equity, 2),
        round(unrealized_pnl, 2), round(unrealized_pnl_pct, 2)
    ))
    conn.commit()
    conn.close()


def save_trade_event(action, label, price, qty, avg_cost,
                     cash_after, shares_after, realized_pnl, reason=""):
    """
    매수/매도 실행 시 호출 — 거래 이벤트 저장
    """
    equity_after = cash_after + shares_after * price

    conn = sqlite3.connect(LOG_DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO trade_event
        (timestamp, action, label, price, qty, avg_cost,
         cash_after, shares_after, equity_after, realized_pnl, reason)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        now_iso(), action, label,
        round(price, 4), qty, round(avg_cost, 4),
        round(cash_after, 2), shares_after,
        round(equity_after, 2), round(realized_pnl, 4), reason
    ))
    conn.commit()
    conn.close()


def get_equity_curve(limit=500):
    """
    최근 N개 equity snapshot 반환
    risk_layer 등에서 사용
    """
    conn = sqlite3.connect(LOG_DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT timestamp, price, equity, unrealized_pnl_pct
        FROM price_snapshot
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()

    # 오래된 것부터 정렬
    rows.reverse()
    return [
        {
            "timestamp":           r[0],
            "price":               r[1],
            "equity":              r[2],
            "unrealized_pnl_pct":  r[3]
        }
        for r in rows
    ]


def get_trade_events(limit=100):
    """최근 거래 이벤트 반환"""
    conn = sqlite3.connect(LOG_DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT timestamp, action, label, price, qty,
               avg_cost, equity_after, realized_pnl, reason
        FROM trade_event
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    rows.reverse()
    return [
        {
            "timestamp":    r[0],
            "action":       r[1],
            "label":        r[2],
            "price":        r[3],
            "qty":          r[4],
            "avg_cost":     r[5],
            "equity_after": r[6],
            "realized_pnl": r[7],
            "reason":       r[8]
        }
        for r in rows
    ]


# CLI: 현재 누적 데이터 확인
if __name__ == "__main__":
    init_tables()
    curve = get_equity_curve(10)
    events = get_trade_events(10)

    print("=" * 50)
    print("최근 Equity Snapshots (최대 10개)")
    print("=" * 50)
    for r in curve:
        print(f"  {r['timestamp']} | 가격 ${r['price']:.4f} | Equity ${r['equity']:.2f} | 손익 {r['unrealized_pnl_pct']:+.2f}%")

    print()
    print("=" * 50)
    print("최근 Trade Events (최대 10개)")
    print("=" * 50)
    for r in events:
        print(f"  {r['timestamp']} | {r['action']} {r['label']} | {r['qty']}주 @ ${r['price']:.4f} | equity ${r['equity_after']:.2f}")
