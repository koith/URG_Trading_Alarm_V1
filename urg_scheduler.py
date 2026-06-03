"""
URG 스케줄러 v1.1
- 5분마다 실행 (urg_settings.json check_interval_minutes 반영)
- 한국시간 기준 미국 정규장 감지
- 서머타임 근사 반영

실행: py urg_scheduler.py
"""
import schedule
import time
from datetime import datetime
import pytz

from common import read_json, SETTINGS_PATH
from urg_alert import main as run_alert

KST = pytz.timezone("Asia/Seoul")


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
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    if is_market_time():
        print(f"\n[{now}] 장 시간 → 체크 실행")
        run_alert()
    else:
        print(f"[{now}] 장 외 시간 → 스킵")


def main():
    settings = read_json(SETTINGS_PATH)
    interval = int(settings.get("check_interval_minutes", 5))
    print("=" * 50)
    print("URG 스케줄러 v1.1")
    print(f"체크 주기: {interval}분")
    print("종료: Ctrl+C")
    print("=" * 50)
    schedule.every(interval).minutes.do(job)
    job()
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
