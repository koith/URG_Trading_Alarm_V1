# URG Box Trading Assistant v1.1

자동매매가 아닌 **매매 가이드 알림 시스템**입니다.
실제 주문은 본인이 직접 실행합니다.

## 파일 구조
```
├── common.py           # 공통 유틸
├── trailing.py         # 트레일링 스탑 + 재진입 엔진
├── portfolio.py        # 포트폴리오 수동 추적
├── urg_alert.py        # 가격 조회 + 신호 판정 + 텔레그램
├── urg_analyze.py      # 구간 재분석 + 백테스트
├── urg_scheduler.py    # 5분마다 자동 반복
├── urg_settings.json   # 전략 설정 (자동 생성)
├── portfolio.json      # 보유/평단/손익 상태
├── trail_state.json    # 트레일링 상태 (자동 생성)
├── alert_state.json    # 알림 쿨다운 상태
├── .env                # 텔레그램 토큰 (직접 생성)
└── requirements.txt
```

## 설치
```powershell
py -m pip install -r requirements.txt
```

## .env 파일 만들기
프로젝트 폴더에 `.env` 파일 생성 후:
```
TELEGRAM_TOKEN=발급받은_토큰
TELEGRAM_CHAT_ID=6946217892
```

## 포트폴리오 초기화
```powershell
py portfolio.py init --shares 1600 --avg-cost 1.4063 --cash 844 --budget 10000
py portfolio.py show
```

## 알림 테스트
```powershell
py urg_alert.py
```

## 자동 실행 (5분마다)
```powershell
py urg_scheduler.py
```

## 트레일링 스탑 관리
```powershell
py trailing.py                        # 현재 상태 확인
py trailing.py activate 2.11         # 트레일링 활성화 (현재가 입력)
py trailing.py reentry 2.11          # 전량 매도 후 재진입 감시 시작
py trailing.py set trail_pct 0.10    # 스탑 기준 변경 (기본 12%)
py trailing.py set reentry_pct 0.15  # 재진입 기준 변경 (기본 20%)
```

## 매매 체결 후 반드시 반영
```powershell
py portfolio.py sell 400 2.11   # 매도 체결 후
py portfolio.py buy 300 1.00    # 매수 체결 후
py portfolio.py show            # 현재 상태 확인
```

## 구간 재분석 (분기마다)
```powershell
py urg_analyze.py
```

## 신호 우선순위
1. 트레일링 스탑 (가장 먼저)
2. 매도 구간 (평단 + 수익률 조건 충족 시)
3. 재진입 감시
4. 매수 구간

## 동적 매도 비율
수익률에 따라 자동 조정:
- 기본: settings 비율
- 수익 +35% 이상: +10%
- 수익 +45% 이상: +20%

## 주의사항
- 자동주문 없음
- 시장가 금지 / 지정가만
- 미체결 시 추격 금지
- 체결 후 반드시 portfolio.py 반영
