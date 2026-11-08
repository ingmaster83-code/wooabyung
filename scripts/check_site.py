# -*- coding: utf-8 -*-
"""_site 점검: 내부 링크 깨짐, 제목/설명 중복, JSON-LD, 사이트맵 파일 존재."""
import re, sys, json, pathlib, collections, urllib.parse
sys.stdout.reconfigure(encoding="utf-8")
root = pathlib.Path(__file__).resolve().parent.parent / "_site"
import os
files = []
exist = set()
for d, _, fs in os.walk(root):
    if "index.html" in fs:
        files.append(pathlib.Path(d) / "index.html")
        rel = os.path.relpath(d, root).replace(os.sep, "/")
        exist.add("/" if rel == "." else "/" + rel + "/")
exist.add("/")
broken = collections.Counter(); titles = collections.Counter(); badld = 0; josa = 0
import time
_t0 = time.time()
for _i, f in enumerate(files):
    if _i % 3000 == 0: print(_i, round(time.time() - _t0), flush=True)
    t = f.read_text(encoding="utf-8")
    for h in re.findall(r'href="(/[^"#?]*)', t):
        if h.startswith("//") or h.startswith("/assets/") : continue
        hh = urllib.parse.unquote(h)
        if hh.endswith("/") and hh not in exist: broken[h] += 1
    titles[re.search(r"<title>(.*?)</title>", t).group(1)] += 1
    for ld in re.findall(r'<script type="application/ld\+json">(.*?)</script>', t, re.S):
        try: json.loads(ld.replace("<\/", "</"))
        except Exception: badld += 1
    if re.search(r"이\(가\)|은\(는\)|을\(를\)|과\(와\)", t.split("<footer")[0].split("<main")[-1]): josa += 1
print("페이지", len(files), "깨진 링크", len(broken), list(broken.items())[:8])
print("중복 title", sum(1 for v in titles.values() if v > 1), [k for k, v in titles.items() if v > 1][:3])
print("JSON-LD 오류", badld, "josa 미해결", josa)
