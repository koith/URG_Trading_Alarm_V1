"""
URG 스케줄러 v1.4
- 5분마다 실행 (urg_settings.json check_interval_minutes 반영)
- 한국시간 기준 미국 정규장 감지
- 서머타임 근사 반영
- sync_portfolio 30분 주기 연동 (KIS API 토큰 절약)
- heartbeat: 1시간마다 텔레그램 생존 알림 (장 외 시간 포함)

실행: py urg_scheduler.py
"""
import schedule
import time
from datetime import datetime, timedelta
import pytz

from common import read_json, SETTINGS_PATH
from urg_alert import main as run_alert, init_db, send_telegram
from sync_portfolio import main as run_sync

KST = pytz.timezone("Asia/Seoul")
SYNC_INTERVAL_MINUTES      = 30
HEARTBEAT_INTERVAL_MINUTES = 60

_last_sync_time = None


def heartbeat():
    """1시간마다 스케줄러 생존 알림 전송 (장 외 시간 포함)"""
    now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    msg = f"[URG] 스케줄러 정상 실행 중 | {now_str}"
    print(f"[Heartbeat] {now_str}")
    try:
        send_telegram(msg)
    except Exception as e:
        print(f"[Heartbeat] 전송 오류: {e}")


def is_us_dst_rough(now_kst):
    return 3 <= now_kst.month <= 10


def is_market_time():
    now = datetime.now(KST)
    minutes = now.hour * 60 + now.minute
    if is_us_dst_rough(now):
        start, end = 22 * 60 + 30, 5 * 60
    else:
        start, end = 23 * 60 + 30, 6 * 60
    return minutes >= start or minutes < end


def job():
    global _last_sync_time
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    if is_market_time():
        print(f"\n[{now}] 장 시간 → 체크 실행")

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

        run_alert()
    else:
        print(f"[{now}] 장 외 시간 → 스킵")


def main():
    settings = read_json(SETTINGS_PATH)
    interval = int(settings.get("check_interval_minutes", 5))
    print("=" * 50)
    print("URG 스케줄러 v1.4")
    print(f"체크 주기: {interval}분 / 동기화: {SYNC_INTERVAL_MINUTES}분 / Heartbeat: {HEARTBEAT_INTERVAL_MINUTES}분")
    print("종료: Ctrl+C")
    print("=" * 50)
    init_db()  # 장 외 시간 배포 시에도 DB 테이블 보장
    schedule.every(interval).minutes.do(job)
    schedule.every(HEARTBEAT_INTERVAL_MINUTES).minutes.do(heartbeat)
    heartbeat()  # 시작 즉시 1회 전송
    job()
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
