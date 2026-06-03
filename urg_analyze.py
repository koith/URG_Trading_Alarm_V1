"""
URG 전략 분석기 v2.0
=====================
레이어: Backtest / Analysis Layer

기존 대비 추가:
- 거래 이유(reason) 기록
- 보유 기간 계산
- Equity curve (시간별 자산 변화)
- 성과 지표: 샤프비율 / MDD / 승률 / 평균 보유기간
- CSV 저장 (trade_log.csv, equity_curve.csv)
- 성과 리포트 출력

실행: py urg_analyze.py
"""
import csv
from datetime import datetime
from pathlib import Path

import numpy as np
import yfinance as yf

from common import SETTINGS_PATH, BASE_DIR, write_json, read_json

# ============================================================
# 설정
# ============================================================
TICKER          = "URG"
PERIOD          = "5y"
INITIAL_BUDGET  = 1000.0
COMMISSION_RATE = 0.001
SLIPPAGE_RATE   = 0.002

BUY_PERCENTILES  = [20, 10, 5]
SELL_PERCENTILES = [75, 88, 95]
BUY_BUDGET_PCT   = [0.25, 0.35, 0.40]
SELL_HOLD_PCT    = [0.30, 0.40, 1.00]
MIN_PROFIT_PCT   = [0.08, 0.15, 0.25]

TRADE_LOG_PATH  = BASE_DIR / "trade_log.csv"
EQUITY_LOG_PATH = BASE_DIR / "equity_curve.csv"

# ============================================================
# 1. 데이터 로드
# ============================================================
def load_data():
    print(f"[1/5] {TICKER} {PERIOD} 데이터 로드")
    df = yf.Ticker(TICKER).history(period=PERIOD)
    if df.empty:
        raise RuntimeError("데이터 로드 실패")
    print(f"      {len(df)}일: {df.index[0].date()} ~ {df.index[-1].date()}")
    return df

# ============================================================
# 2. 구간 도출
# ============================================================
def derive_levels(df):
    print("[2/5] 분위수 기반 구간 계산")
    closes = df["Close"].dropna().values

    buy_levels, sell_levels = [], []

    for i, pct in enumerate(BUY_PERCENTILES):
        buy_levels.append({
            "label": f"{i+1}차 매수",
            "price": round(float(np.percentile(closes, pct)), 4),
            "budget_pct": BUY_BUDGET_PCT[i],
            "percentile": pct
        })

    for i, pct in enumerate(SELL_PERCENTILES):
        sell_levels.append({
            "label": f"{i+1}차 매도",
            "price": round(float(np.percentile(closes, pct)), 4),
            "hold_pct": SELL_HOLD_PCT[i],
            "min_profit_pct": MIN_PROFIT_PCT[i],
            "percentile": pct
        })

    print(f"      가격범위: ${closes.min():.4f} ~ ${closes.max():.4f}")
    for x in buy_levels:
        print(f"      {x['label']}: ${x['price']} (하위 {x['percentile']}%)")
    for x in sell_levels:
        print(f"      {x['label']}: ${x['price']} (상위 {100-x['percentile']}%, 최소수익 +{x['min_profit_pct']*100:.0f}%)")

    return buy_levels, sell_levels

# ============================================================
# 3. 백테스트 (거래 이유 + 보유 기간 포함)
# ============================================================
def backtest(df, buy_levels, sell_levels):
    print("[3/5] 백테스트 실행")

    cash      = INITIAL_BUDGET
    shares    = 0
    avg_cost  = 0.0
    realized  = 0.0
    trades    = []
    equity_curve = []   # (date, equity, shares, cash)
    bought    = set()
    sold      = set()

    # 매수 날짜 추적 (보유 기간 계산용)
    buy_date  = None

    for date, row in df.iterrows():
        raw_price = float(row["Close"])
        date_str  = str(date.date())

        # ── 매도 판정 ──────────────────────────────────────
        if shares > 0:
            for level in sell_levels:
                if level["label"] in sold:
                    continue
                min_price = avg_cost * (1 + level["min_profit_pct"])
                if raw_price >= level["price"] and raw_price >= min_price:
                    exec_price  = raw_price * (1 - SLIPPAGE_RATE)
                    qty         = min(shares, max(1, int(shares * level["hold_pct"])))
                    gross       = qty * exec_price
                    fee         = gross * COMMISSION_RATE
                    pnl_trade   = (exec_price - avg_cost) * qty - fee
                    cash        += gross - fee
                    realized    += pnl_trade
                    shares      -= qty
                    sold.add(level["label"])

                    # 보유 기간
                    hold_days = (date.date() - buy_date).days if buy_date else 0

                    trades.append({
                        "date":      date_str,
                        "action":    "SELL",
                        "label":     level["label"],
                        "reason":    f"가격(${raw_price:.4f}) >= 매도기준(${level['price']}) AND 수익률 >= {level['min_profit_pct']*100:.0f}%",
                        "price":     round(exec_price, 4),
                        "qty":       qty,
                        "avg_cost":  round(avg_cost, 4),
                        "pnl":       round(pnl_trade, 2),
                        "hold_days": hold_days,
                        "cash":      round(cash, 2),
                        "shares":    shares,
                        "realized_pnl_cumul": round(realized, 2)
                    })

                    if shares == 0:
                        avg_cost = 0.0
                        buy_date = None
                    break

        # 전량 매도 후 사이클 리셋
        if shares == 0 and sold:
            bought = set()
            sold   = set()

        # ── 매수 판정 ──────────────────────────────────────
        for level in buy_levels:
            if level["label"] in bought:
                continue
            if raw_price <= level["price"]:
                exec_price   = raw_price * (1 + SLIPPAGE_RATE)
                target_cash  = INITIAL_BUDGET * level["budget_pct"]
                qty          = int(min(cash, target_cash) / exec_price)
                if qty <= 0:
                    continue
                cost         = qty * exec_price
                fee          = cost * COMMISSION_RATE
                total        = cost + fee
                old_value    = shares * avg_cost
                cash        -= total
                shares      += qty
                avg_cost     = (old_value + total) / shares
                bought.add(level["label"])

                if buy_date is None:
                    buy_date = date.date()

                trades.append({
                    "date":      date_str,
                    "action":    "BUY",
                    "label":     level["label"],
                    "reason":    f"가격(${raw_price:.4f}) <= 매수기준(${level['price']}) / 예산 {int(level['budget_pct']*100)}%",
                    "price":     round(exec_price, 4),
                    "qty":       qty,
                    "avg_cost":  round(avg_cost, 4),
                    "pnl":       0.0,
                    "hold_days": 0,
                    "cash":      round(cash, 2),
                    "shares":    shares,
                    "realized_pnl_cumul": round(realized, 2)
                })
                break

        # Equity curve 기록
        equity = cash + shares * raw_price
        equity_curve.append({
            "date":   date_str,
            "price":  round(raw_price, 4),
            "shares": shares,
            "cash":   round(cash, 2),
            "equity": round(equity, 2)
        })

    # ── 최종 평가 ──────────────────────────────────────────
    final_price = float(df["Close"].iloc[-1])
    final_value = cash + shares * final_price

    return trades, equity_curve, {
        "initial_budget":   INITIAL_BUDGET,
        "commission_rate":  COMMISSION_RATE,
        "slippage_rate":    SLIPPAGE_RATE,
        "final_cash":       round(cash, 2),
        "remaining_shares": shares,
        "final_price":      round(final_price, 4),
        "final_value":      round(final_value, 2),
        "total_return_pct": round((final_value - INITIAL_BUDGET) / INITIAL_BUDGET * 100, 2),
        "realized_pnl":     round(realized, 2),
        "total_trades":     len(trades),
    }

# ============================================================
# 4. 성과 지표 계산
# ============================================================
def compute_metrics(trades, equity_curve, summary):
    print("[4/5] 성과 지표 계산")

    equities = np.array([e["equity"] for e in equity_curve])

    # MDD (최대 낙폭)
    peak       = np.maximum.accumulate(equities)
    drawdown   = (equities - peak) / peak
    mdd        = round(float(drawdown.min()) * 100, 2)

    # 샤프비율 (일간 수익률 기준)
    daily_ret  = np.diff(equities) / equities[:-1]
    sharpe     = round(float(np.mean(daily_ret) / (np.std(daily_ret) + 1e-9) * np.sqrt(252)), 4)

    # 승률 / 평균 수익 / 평균 손실
    sell_trades = [t for t in trades if t["action"] == "SELL"]
    wins        = [t for t in sell_trades if t["pnl"] > 0]
    losses      = [t for t in sell_trades if t["pnl"] <= 0]
    win_rate    = round(len(wins) / len(sell_trades) * 100, 2) if sell_trades else 0
    avg_win     = round(np.mean([t["pnl"] for t in wins]), 2) if wins else 0
    avg_loss    = round(np.mean([t["pnl"] for t in losses]), 2) if losses else 0
    avg_hold    = round(np.mean([t["hold_days"] for t in sell_trades]), 1) if sell_trades else 0

    metrics = {
        "mdd_pct":        mdd,
        "sharpe_ratio":   sharpe,
        "win_rate_pct":   win_rate,
        "avg_win_usd":    avg_win,
        "avg_loss_usd":   avg_loss,
        "avg_hold_days":  avg_hold,
        "total_sell_trades": len(sell_trades),
    }

    print(f"      수익률:     {summary['total_return_pct']}%")
    print(f"      MDD:        {mdd}%")
    print(f"      샤프비율:   {sharpe}")
    print(f"      승률:       {win_rate}% ({len(wins)}승 / {len(losses)}패)")
    print(f"      평균수익:   ${avg_win} / 평균손실: ${avg_loss}")
    print(f"      평균보유:   {avg_hold}일")

    return metrics

# ============================================================
# 5. CSV 저장
# ============================================================
def save_csv(trades, equity_curve):
    # 거래 로그
    if trades:
        fields = list(trades[0].keys())
        with open(TRADE_LOG_PATH, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(trades)
        print(f"      trade_log.csv 저장 ({len(trades)}건)")

    # Equity curve
    if equity_curve:
        fields = list(equity_curve[0].keys())
        with open(EQUITY_LOG_PATH, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(equity_curve)
        print(f"      equity_curve.csv 저장 ({len(equity_curve)}일)")

# ============================================================
# 6. settings 저장
# ============================================================
def save_settings(buy_levels, sell_levels, summary, metrics):
    print("[5/5] urg_settings.json 저장")
    old = read_json(SETTINGS_PATH, default={})
    settings = {
        "ticker":               TICKER,
        "analysis_period":      PERIOD,
        "timezone":             old.get("timezone", "Asia/Seoul"),
        "check_interval_minutes": old.get("check_interval_minutes", 5),
        "buy_levels":           buy_levels,
        "sell_levels":          sell_levels,
        "risk_rules":           old.get("risk_rules", {
            "market_order_forbidden":       True,
            "limit_order_only":             True,
            "do_not_chase":                 True,
            "alert_cooldown_hours":         24,
            "max_one_signal_per_run":       True,
            "sell_below_avg_cost_forbidden": True
        }),
        "generated_at":         datetime.now().isoformat(timespec="seconds"),
        "backtest_summary":     summary,
        "backtest_metrics":     metrics,
    }
    write_json(SETTINGS_PATH, settings)

# ============================================================
# 메인
# ============================================================
def main():
    print("=" * 55)
    print("URG 전략 분석기 v2.0")
    print("=" * 55)

    df                       = load_data()
    buy_levels, sell_levels  = derive_levels(df)
    trades, equity_curve, summary = backtest(df, buy_levels, sell_levels)
    metrics                  = compute_metrics(trades, equity_curve, summary)

    print("[CSV] 저장 중...")
    save_csv(trades, equity_curve)

    save_settings(buy_levels, sell_levels, summary, metrics)

    print("=" * 55)
    print("완료 — trade_log.csv / equity_curve.csv 확인하세요")
    print("=" * 55)

if __name__ == "__main__":
    main()
