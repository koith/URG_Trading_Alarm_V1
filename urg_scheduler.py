"""
URG 스케줄러 v1.5
- 5분마다 실행 (urg_settings.json check_interval_minutes 반영)
- 프리마켓 + 정규장 + 장 외 시간 구간 감지 (market_rules 기반)
- sync_portfolio 30분 주기 연동 (정규장 전용)
- heartbeat: 1시간마다 텔레그램 생존 알림

실행: py urg_scheduler.py
"""
import schedule
import time
from datetime import datetime, timedelta
import pytz

from common import read_json, SETTINGS_PATH
from urg_alert import main as run_alert, init_db
from sync_portfolio import main as run_sync

KST = pytz.timezone("Asia/Seoul")
SYNC_INTERVAL_MINUTES      = 30
HEARTBEAT_INTERVAL_MINUTES = 60

_last_sync_time = None

DEFAULT_MARKET_RULES = {
    "enable_premarket_watch": True,
    "premarket_start_kst": "17:00",
    "regular_start_kst": "22:30",
    "regular_end_kst": "05:00",
    "allow_alerts_in_premarket": False,
}


def heartbeat():
    """1시간마다 Railway Deploy Logs에 생존 기록"""
    now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    print(f"[HEARTBEAT] URG 스케줄러 정상 실행 중 | {now_str}")


def _parse_hm(s):
    """'HH:MM' → 분 단위 정수"""
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def get_market_segment(rules):
    """
    현재 KST 시각 기준으로 시장 구간 반환.
    반환값: 'regular' | 'premarket' | 'closed'
    정규장(22:30~05:00)은 자정을 넘기 때문에 OR 조건으로 판단.
    """
    now = datetime.now(KST)
    cur = now.hour * 60 + now.minute

    regular_start   = _parse_hm(rules.get("regular_start_kst",   "22:30"))  # 1350분
    regular_end     = _parse_hm(rules.get("regular_end_kst",     "05:00"))  # 300분
    premarket_start = _parse_hm(rules.get("premarket_start_kst", "17:00"))  # 1020분

    if cur >= regular_start or cur < regular_end:
        return "regular"

    if rules.get("enable_premarket_watch", False):
        if premarket_start <= cur < regular_start:
            return "premarket"

    return "closed"


def job():
    global _last_sync_time
    now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    try:
        settings = read_json(SETTINGS_PATH)
    except Exception:
        settings = {}
    rules = settings.get("market_rules", DEFAULT_MARKET_RULES)
    segment = get_market_segment(rules)

    if segment == "regular":
        print(f"\n[{now_str}] [정규장] 체크 실행")

        now_dt = datetime.now()
        if _last_sync_time is None or now_dt - _last_sync_time >= timedelta(minutes=SYNC_INTERVAL_MINUTES):
            print("[Sync] 포트폴리오 동기화 시작...")
            try:
                run_sync()
                _last_sync_time = now_dt
            except Exception as e:
                print(f"[Sync] 오류 (계속 진행): {e}")
        else:
            remaining = SYNC_INTERVAL_MINUTES - int((now_dt - _last_sync_time).seconds / 60)
            print(f"[Sync] 스킵 (다음 동기화까지 약 {remaining}분)")

        run_alert(market_segment="regular")

    elif segment == "premarket":
        print(f"\n[{now_str}] [프리마켓] 체크 실행")
        run_alert(market_segment="premarket")

    else:
        print(f"[{now_str}] [장 외 시간] 스킵")


def main():
    settings = read_json(SETTINGS_PATH)
    interval = int(settings.get("check_interval_minutes", 5))
    print("=" * 50)
    print("URG 스케줄러 v1.5")
    print(f"체크 주기: {interval}분 / 동기화: {SYNC_INTERVAL_MINUTES}분 / Heartbeat: {HEARTBEAT_INTERVAL_MINUTES}분")
    print("종료: Ctrl+C")
    print("=" * 50)
    init_db()
    schedule.every(interval).minutes.do(job)
    schedule.every(HEARTBEAT_INTERVAL_MINUTES).minutes.do(heartbeat)
    heartbeat()
    job()
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
