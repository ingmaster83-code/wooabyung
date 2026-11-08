# -*- coding: utf-8 -*-
"""
우아병역 수집기 — 병무청 공공데이터 2종 (data.go.kr)
  · 전문연구/산업기능요원 지정업체 정보 3066759  →  apis.data.go.kr/1300000/jjEopChe/list2/getjjEopChe   → data/jj.json.gz
  · 병역일터 채용공고            3065599  →  apis.data.go.kr/1300000/CyJeongBo/list                    → data/cy.json.gz
키: 환경변수 API_KEY → DATA_GO_KR_API_KEY → 로컬 ../hosppass/.env 의 API_KEY (코드에 넣지 않는다).
수집 결과가 직전 대비 너무 적으면(지정업체 90% 미만) 실패 처리해 빈 데이터로 사이트가 덮이지 않게 한다.
"""
import gzip, json, os, re, sys, time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
BAD = {c for c in range(0, 32) if c not in (9, 10, 13)} | {0xFFFE, 0xFFFF}


def api_key():
    for name in ("API_KEY", "DATA_GO_KR_API_KEY"):
        if os.environ.get(name):
            return os.environ[name].strip()
    for p in (ROOT / ".env", ROOT.parent / "hosppass" / ".env"):
        if p.exists():
            m = re.search(r"^API_KEY\s*=\s*(\S+)", p.read_text(encoding="utf-8"), re.M)
            if m:
                return m.group(1).strip("\"'")
    sys.exit("환경변수 API_KEY 가 필요합니다.")


KEY = api_key()
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"


def clean(t):
    return "".join(ch for ch in t if ord(ch) not in BAD)


def pull(url, n):
    out, page = [], 1
    while True:
        last = ""
        for attempt in range(6):
            try:
                r = S.get(url, params=dict(serviceKey=KEY, numOfRows=n, pageNo=page), timeout=120)
                txt = clean(r.content.decode("utf-8", "replace"))
                if "LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND" in txt:
                    last = "rate"; time.sleep(15 + 5 * attempt); continue
                root = ET.fromstring(txt.encode("utf-8"))
                if root.tag == "OpenAPI_ServiceResponse":
                    raise RuntimeError(txt[:300])
                if root.findtext("./header/resultCode") != "00":
                    raise RuntimeError(root.findtext("./header/resultMsg"))
                break
            except (requests.RequestException, ET.ParseError) as e:
                last = str(e); time.sleep(3 + 3 * attempt)
        else:
            raise RuntimeError("API 실패: %s %s" % (url, last))
        total = int(root.findtext("./body/totalCount"))
        out += [{c.tag: (c.text or "").strip() for c in it} for it in root.findall("./body/items/item")]
        print("  %s %d/%d" % (url.rsplit("/", 2)[-2], len(out), total), flush=True)
        if page * n >= total:
            return out
        page += 1
        time.sleep(0.4)


def save(p, obj):
    tmp = p.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    tmp.replace(p)


def main():
    jj = pull("https://apis.data.go.kr/1300000/jjEopChe/list2/getjjEopChe", 1000)
    cy = pull("https://apis.data.go.kr/1300000/CyJeongBo/list", 100)
    old = DATA / "jj.json.gz"
    if old.exists():
        prev = len(json.loads(gzip.open(old, "rt", encoding="utf-8").read()))
        if len(jj) < prev * 0.9:
            sys.exit("지정업체 수가 직전(%d)보다 90%% 미만(%d)이라 중단" % (prev, len(jj)))
    save(DATA / "jj.json.gz", jj)
    save(DATA / "cy.json.gz", cy)
    print("지정업체", len(jj), "채용공고", len(cy))


if __name__ == "__main__":
    main()
