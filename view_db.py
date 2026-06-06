import sqlite3
import pandas as pd

DB = "urg_log.db"
conn = sqlite3.connect(DB)

tables = ["price_snapshot", "equity_snapshot", "trade_log", "strategy_state"]

for t in tables:
    print("\n====================")
    print(t)
    print("====================")

    try:
        df = pd.read_sql(f"SELECT * FROM {t}", conn)
        print(df.tail(20))

        # ✔ CSV 자동 저장 추가
        df.to_csv(f"{t}.csv", index=False)

    except Exception as e:
        print("ERROR:", e)

conn.close()
