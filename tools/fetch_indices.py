"""「주식 한 판」 위젯이 읽을 주요 지수 데이터를 받아 jusik-hanpan/data/indices.json 으로 저장한다.

야후 금융 차트 API(비공식, 키 없음)에서 최근 6개월 일별 종가를 받는다.
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

# 위젯에 보여 줄 지수. id 는 위젯이 「담기」 기록에 쓰는 이름이라 바꾸지 않는다
INDICES = [
    {"id": "KOSPI", "symbol": "^KS11", "name": "코스피", "region": "한국"},
    {"id": "KOSDAQ", "symbol": "^KQ11", "name": "코스닥", "region": "한국"},
    {"id": "SP500", "symbol": "^GSPC", "name": "S&P 500", "region": "미국"},
    {"id": "NASDAQ", "symbol": "^IXIC", "name": "나스닥", "region": "미국"},
    {"id": "DOW", "symbol": "^DJI", "name": "다우존스", "region": "미국"},
    {"id": "NIKKEI", "symbol": "^N225", "name": "닛케이 225", "region": "일본"},
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


def fetch(symbol):
    url = URL.format(symbol=urllib.request.quote(symbol))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20, context=CONTEXT) as res:
        data = json.load(res)
    result = data["chart"]["result"][0]
    offset = result["meta"].get("gmtoffset", 0)  # 그 거래소 현지 날짜로 맞추려고 쓴다
    dates, closes = [], []
    for ts, close in zip(result["timestamp"], result["indicators"]["quote"][0]["close"]):
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
            dates, closes = fetch(item["symbol"])
        except Exception as error:  # 하나가 실패해도 나머지는 저장한다
            failed.append(f"{item['symbol']}: {error}")
            continue
        out["indices"].append({**item, "dates": dates, "closes": closes})
        time.sleep(0.5)

    if not out["indices"]:
        sys.exit("지수를 하나도 못 받았다:\n" + "\n".join(failed))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"저장: {OUT} ({len(out['indices'])}개)")
    for line in failed:
        print("실패", line)


if __name__ == "__main__":
    main()
