from common import read_json

SETTINGS_PATH = "settings.json"


# =========================================================
# 실행 모드 체크
# =========================================================
def is_live_mode():
    settings = read_json(SETTINGS_PATH)
    return settings.get("execution_mode", "paper") == "live"


# =========================================================
# 주문 실행 (핵심 게이트)
# =========================================================
def place_order(action, qty, price):
    settings = read_json(SETTINGS_PATH)

    mode = settings.get("execution_mode", "paper")

    # -----------------------------------------------------
    # ✔ PAPER MODE
    # -----------------------------------------------------
    if mode == "paper":
        print(f"[PAPER MODE] {action} {qty} @ {price}")
        return {
            "status": "paper",
            "action": action,
            "qty": qty,
            "price": price
        }

    # -----------------------------------------------------
    # ✔ LIVE MODE (여기서 KIS API 붙일 예정)
    # -----------------------------------------------------
    elif mode == "live":
        print(f"[LIVE ORDER] {action} {qty} @ {price}")

        # TODO: KIS 주문 API 연결
        # kis_api.place_order(...)

        return {
            "status": "live_sent",
            "action": action,
            "qty": qty,
            "price": price
        }

    else:
        raise Exception("Invalid execution_mode")