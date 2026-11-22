"""「주식 한 판」 위젯이 읽을 주요 지수와 원/달러 환율을 받아 jusik-hanpan/data/indices.json 으로 저장한다.

야후 금융 차트 API(비공식, 키 없음)에서 최근 6개월 일별 종가를 받는다.
장이 열려 있는 날의 값은 종가가 아니라서 빼고, 끝난 날까지만 저장한다.
브라우저에서 직접 부르면 CORS 로 막히기 때문에, 이 스크립트가 미리 받아 두고 위젯은 같은 저장소의 파일만 읽는다.

    python3 tools/fetch_indices.py

표준 라이브러리만 쓴다.
"""

import json
import os
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 위젯에 보여 줄 지수와 환율. id 는 위젯이 「담기」 기록에 쓰는 이름이라 바꾸지 않는다
# tz_hours 를 적으면 거래소 시간대 대신 그 시간대(한국 = 9)로 날짜를 끊는다
INDICES = [
    {"id": "KOSPI", "symbol": "^KS11", "name": "코스피", "region": "한국"},
    {"id": "KOSDAQ", "symbol": "^KQ11", "name": "코스닥", "region": "한국"},
    {"id": "SP500", "symbol": "^GSPC", "name": "S&P 500", "region": "미국"},
    {"id": "NASDAQ", "symbol": "^IXIC", "name": "나스닥", "region": "미국"},
    {"id": "DOW", "symbol": "^DJI", "name": "다우존스", "region": "미국"},
    {"id": "NIKKEI", "symbol": "^N225", "name": "닛케이 225", "region": "일본"},
    {"id": "USDKRW", "symbol": "KRW=X", "name": "원/달러", "region": "환율", "tz_hours": 9},
]

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=6mo&interval=1d"
OUT = Path(__file__).resolve().parent.parent / "jusik-hanpan" / "data" / "indices.json"
KST = timezone(timedelta(hours=9))


def ssl_context():
    """python.org 판 파이썬은 맥에서 인증서 묶음을 못 찾을 때가 있어 시스템 인증서로 대신한다."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    if os.path.exists("/etc/ssl/cert.pem"):
        return ssl.create_default_context(cafile="/etc/ssl/cert.pem")
    return ssl.create_default_context()


CONTEXT = ssl_context()


def drop_unfinished(stamps, closes):
    """마지막 값이 아직 안 끝난 날의 시세면 뺀다.

    끝난 날의 값은 시각이 날마다 같은 자리(장 시작 시각)에 찍히고, 진행 중인 날은 받은 순간의 시각이 찍힌다.
    그래서 마지막 두 시각의 간격이 하루 단위로 안 떨어지면 진행 중으로 본다 (서머타임이 바뀌는 날의 1시간 차이는 봐준다).
    """
    if len(stamps) < 2:
        return stamps, closes
    gap = (stamps[-1] - stamps[-2]) % 86400
    if gap in (0, 3600, 82800):
        return stamps, closes
    return stamps[:-1], closes[:-1]


def fetch(symbol, tz_hours=None):
    url = URL.format(symbol=urllib.request.quote(symbol))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20, context=CONTEXT) as res:
        data = json.load(res)
    result = data["chart"]["result"][0]
    # 그 거래소 현지 날짜로 맞춘다. 환율처럼 거래소가 없는 것은 tz_hours 로 정한 시간대를 쓴다
    offset = tz_hours * 3600 if tz_hours is not None else result["meta"].get("gmtoffset", 0)
    stamps, values = drop_unfinished(result["timestamp"], result["indicators"]["quote"][0]["close"])
    dates, closes = [], []
    for ts, close in zip(stamps, values):
        if close is None:  # 휴장일 등 빈 값은 건너뛴다
            continue
        day = datetime.fromtimestamp(ts + offset, tz=timezone.utc).strftime("%Y-%m-%d")
        if dates and dates[-1] == day:  # 같은 날이 두 번 오면 뒤의 값으로 덮는다
            closes[-1] = round(close, 2)
            continue
        dates.append(day)
        closes.append(round(close, 2))
    return dates, closes


def main():
    out = {
        "updated_at": datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "source": "Yahoo Finance 차트 API (비공식)",
        "indices": [],
    }
    failed = []
    for item in INDICES:
        try:
            dates, closes = fetch(item["symbol"], item.get("tz_hours"))
        except Exception as error:  # 하나가 실패해도 나머지는 저장한다
            failed.append(f"{item['symbol']}: {error}")
            continue
        if len(closes) < 2:  # 전날 대비를 계산하려면 이틀 치는 있어야 한다
            failed.append(f"{item['symbol']}: 받은 값이 {len(closes)}개뿐")
            continue
        public = {key: item[key] for key in ("id", "symbol", "name", "region")}
        out["indices"].append({**public, "dates": dates, "closes": closes})
        time.sleep(0.5)

    if not out["indices"]:
        sys.exit("지수를 하나도 못 받았다:\n" + "\n".join(failed))

    # 휴장일처럼 숫자가 그대로면 파일을 다시 쓰지 않는다 (자동 실행이 빈 커밋을 쌓지 않게)
    if OUT.exists():
        try:
            before = json.loads(OUT.read_text(encoding="utf-8"))
            if before.get("indices") == out["indices"]:
                print("변화 없음: 파일을 그대로 둔다")
                return
        except ValueError:
            pass

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"저장: {OUT} ({len(out['indices'])}개)")
    for line in failed:
        print("실패", line)


if __name__ == "__main__":
    main()
