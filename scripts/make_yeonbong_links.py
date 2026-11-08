# -*- coding: utf-8 -*-
"""
우아연봉(wooayeonbong) 회사 페이지와 병역지정업체를 연결하는 매칭표를 만든다 → data/yeonbong_links.json  {사업자번호: 우아연봉 slug}
매칭 규칙: 사업자번호 앞 6자리(국민연금 DB의 biz) 일치 + 정규화한 회사명 일치, 그리고 우아연봉 _site/company/{slug}/ 가 실제로 존재할 것.
우아연봉을 다시 빌드한 뒤 수동으로 한 번 더 실행하면 갱신된다(월 1회 정도).
사용: python scripts/make_yeonbong_links.py
"""
import gzip, json, re, sys, unicodedata
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
YB = ROOT.parent / "wooayeonbong"


def slugify(name):  # wooayeonbong/scripts/build_site.py 와 동일
    s = unicodedata.normalize("NFKC", name)
    s = re.sub(r"주식회사|유한회사|유한책임회사|사단법인|재단법인|학교법인|사회복지법인|의료법인", "", s)
    s = re.sub(r"\([^)]{0,6}\)", "", s)
    s = re.sub(r'[\\/?#%&"<>|:*\'`~!@$^+=,;\[\]{}]', "", s)
    s = s.replace("(", "").replace(")", "")
    s = re.sub(r"\s+", "-", s.strip()).strip(".-")
    return s or "회사"


def norm(n):
    n = unicodedata.normalize("NFKC", n or "")
    n = re.sub(r"\(주\)|주식회사|\(유\)|유한회사", "", n)
    n = re.sub(r"[\s\-·.,]+", "", n)
    n = re.sub(r"\[.*?\]|\(.*?\)", "", n)
    return n.lower()


def main():
    cs = json.load(gzip.open(YB / "_data" / "companies.json.gz", "rt", encoding="utf-8"))["companies"]
    exist = {p.name for p in (YB / "_site" / "company").iterdir() if p.is_dir()}
    print("우아연봉 회사 페이지", len(exist))
    used, key2slug = {}, {}
    for c in cs:
        if c["n"] < 30:
            continue
        name = unicodedata.normalize("NFKC", c["name"])
        sl = slugify(name)
        if sl in used:
            sl = sl + "-" + c["biz"]
        used[sl] = 1
        if sl in exist:
            key2slug.setdefault((c["biz"], norm(name)), sl)
    jj = json.loads(gzip.open(ROOT / "data" / "jj.json.gz", "rt", encoding="utf-8").read())
    out = {}
    for x in jj:
        brn = x.get("saeopjaDrno", "")
        if len(brn) < 6:
            continue
        sl = key2slug.get((brn[:6], norm(x.get("eopcheNm", ""))))
        if sl:
            out[brn] = sl
    json.dump(out, open(ROOT / "data" / "yeonbong_links.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("연결", len(out), "곳")


if __name__ == "__main__":
    main()
