"""
트레일링 스탑 + 재진입 규칙 엔진 v1.2
=======================================
수정사항:
- 고점 누적 추적 (실행마다 리셋 안 됨)
- 재진입 감시 중엔 트레일링 비활성화
- trail_state.json 에 상태 영구 저장

직접 실행 불필요 — urg_alert.py 에서 import 해서 씀
"""
import sys
from datetime import datetime
from common import BASE_DIR, read_json, write_json, now_iso

TRAIL_STATE_PATH = BASE_DIR / "trail_state.json"

DEFAULT_STATE = {
    "high_price": 0.0,
    "trail_pct": 0.12,
    "reentry_pct": 0.20,
    "last_sell_price": 0.0,
    "trailing_active": False,
    "reentry_active": False,
    "updated_at": ""
}


def load_trail():
    return read_json(TRAIL_STATE_PATH, default=DEFAULT_STATE.copy())


def save_trail(state):
    state["updated_at"] = now_iso()
    write_json(TRAIL_STATE_PATH, state)


def update_high(current_price: float):
    """
    고점 갱신 — 현재가가 저장된 고점보다 높을 때만 갱신
    매 실행마다 리셋되지 않음
    """
    state = load_trail()
    if not state.get("trailing_active"):
        return
    if current_price > state["high_price"]:
        state["high_price"] = current_price
        save_trail(state)
        print(f"[Trailing] 고점 갱신 → ${current_price:.4f}")


def activate_trailing(current_price: float):
    """트레일링 활성화 — 이미 활성화된 경우 고점만 갱신"""
    state = load_trail()
    changed = False

    if not state.get("trailing_active"):
        state["trailing_active"] = True
        state["reentry_active"] = False
        changed = True
        print(f"[Trailing] 활성화")

    # 고점은 현재가가 더 높을 때만 갱신
    if current_price > state["high_price"]:
        state["high_price"] = current_price
        changed = True
        print(f"[Trailing] 고점 갱신 → ${current_price:.4f}")

    if changed:
        save_trail(state)


def activate_reentry(sell_price: float):
    """전량 매도 후 재진입 감시 시작"""
    state = load_trail()
    state["trailing_active"] = False
    state["reentry_active"] = True
    state["last_sell_price"] = sell_price
    state["high_price"] = 0.0
    save_trail(state)
    print(f"[Reentry] 활성화 — 기준가 ${sell_price:.4f} / 재진입 기준 ${sell_price * (1 - state['reentry_pct']):.4f}")


def check_trailing(current_price: float, shares: int):
    """
    트레일링 스탑 체크
    반환: ("TRAIL_STOP", qty, msg) 또는 None
    """
    state = load_trail()
    if not state.get("trailing_active"):
        return None
    if shares <= 0:
        return None

    high = state["high_price"]
    if high <= 0:
        return None

    trail_pct = state["trail_pct"]
    stop_price = high * (1 - trail_pct)
    drop_pct = (high - current_price) / high * 100

    print(f"[Trailing] 고점 ${high:.4f} / 현재 ${current_price:.4f} / 하락 {drop_pct:.1f}% / 스탑 ${stop_price:.4f}")

    if current_price <= stop_price:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        msg = (
            f"🛑 <b>[URG 트레일링 스탑]</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"⏰ {now}\n"
            f"💰 현재가: <b>${current_price:.4f}</b>\n"
            f"📉 고점: ${high:.4f} → 하락 {drop_pct:.1f}%\n"
            f"🎯 스탑 기준: 고점 대비 -{trail_pct*100:.0f}%\n"
            f"━━━━━━━━━━━━━━\n"
            f"✅ 권장 행동\n"
            f"  잔여 <b>{shares}주 전량 매도</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"⚠️ 지정가 주문만\n"
            f"⚠️ 체결 후: py portfolio.py sell {shares} {current_price:.4f}\n"
            f"⚠️ 체결 후: py trailing.py reentry {current_price:.4f}"
        )
        return ("TRAIL_STOP", shares, msg)

    return None


def check_reentry(current_price: float):
    """
    재진입 감시 체크
    반환: ("REENTRY", 0, msg) 또는 None
    """
    state = load_trail()
    if not state.get("reentry_active"):
        return None

    last_sell = state["last_sell_price"]
    if last_sell <= 0:
        return None

    reentry_pct = state["reentry_pct"]
    reentry_price = last_sell * (1 - reentry_pct)
    drop_pct = (last_sell - current_price) / last_sell * 100

    print(f"[Reentry] 기준가 ${last_sell:.4f} / 현재 ${current_price:.4f} / 하락 {drop_pct:.1f}% / 재진입 ${reentry_price:.4f}")

    if current_price <= reentry_price:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        msg = (
            f"🔄 <b>[URG 재진입 알림]</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"⏰ {now}\n"
            f"💰 현재가: <b>${current_price:.4f}</b>\n"
            f"📉 마지막 매도가: ${last_sell:.4f} → 하락 {drop_pct:.1f}%\n"
            f"🎯 재진입 기준: 매도가 대비 -{reentry_pct*100:.0f}%\n"
            f"━━━━━━━━━━━━━━\n"
            f"✅ 권장 행동\n"
            f"  1차 매수 구간부터 분할 매수 재시작\n"
            f"━━━━━━━━━━━━━━\n"
            f"⚠️ 지정가 주문만\n"
            f"⚠️ 체결 후: py portfolio.py buy [수량] {current_price:.4f}\n"
            f"⚠️ 체결 후: py trailing.py activate {current_price:.4f}"
        )
        return ("REENTRY", 0, msg)

    return None


# ============================================================
# CLI
# ============================================================
if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        state = load_trail()
        print("=" * 40)
        print("Trail State")
        print("=" * 40)
        print(f"트레일링 활성: {state.get('trailing_active')}")
        print(f"재진입 감시:   {state.get('reentry_active')}")
        print(f"고점:          ${state.get('high_price', 0):.4f}")
        print(f"마지막 매도가: ${state.get('last_sell_price', 0):.4f}")
        print(f"트레일 기준:   -{state.get('trail_pct', 0)*100:.0f}%")
        print(f"재진입 기준:   -{state.get('reentry_pct', 0)*100:.0f}%")
        print(f"업데이트:      {state.get('updated_at')}")

    elif args[0] == "activate" and len(args) >= 2:
        activate_trailing(float(args[1]))
        print("트레일링 스탑 활성화 완료")

    elif args[0] == "reentry" and len(args) >= 2:
        activate_reentry(float(args[1]))
        print("재진입 감시 활성화 완료")

    elif args[0] == "set" and len(args) >= 3:
        state = load_trail()
        key, val = args[1], float(args[2])
        state[key] = val
        save_trail(state)
        print(f"{key} = {val} 저장 완료")

    elif args[0] == "reset":
        save_trail(DEFAULT_STATE.copy())
        print("trail_state.json 초기화 완료")

    else:
        print("사용법:")
        print("  py trailing.py                        # 현재 상태")
        print("  py trailing.py activate 2.11          # 트레일링 활성화")
        print("  py trailing.py reentry 2.11           # 재진입 감시 시작")
        print("  py trailing.py set trail_pct 0.10     # 스탑 기준 변경")
        print("  py trailing.py set reentry_pct 0.15   # 재진입 기준 변경")
        print("  py trailing.py reset                  # 전체 초기화")
