"""
URG 포트폴리오 수동 추적기

사용 예시:
  py portfolio.py show
  py portfolio.py init --shares 2000 --avg-cost 1.4063 --cash 0 --budget 10000
  py portfolio.py buy 100 1.00
  py portfolio.py sell 100 1.80
"""
import argparse
from common import PORTFOLIO_PATH, read_json, write_json, now_iso


def load_portfolio():
    return read_json(PORTFOLIO_PATH)


def save_portfolio(p):
    p["updated_at"] = now_iso()
    write_json(PORTFOLIO_PATH, p)


def show():
    p = load_portfolio()
    print("=" * 50)
    print("URG Portfolio")
    print("=" * 50)
    print(f"보유수량: {p['shares']}주")
    print(f"평단가: ${p['avg_cost']:.4f}")
    print(f"현금: ${p['cash_usd']:.2f}")
    print(f"총 예산: ${p['total_budget_usd']:.2f}")
    print(f"실현손익: ${p['realized_pnl_usd']:.2f}")
    print(f"업데이트: {p.get('updated_at')}")
    print(f"거래기록: {len(p.get('trades', []))}건")


def init(args):
    p = load_portfolio()
    p.update({
        "total_budget_usd": float(args.budget),
        "cash_usd": float(args.cash),
        "shares": int(args.shares),
        "avg_cost": float(args.avg_cost),
        "realized_pnl_usd": float(args.realized_pnl),
        "trades": p.get("trades", [])
    })
    save_portfolio(p)
    show()


def buy(args):
    qty = int(args.qty)
    price = float(args.price)
    fee = float(args.fee)
    if qty <= 0 or price <= 0:
        raise ValueError("수량과 가격은 0보다 커야 합니다.")

    p = load_portfolio()
    old_shares = int(p["shares"])
    old_avg = float(p["avg_cost"])
    cost = qty * price + fee
    new_shares = old_shares + qty
    new_avg = ((old_shares * old_avg) + cost) / new_shares if new_shares else 0.0

    p["cash_usd"] = float(p.get("cash_usd", 0.0)) - cost
    p["shares"] = new_shares
    p["avg_cost"] = round(new_avg, 6)
    p.setdefault("trades", []).append({
        "time": now_iso(), "action": "BUY", "qty": qty, "price": price,
        "fee": fee, "amount": round(cost, 4), "shares_after": new_shares,
        "avg_cost_after": p["avg_cost"]
    })
    save_portfolio(p)
    show()


def sell(args):
    qty = int(args.qty)
    price = float(args.price)
    fee = float(args.fee)
    if qty <= 0 or price <= 0:
        raise ValueError("수량과 가격은 0보다 커야 합니다.")

    p = load_portfolio()
    old_shares = int(p["shares"])
    if qty > old_shares:
        raise ValueError(f"보유수량 초과 매도: 보유 {old_shares}주, 입력 {qty}주")

    avg = float(p["avg_cost"])
    proceeds = qty * price - fee
    realized = (price - avg) * qty - fee
    new_shares = old_shares - qty

    p["cash_usd"] = float(p.get("cash_usd", 0.0)) + proceeds
    p["shares"] = new_shares
    p["avg_cost"] = round(avg if new_shares > 0 else 0.0, 6)
    p["realized_pnl_usd"] = round(float(p.get("realized_pnl_usd", 0.0)) + realized, 4)
    p.setdefault("trades", []).append({
        "time": now_iso(), "action": "SELL", "qty": qty, "price": price,
        "fee": fee, "amount": round(proceeds, 4), "realized_pnl": round(realized, 4),
        "shares_after": new_shares, "avg_cost_after": p["avg_cost"]
    })
    save_portfolio(p)
    show()


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("show")

    p_init = sub.add_parser("init")
    p_init.add_argument("--shares", required=True)
    p_init.add_argument("--avg-cost", required=True)
    p_init.add_argument("--cash", default=0)
    p_init.add_argument("--budget", default=10000)
    p_init.add_argument("--realized-pnl", default=0)

    p_buy = sub.add_parser("buy")
    p_buy.add_argument("qty")
    p_buy.add_argument("price")
    p_buy.add_argument("--fee", default=0)

    p_sell = sub.add_parser("sell")
    p_sell.add_argument("qty")
    p_sell.add_argument("price")
    p_sell.add_argument("--fee", default=0)

    args = parser.parse_args()
    if args.cmd == "show":
        show()
    elif args.cmd == "init":
        init(args)
    elif args.cmd == "buy":
        buy(args)
    elif args.cmd == "sell":
        sell(args)


if __name__ == "__main__":
    main()
