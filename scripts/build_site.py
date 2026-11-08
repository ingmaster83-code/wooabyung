# -*- coding: utf-8 -*-
"""우아병역 정적 사이트 생성기.
입력: data/jj.json.gz(지정업체) · data/cy.json.gz(채용공고) · data/roster_*.csv(2026 산업기능요원 인원배정 명부) · data/yeonbong_links.json
출력: _site/  (지정업체 상세, 업종·지역 허브, 채용공고, 안내 페이지, 검색 인덱스, sitemap)
"""
import collections, csv, gzip, hashlib, json, re, shutil, sys, unicodedata
from datetime import date, datetime, timedelta, timezone

from common import *  # noqa

sys.stdout.reconfigure(encoding="utf-8")
DATA = ROOT / "data"
TODAY = (datetime.now(timezone.utc) + timedelta(hours=9)).date()
YEAR = TODAY.year

# ───────────────────────── 코드표 ─────────────────────────
# 업종 코드(병무청) → (업종명, 요원 구분). 이름은 채용공고 API의 업종명, 인원배정 명부의 업종, 업체명 표본으로 정리했다.
TYPES = {
    "industrial": ("산업기능요원", "🏭", "제조·정보처리·건설 등 병역지정업체에서 근무하며 병역을 이행하는 제도"),
    "researcher": ("전문연구요원", "🔬", "연구기관·기업부설연구소 등 병역지정업체에서 연구 업무에 종사하며 병역을 이행하는 제도"),
    "seafarer": ("승선근무예비역", "🚢", "해운업·수산업 병역지정업체에서 선박에 승선해 근무하며 병역을 이행하는 제도"),
}
CODE = {
    "11101": "철강", "11102": "기계", "11103": "전기", "11104": "전자", "11105": "화학", "11106": "섬유", "11107": "신발", "11108": "시멘요업",
    "11109": "생활용품", "11110": "통신기기", "11111": "정보처리", "11112": "게임S/W", "11113": "기타 공업", "11114": "의료의약", "11115": "식음료",
    "11116": "농산물가공", "11117": "수산물가공", "11118": "임산물가공", "11119": "동물약품", "11120": "애니메이션", "11121": "동물사료",
    "11203": "선광제련", "11301": "에너지", "11401": "국내건설", "11402": "국외건설", "11504": "해운(산업기능)", "11602": "수산(산업기능)",
    "12105": "민영방산",
    "21101": "연구기관·연구소", "21102": "연구기관·연구소", "21103": "연구기관·연구소", "21201": "연구기관·연구소", "21301": "연구기관·연구소", "21401": "연구기관·연구소",
    "21501": "기업부설연구소(기타)", "21502": "중소기업부설연구소", "21503": "벤처기업부설연구소", "21504": "중견기업부설연구소",
    "23101": "대학원", "23201": "대학 연구소·센터", "24101": "국방 관련 연구기관",
    "31101": "원양어업", "32101": "해운업",
}
SIZE = {"01": "대기업", "02": "중소기업", "03": "벤처기업", "04": "중견기업"}  # 그 외 코드(A1·Z)는 규모 구분이 아닌 연구기관 등
SIDO_FIX = {"서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시", "광주": "광주광역시", "대전": "대전광역시",
            "울산": "울산광역시", "세종": "세종특별자치시", "경기": "경기도", "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
            "전북": "전북특별자치도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도", "제주": "제주특별자치도",
            "강원도": "강원특별자치도", "전라북도": "전북특별자치도"}
SIDOS = {"서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원특별자치도",
         "충청북도", "충청남도", "전북특별자치도", "전라남도", "경상북도", "경상남도", "제주특별자치도", "전남광주통합특별시"}
SHORT = {"서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산",
         "세종특별자치시": "세종", "경기도": "경기", "강원특별자치도": "강원", "충청북도": "충북", "충청남도": "충남", "전북특별자치도": "전북",
         "전라남도": "전남", "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주", "전남광주통합특별시": "전남광주"}


def norm(n):
    n = unicodedata.normalize("NFKC", n or "")
    n = re.sub(r"\(주\)|㈜|주식회사|\(유\)|유한회사|\s+", "", n)
    n = re.sub(r"\[.*?\]|\(.*?\)", "", n)
    return n.lower()


def ctype(code):
    if code.startswith(("11", "12")):
        return "industrial"
    if code.startswith("2"):
        return "researcher"
    if code.startswith("3"):
        return "seafarer"
    return None


def parse_region(addr):
    t = (addr or "").split()
    if not t:
        return None, None
    sido = SIDO_FIX.get(t[0], t[0])
    if sido not in SIDOS:
        return None, None
    sgg = None
    if len(t) > 1 and re.search(r"[시군구]$", t[1]):
        sgg = t[1]
        if len(t) > 2 and t[1].endswith("시") and re.search(r"구$", t[2]) and not t[2].endswith("시구"):
            sgg = t[1] + " " + t[2]
    return sido, sgg


def clean_addr(a):
    """'서울특별시 강남구 역삼동 서울특별시 강남구 도곡로 121(…)'처럼 지번 주소 뒤에 도로명 주소가 이어 붙은 경우 도로명 주소만 남긴다."""
    a = re.sub(r"\s+", " ", a or "").strip()
    t = a.split(" ")
    if len(t) > 5 and t[0] in t[1:]:
        i = t.index(t[0], 1)
        if i >= 2:
            return " ".join(t[i:])
    return a


def phone(p):
    p = re.sub(r"[^0-9]", "", p or "")
    if len(p) < 8:
        return ""
    if p.startswith("02"):
        return "02-%s-%s" % (p[2:-4], p[-4:])
    return "%s-%s-%s" % (p[:3], p[3:-4], p[-4:])


def num(x):
    try:
        return int(float(str(x).strip()))
    except Exception:
        return 0


# ───────────────────────── 데이터 준비 ─────────────────────────
def load():
    jj = json.loads(gzip.open(DATA / "jj.json.gz", "rt", encoding="utf-8").read())
    cy = json.loads(gzip.open(DATA / "cy.json.gz", "rt", encoding="utf-8").read())
    links = json.loads((DATA / "yeonbong_links.json").read_text(encoding="utf-8")) if (DATA / "yeonbong_links.json").exists() else {}
    roster = {}
    for fn, kind in (("roster_gigan.csv", "기간산업체"), ("roster_bangsan.csv", "방위산업체")):
        for r in csv.DictReader(open(DATA / fn, encoding="cp949", newline="")):
            r["_kind"] = kind
            roster[norm(r["업체명"])] = r
    jobs = collections.defaultdict(list)
    for p in cy:
        if p.get("saeopjaDrno"):
            jobs[p["saeopjaDrno"]].append(p)
    cs, seen, dedup = [], collections.Counter(), set()
    for x in jj:
        name = unicodedata.normalize("NFKC", x.get("eopcheNm", "")).strip()
        code = x.get("eopjongGbcd", "")
        if not name or code.startswith(("13", "14")):
            continue
        typ = ctype(code)
        if typ is None and "연구" in name:
            typ, code = "researcher", "21501"
        if typ is None or code not in CODE:
            continue
        brn = x.get("saeopjaDrno", "")
        sido, sgg = parse_region(x.get("eopcheAddr"))
        c = dict(name=name, brn=brn, code=code, ind=CODE[code], typ=typ, sido=sido, sgg=sgg, addr=clean_addr(x.get("eopcheAddr", "")),
                 size=SIZE.get(x.get("gegyumoCd", ""), ""), year=num(x.get("seonjeongYy")) or None, tel=phone(x.get("yeonrakcheoNo")),
                 home=(x.get("hmpgAddr") or "").strip(), roster=roster.get(norm(name)), jobs=[], yb=links.get(brn))
        dk = (brn, name, c["addr"])
        if dk in dedup:  # 이름·주소·사업자번호가 완전히 같은 중복 행은 한 번만
            continue
        dedup.add(dk)
        base = brn if brn else "n" + hashlib.md5((name + c["addr"]).encode()).hexdigest()[:8]
        seen[base] += 1
        c["_base"] = base
        cs.append(c)
    for c in cs:
        b = c["_base"]
        c["slug"] = b if seen[b] == 1 else "%s-%s" % (b, hashlib.md5((c["name"] + c["addr"]).encode()).hexdigest()[:4])
        if c["brn"] and c["brn"] in jobs:
            # 같은 사업자번호의 지정업체가 여럿이면 업체명이 일치하는 곳에만 연결
            for p in jobs[c["brn"]]:
                if seen[c["_base"]] == 1 or norm(p.get("eopcheNm")) == norm(c["name"]):
                    c["jobs"].append(p)
    return cs, cy


def fmt_date(d):
    d = (d or "").strip()
    return "%s.%s.%s" % (d[:4], d[4:6], d[6:8]) if re.fullmatch(r"\d{8}", d) else ""


def days_left(d):
    try:
        return (datetime.strptime(d, "%Y%m%d").date() - TODAY).days
    except Exception:
        return None


# ───────────────────────── 렌더 도우미 ─────────────────────────
def cl(c):
    return '<a href="/company/%s/">%s</a>' % (c["slug"], esc(c["name"]))


def tag_row(c):
    t = ['<span class="tag term">%s</span>' % TYPES[c["typ"]][0], '<span class="tag">%s</span>' % esc(c["ind"])]
    if c["size"]:
        t.append('<span class="tag gil">%s</span>' % c["size"])
    if c["jobs"]:
        t.append('<span class="tag hol">채용공고 %d건</span>' % len(c["jobs"]))
    return " ".join(t)


def company_table(rows, cap=300, show_region=True):
    rows = rows[:cap]
    head = "<tr><th>업체명</th><th>업종</th><th>구분</th>%s<th>선정</th><th>비고</th></tr>" % ("<th>소재지</th>" if show_region else "")
    out = []
    for c in rows:
        loc = "<td>%s</td>" % esc(" ".join(x for x in (SHORT.get(c["sido"], c["sido"]) or "", c["sgg"] or "") if x) or "-") if show_region else ""
        note = ('<span class="red">채용 %d건</span>' % len(c["jobs"])) if c["jobs"] else ""
        out.append("<tr><td>%s</td><td>%s</td><td>%s</td>%s<td>%s</td><td>%s</td></tr>" % (
            cl(c), esc(c["ind"]), TYPES[c["typ"]][0], loc, "%d년" % c["year"] if c["year"] else "-", note))
    return '<div class="tbl-wrap"><table class="tbl">%s%s</table></div>' % (head, "".join(out))


def order_key(c):
    return (-len(c["jobs"]), -(c["year"] or 0), c["name"])


def rs(c):
    """지역 문자열"""
    return " ".join(x for x in (c["sido"], c["sgg"]) if x) or ""


def sdo(s):
    return SHORT.get(s, s)


# ───────────────────────── 페이지 ─────────────────────────
def page_company(c, groups):
    typ = TYPES[c["typ"]][0]
    region = rs(c)
    reg_txt = region or "소재지 미상"
    ro = c["roster"]
    sel = ("%d년에 선정됐습니다." % c["year"]) if c["year"] else ""
    same_ind = groups["ind_sgg"].get((c["ind"], c["sido"], c["sgg"]), []) if c["sgg"] else []
    ind_sido = groups["ind_sido"].get((c["ind"], c["sido"]), []) if c["sido"] else []
    # 요약 문단
    parts = ["<b>%s</b>은(는) %s의 <b>%s 병역지정업체</b>(업종 %s)입니다." % (esc(c["name"]), esc(reg_txt), typ, esc(c["ind"]))]
    if c["size"]:
        parts.append("기업 규모는 %s이며 %s" % (c["size"], sel) if sel else "기업 규모는 %s입니다." % c["size"])
    elif sel:
        parts.append(sel)
    if ind_sido and c["year"]:
        older = sum(1 for o in ind_sido if o["year"] and o["year"] < c["year"])
        if older:
            parts.append("%s %s 지정업체 %d곳 중 이 업체보다 일찍 선정된 곳은 %d곳입니다." % (esc(sdo(c["sido"])), esc(c["ind"]), len(ind_sido), older))
        else:
            parts.append("%s %s 지정업체 %d곳 중 가장 먼저 선정된 업체군에 속합니다." % (esc(sdo(c["sido"])), esc(c["ind"]), len(ind_sido)))
    if c["jobs"]:
        parts.append("병역일터에 <b>채용공고 %d건</b>이 등록돼 있습니다." % len(c["jobs"]))
    if ro:
        tot = num(ro.get("배정인원(계)")) or 0
        if tot:
            parts.append("%d년도 산업기능요원 인원배정은 <b>%d명</b>입니다." % (YEAR, tot))
    lead = '<p class="lead">%s</p>' % " ".join(parts)
    # 기본 정보 표
    rows = [("요원 구분", typ), ("업종", c["ind"])]
    if c["size"]:
        rows.append(("기업 규모", c["size"]))
    if c["year"]:
        rows.append(("선정년도", "%d년 (지정 %d년차)" % (c["year"], YEAR - c["year"] + 1)))
    rows.append(("소재지", c["addr"] or "정보 없음"))
    if c["tel"]:
        rows.append(("연락처", c["tel"]))
    if c["home"]:
        h = c["home"] if c["home"].startswith("http") else "http://" + c["home"]
        rows.append(("홈페이지", '<a href="%s" rel="nofollow noopener" target="_blank">%s</a>' % (esc(h), esc(c["home"]))))
    if c["brn"]:
        rows.append(("사업자등록번호", c["brn"][:3] + "-" + c["brn"][3:5] + "-" + c["brn"][5:]))
    if ro:
        rows.append(("관할 지방병무청", ro.get("관할청", "-")))
    tbl = '<div class="tbl-wrap"><table class="tbl">%s</table></div>' % "".join(
        "<tr><th>%s</th><td>%s</td></tr>" % (a, b if a == "홈페이지" else esc(b)) for a, b in rows)
    body = ['<div class="page-head"><h1>%s 병역지정업체 정보</h1><p>%s</p></div>' % (esc(c["name"]), tag_row(c)), lead, ad(),
            '<h2 class="group-title">기본 정보</h2>', tbl]
    # 인원배정
    if ro:
        cols = [("06년생 이전 3자협약 등", "06년생 이전 3자협약"), ("06년생 이전 2자협약 등", "06년생 이전 2자협약"), ("07년생 3자협약 등", "07년생 3자협약"),
                ("별도배정(소계)", "별도배정(소계)")]
        trs = "".join("<tr><th>%s</th><td>%s명</td></tr>" % (lab, num(ro.get(k))) for k, lab in cols if num(ro.get(k)))
        body.append('<h2 class="group-title">%d년도 산업기능요원 인원배정 <small>병무청 인원배정 명부(%s)</small></h2>' % (YEAR, ro["_kind"]))
        body.append('<div class="tbl-wrap"><table class="tbl"><tr><th>배정인원(계)</th><td><b>%s명</b></td></tr>%s</table></div>' % (num(ro.get("배정인원(계)")), trs))
        body.append('<p class="note">인원배정 명부는 연 1회 공개되는 자료입니다. 배정 인원이 있어도 실제 채용 여부는 업체마다 다르니 채용공고를 확인하세요.</p>')
    # 채용공고
    if c["jobs"]:
        body.append('<h2 class="group-title">병역일터 채용공고 <small>%d건</small></h2>' % len(c["jobs"]))
        for p in c["jobs"]:
            dl = days_left(p.get("magamDt"))
            dtxt = ("마감 %s" % fmt_date(p.get("magamDt"))) + (" (D-%d)" % dl if dl is not None and dl >= 0 else "") if p.get("magamDt") else ""
            li = [("모집 요원", "%s(%s)" % (p.get("yowonGbcdNm", ""), p.get("yeokjongBrcdNm", "")) if p.get("yeokjongBrcdNm") else p.get("yowonGbcdNm", "")),
                  ("모집 인원", p.get("mjinwonNm")), ("담당 업무", p.get("ddeopmuNm")), ("근무지", p.get("geunmujy") or p.get("geunmujysido")),
                  ("연봉 구간", p.get("gyjogeonCdNm")), ("학력", p.get("cjhakryeok")), ("경력", p.get("gyeongryeokGbcdNm")), ("근무형태", p.get("gmhyeongtaeNm")),
                  ("복리후생", p.get("bokrihs")), ("접수 방법", p.get("jeopsubb")), ("마감", dtxt)]
            trs = "".join("<tr><th>%s</th><td>%s</td></tr>" % (a, esc(b)) for a, b in li if b)
            body.append('<h3>%s</h3><div class="tbl-wrap"><table class="tbl">%s</table></div>' % (esc(p.get("cyjemokNm", "채용공고")), trs))
        body.append('<p class="note">채용공고는 병역일터에 등록된 시점의 정보입니다. 접수 마감·변경은 병역일터(work.mma.go.kr)에서 확인하세요.</p>')
    # 우아연봉
    if c["yb"]:
        body.append('<div class="note-box">💰 이 회사의 국민연금 가입자 수와 추정 평균연봉은 <a href="https://wooayeonbong.wooahouse.com/company/%s/">우아연봉 %s 페이지</a>에서 볼 수 있습니다.</div>' % (q(c["yb"]), esc(c["name"])))
    # 같은 동네·업종
    sib = [o for o in same_ind if o is not c][:8]
    if sib:
        body.append('<h2 class="group-title">같은 지역 같은 업종 <small>%s %s</small></h2>' % (esc(region), esc(c["ind"])))
        body.append(company_table(sib, show_region=False))
    nav = []
    if c["sido"] and len(ind_sido) >= 3:
        nav.append('<a class="chip" href="/industry/%s/%s/">%s %s 지정업체 전체 (%d곳)</a>' % (q(c["ind"]), q(c["sido"]), esc(sdo(c["sido"])), esc(c["ind"]), len(ind_sido)))
    nav.append('<a class="chip" href="/industry/%s/">%s 지정업체 전국</a>' % (q(c["ind"]), esc(c["ind"])))
    if c["sido"] and c["sgg"] and groups["sgg_n"].get((c["sido"], c["sgg"]), 0) >= 2:
        nav.append('<a class="chip" href="/region/%s/%s/">%s 지정업체</a>' % (q(c["sido"]), q(c["sgg"]), esc(region)))
    elif c["sido"]:
        nav.append('<a class="chip" href="/region/%s/">%s 지정업체</a>' % (q(c["sido"]), esc(c["sido"])))
    body.append('<div class="chips">%s</div>' % "".join(nav))
    # FAQ
    faq = [("%s은(는) 어떤 병역지정업체인가요?" % c["name"],
            "%s은(는) %s의 %s 병역지정업체이며 업종은 %s입니다.%s" % (c["name"], reg_txt, typ, c["ind"], (" " + sel) if sel else "")),
           ("%s에서 %s으로(로) 복무하려면 어떻게 해야 하나요?" % (c["name"], typ),
            "%s 복무는 지정업체에 채용된 뒤 병무청의 편입 절차를 거쳐야 하며, 편입 요건과 가능 여부는 병무청이 판단합니다. 병역일터(work.mma.go.kr)의 안내와 관할 지방병무청 문의로 최신 요건을 확인하세요." % typ),
           ("이 정보는 최신인가요?",
            "병무청이 공공데이터포털에 공개하는 지정업체 정보를 매일 받아 정리합니다. 다만 지정 취소·변경이 늦게 반영될 수 있어, 지원 전 병역일터나 업체에 직접 확인하는 것이 안전합니다.")]
    if c["jobs"]:
        faq.insert(1, ("%s 채용공고는 어디서 지원하나요?" % c["name"], "병역일터에 등록된 공고 기준이며 접수 방법은 각 공고의 '접수 방법'에 적혀 있습니다. 마감일은 %s입니다." % (fmt_date(c["jobs"][0].get("magamDt")) or "공고별로 다름")))
    crumbs = [("홈", "/")] + ([(TYPES[c["typ"]][0], "/type/%s/" % c["typ"])]) + [(c["name"], "/company/%s/" % c["slug"])]
    ld = [{"@context": "https://schema.org", "@type": "Organization", "name": c["name"], "address": c["addr"], **({"telephone": c["tel"]} if c["tel"] else {}),
           **({"url": c["home"] if c["home"].startswith("http") else "http://" + c["home"]} if c["home"] else {})}]
    title = "%s 병역지정업체 - %s %s" % (c["name"], c["ind"], sdo(c["sido"]) if c["sido"] else "")
    if groups["dup_title"].get((c["name"], c["ind"], c["sido"]), 0) > 1:  # 같은 이름·업종·시도의 업체는 시군구(또는 사업자번호 끝자리)로 구분
        lab = c["sgg"] or ""
        if groups["dup_title2"].get((c["name"], c["ind"], c["sido"], c["sgg"]), 0) > 1 or not lab:  # 시군구까지 같으면 사업자번호 끝자리로 구분
            lab = (lab + " " if lab else "") + "사업자 " + (c["slug"].rsplit("-", 1)[-1] if "-" in c["slug"] else (c["brn"][-4:] or c["slug"][-4:]))
        title = "%s(%s) 병역지정업체 - %s %s" % (c["name"], lab, c["ind"], sdo(c["sido"]) if c["sido"] else "")
    desc = "%s은(는) %s의 %s 병역지정업체(%s)입니다. %s연락처·홈페이지%s를 확인하세요." % (
        c["name"], reg_txt, typ, c["ind"], ("%d년 선정. " % c["year"]) if c["year"] else "", "·채용공고" if c["jobs"] else "")
    write("/company/%s/" % c["slug"], layout("/company/%s/" % c["slug"], title.strip(), desc, "\n".join(body), faq, crumbs, "article", ld, coupang=bool(c["jobs"])), "0.6")


def hub_text(label, cs):
    n = len(cs)
    ts = collections.Counter(TYPES[c["typ"]][0] for c in cs)
    jobs = sum(len(c["jobs"]) for c in cs)
    yrs = [c["year"] for c in cs if c["year"]]
    s = "%s 병역지정업체는 현재 <b>%d곳</b>입니다." % (esc(label), n)
    if len(ts) > 1:
        s += " 요원 구분별로는 %s입니다." % ", ".join("%s %d곳" % (k, v) for k, v in ts.most_common())
    if yrs:
        s += " 선정년도는 %d년부터 %d년까지이고, 최근 3년(%d~%d년) 사이 새로 선정된 곳이 %d곳입니다." % (min(yrs), max(yrs), YEAR - 2, YEAR, sum(1 for y in yrs if y >= YEAR - 2))
    if jobs:
        s += " 이 중 병역일터에 채용공고를 올린 업체가 있어 공고 <b>%d건</b>이 확인됩니다." % jobs
    return '<p class="lead">%s</p>' % s


def breakdown(cs, key, base, label_fn=lambda k: k, cap=60, extra="", ok=None):
    """칩 목록. ok(k)가 False면(해당 허브 페이지가 없으면) 링크 없이 표시만 한다."""
    cnt = collections.Counter(key(c) for c in cs if key(c))
    chips = "".join(('<a class="chip" href="%s%s/%s">%s <small>%d</small></a>' % (base, q(k), extra, esc(label_fn(k)), v)) if (ok is None or ok(k))
                    else '<span class="chip">%s <small>%d</small></span>' % (esc(label_fn(k)), v) for k, v in cnt.most_common(cap))
    return '<div class="chips">%s</div>' % chips


def build():
    cs, cy = load()
    print("업체", len(cs), "채용공고", len(cy))
    groups = {"ind_sgg": collections.defaultdict(list), "ind_sido": collections.defaultdict(list)}
    by_sido, by_sgg, by_ind, by_typ = collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list)
    for c in cs:
        by_ind[c["ind"]].append(c)
        by_typ[c["typ"]].append(c)
        if c["sido"]:
            by_sido[c["sido"]].append(c)
            groups["ind_sido"][(c["ind"], c["sido"])].append(c)
            if c["sgg"]:
                by_sgg[(c["sido"], c["sgg"])].append(c)
                groups["ind_sgg"][(c["ind"], c["sido"], c["sgg"])].append(c)
    groups["sgg_n"] = {k: len(v) for k, v in by_sgg.items()}
    groups["dup_title"] = collections.Counter((c["name"], c["ind"], c["sido"]) for c in cs)
    groups["dup_title2"] = collections.Counter((c["name"], c["ind"], c["sido"], c["sgg"]) for c in cs)
    for L in list(by_sido.values()) + list(by_sgg.values()) + list(by_ind.values()) + list(by_typ.values()) + list(groups["ind_sido"].values()) + list(groups["ind_sgg"].values()):
        L.sort(key=order_key)
    # _site 폴더 자체는 두고 내용만 비운다(다른 프로세스가 폴더를 붙잡고 있어도 빌드가 실패하지 않도록)
    OUT.mkdir(parents=True, exist_ok=True)
    for ch in OUT.iterdir():
        shutil.rmtree(ch) if ch.is_dir() else ch.unlink()
    for c in cs:
        page_company(c, groups)
    n_jobs = sum(1 for c in cs if c["jobs"])
    total_alloc = sum(num(c["roster"].get("배정인원(계)")) for c in cs if c["roster"])
    # 업종 허브
    for ind, L in by_ind.items():
        typ = L[0]["typ"]
        body = ['<div class="page-head"><h1>%s 병역지정업체 %d곳</h1><p>%s · 전국 업체 목록</p></div>' % (esc(ind), len(L), TYPES[typ][0]), hub_text("%s" % ind, L), ad(),
                '<h2 class="group-title">시도별</h2>', breakdown(L, lambda c: c["sido"], "/industry/%s/" % q(ind), lambda k: sdo(k), ok=lambda k: len(groups["ind_sido"].get((ind, k), [])) >= 3),
                '<h2 class="group-title">업체 목록 <small>채용공고 있는 곳·최근 선정 순</small></h2>', company_table(L, 300)]
        if len(L) > 300:
            body.append('<p class="note">업체가 많아 상위 300곳만 표시했습니다. 시도별 페이지에서 전체를 볼 수 있습니다.</p>')
        faq = [("%s 병역지정업체는 몇 곳인가요?" % ind, "공공데이터 기준 전국 %d곳입니다(요원 구분: %s)." % (len(L), TYPES[typ][0])),
               ("%s 업종 병역지정업체를 어떻게 찾나요?" % ind, "이 페이지에서 시도를 고르거나 홈의 검색창에 업체명을 입력하세요. 채용 중인 업체는 병역일터 채용공고에서도 확인할 수 있습니다.")]
        write("/industry/%s/" % ind, layout("/industry/%s/" % ind, "%s 병역지정업체 목록 (전국 %d곳)" % (ind, len(L)), "%s 업종 %s 병역지정업체 %d곳의 지역·선정년도·채용공고를 정리했습니다." % (ind, TYPES[typ][0], len(L)), "\n".join(body), faq,
                                            [("홈", "/"), (TYPES[typ][0], "/type/%s/" % typ), (ind, "/industry/%s/" % ind)]), "0.7")
    for (ind, sido), L in groups["ind_sido"].items():
        if len(L) < 3:
            continue
        typ = L[0]["typ"]
        sgg_cnt = collections.Counter(c["sgg"] for c in L if c["sgg"])
        body = ['<div class="page-head"><h1>%s %s 병역지정업체 %d곳</h1><p>%s</p></div>' % (esc(sido), esc(ind), len(L), TYPES[typ][0]), hub_text("%s %s" % (sdo(sido), ind), L), ad(),
                '<h2 class="group-title">시군구별</h2><div class="chips">%s</div>' % "".join('<span class="chip">%s <small>%d</small></span>' % (esc(k), v) for k, v in sgg_cnt.most_common(40)),
                '<h2 class="group-title">업체 목록</h2>', company_table(L, 400)]
        faq = [("%s %s 병역지정업체는 몇 곳인가요?" % (sdo(sido), ind), "공공데이터 기준 %d곳입니다." % len(L))]
        write("/industry/%s/%s/" % (ind, sido), layout("/industry/%s/%s/" % (ind, sido), "%s %s 병역지정업체 %d곳" % (sdo(sido), ind, len(L)), "%s %s 업종 병역지정업체 %d곳의 시군구별 분포와 업체 목록, 채용공고 현황입니다." % (sido, ind, len(L)), "\n".join(body), faq,
                                                     [("홈", "/"), (ind, "/industry/%s/" % ind), (sdo(sido), "/industry/%s/%s/" % (ind, sido))]), "0.6")
    # 지역 허브
    for sido, L in by_sido.items():
        sg = collections.Counter(c["sgg"] for c in L if c["sgg"])
        body = ['<div class="page-head"><h1>%s 병역지정업체 %d곳</h1><p>산업기능요원·전문연구요원·승선근무예비역</p></div>' % (esc(sido), len(L)), hub_text(sido, L), ad(),
                '<h2 class="group-title">시군구별</h2><div class="chips">%s</div>' % "".join(('<a class="chip" href="/region/%s/%s/">%s <small>%d</small></a>' % (q(sido), q(k), esc(k), v)) if v >= 2 else '<span class="chip">%s <small>%d</small></span>' % (esc(k), v) for k, v in sg.most_common(80)),
                '<h2 class="group-title">업종별</h2>', breakdown(L, lambda c: c["ind"], "/industry/", cap=40, extra="%s/" % q(sido), ok=lambda k: len(groups["ind_sido"].get((k, sido), [])) >= 3),
                '<h2 class="group-title">업체 목록 <small>채용공고 있는 곳·최근 선정 순</small></h2>', company_table(L, 200)]
        faq = [("%s에는 병역지정업체가 몇 곳 있나요?" % sido, "공공데이터 기준 %d곳이며 업종별·시군구별로 나눠 볼 수 있습니다." % len(L))]
        write("/region/%s/" % sido, layout("/region/%s/" % sido, "%s 병역지정업체 %d곳 (산업기능요원·전문연구요원)" % (sdo(sido), len(L)), "%s의 병역지정업체 %d곳을 업종·시군구별로 정리했습니다. 채용공고와 선정년도를 확인하세요." % (sido, len(L)), "\n".join(body), faq,
                                           [("홈", "/"), (sido, "/region/%s/" % sido)]), "0.7")
    for (sido, sgg), L in by_sgg.items():
        if len(L) < 2:
            continue
        body = ['<div class="page-head"><h1>%s %s 병역지정업체 %d곳</h1></div>' % (esc(sido), esc(sgg), len(L)), hub_text("%s %s" % (sido, sgg), L), ad(),
                '<h2 class="group-title">업종별</h2>', breakdown(L, lambda c: c["ind"], "/industry/", cap=30, extra="%s/" % q(sido), ok=lambda k: len(groups["ind_sido"].get((k, sido), [])) >= 3),
                '<h2 class="group-title">업체 목록</h2>', company_table(L, 300, show_region=False)]
        faq = [("%s %s에 병역지정업체가 몇 곳 있나요?" % (sdo(sido), sgg), "공공데이터 기준 %d곳입니다." % len(L))]
        write("/region/%s/%s/" % (sido, sgg), layout("/region/%s/%s/" % (sido, sgg), "%s %s 병역지정업체 %d곳" % (sdo(sido), sgg, len(L)), "%s %s의 산업기능요원·전문연구요원 병역지정업체 %d곳과 채용공고를 정리했습니다." % (sido, sgg, len(L)), "\n".join(body), faq,
                                                    [("홈", "/"), (sido, "/region/%s/" % sido), (sgg, "/region/%s/%s/" % (sido, sgg))]), "0.6")
    # 요원 구분 허브
    for typ, (label, icon, desc) in TYPES.items():
        L = by_typ[typ]
        body = ['<div class="page-head"><h1>%s %s 병역지정업체 %d곳</h1><p>%s</p></div>' % (icon, label, len(L), desc), hub_text(label, L), ad(),
                '<h2 class="group-title">업종별</h2>', breakdown(L, lambda c: c["ind"], "/industry/", cap=40),
                '<h2 class="group-title">지역별</h2>', breakdown(L, lambda c: c["sido"], "/region/", lambda k: sdo(k)),
                '<h2 class="group-title">채용공고가 있는 업체</h2>', company_table([c for c in L if c["jobs"]], 120) if any(c["jobs"] for c in L) else '<p class="note">현재 병역일터에 올라온 채용공고가 있는 업체가 없습니다.</p>']
        faq = [("%s은(는) 어떤 제도인가요?" % label, "%s입니다. 편입 요건·복무 기간 등 최신 기준은 병무청 병역일터에서 확인하세요." % desc)]
        write("/type/%s/" % typ, layout("/type/%s/" % typ, "%s 병역지정업체 목록 (%d곳)" % (label, len(L)), "%s 병역지정업체 %d곳을 업종·지역별로 정리했습니다." % (label, len(L)), "\n".join(body), faq, [("홈", "/"), (label, "/type/%s/" % typ)]), "0.8")
    # 채용공고
    jc = [c for c in cs if c["jobs"]]
    jobs_all = sorted(((c, p) for c in jc for p in c["jobs"]), key=lambda t: t[1].get("magamDt", "99999999"))
    trs = []
    for c, p in jobs_all:
        dl = days_left(p.get("magamDt"))
        trs.append("<tr><td>%s<br><small>%s</small></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            cl(c), esc(p.get("cyjemokNm", "")), esc(p.get("yowonGbcdNm", "")), esc(p.get("geunmujysido", "") or ""), esc(p.get("gyjogeonCdNm", "") or "-"),
            esc(p.get("mjinwonNm", "") or "-"), esc(fmt_date(p.get("magamDt"))) + (" (D-%d)" % dl if dl is not None and dl >= 0 else "")))
    body = ['<div class="page-head"><h1>병역일터 채용공고 %d건</h1><p>산업기능요원·전문연구요원 모집 중인 병역지정업체</p></div>' % len(jobs_all),
            '<p class="lead">병무청 병역일터에 등록된 채용공고 <b>%d건</b>(업체 %d곳)을 마감이 가까운 순으로 정리했습니다. 업체명을 누르면 지정업체 정보와 공고 상세를 볼 수 있습니다.</p>' % (len(jobs_all), len(jc)), ad(),
            '<div class="tbl-wrap"><table class="tbl"><tr><th>업체 / 공고</th><th>요원</th><th>근무지</th><th>연봉 구간</th><th>인원</th><th>마감</th></tr>%s</table></div>' % "".join(trs),
            '<p class="note">공고는 병역일터 등록 시점의 정보이며 접수 마감·변경은 병역일터에서 확인하세요.</p>']
    faq = [("병역일터 채용공고는 어디서 확인하나요?", "병무청 병역일터(work.mma.go.kr)에서 업종·지역별로 검색할 수 있고, 이 페이지는 같은 공고를 지정업체 정보와 함께 정리한 것입니다.")]
    write("/jobs/", layout("/jobs/", "병역일터 채용공고 %d건 - 산업기능요원·전문연구요원 모집" % len(jobs_all), "병무청 병역일터의 산업기능요원·전문연구요원 채용공고 %d건을 마감순으로 정리했습니다." % len(jobs_all), "\n".join(body), faq, [("홈", "/"), ("채용공고", "/jobs/")], coupang=True), "0.9")
    # 랭킹: 2026 배정
    top = sorted((c for c in cs if c["roster"] and num(c["roster"].get("배정인원(계)"))), key=lambda c: (-num(c["roster"]["배정인원(계)"]), c["name"]))
    if top:
        trs = "".join("<tr><td>%d</td><td>%s</td><td>%s</td><td>%s</td><td><b>%d명</b></td></tr>" % (i + 1, cl(c), esc(c["ind"]), esc(sdo(c["sido"]) if c["sido"] else "-"), num(c["roster"]["배정인원(계)"])) for i, c in enumerate(top[:100]))
        body = ['<div class="page-head"><h1>%d년도 산업기능요원 인원배정 상위 업체</h1><p>병무청 인원배정 명부 기준 배정인원 순위</p></div>' % YEAR,
                '<p class="lead">병무청이 공개한 %d년도 산업기능요원 인원배정 명부에는 <b>%d개 업체, 총 %s명</b>의 배정이 기록돼 있습니다. 배정인원이 많은 상위 100곳입니다.</p>' % (YEAR, len(top), "{:,}".format(total_alloc)), ad(),
                '<div class="tbl-wrap"><table class="tbl"><tr><th>순위</th><th>업체</th><th>업종</th><th>시도</th><th>배정</th></tr>%s</table></div>' % trs]
        write("/rank/allocation/", layout("/rank/allocation/", "%d년 산업기능요원 인원배정 상위 업체" % YEAR, "병무청 %d년도 산업기능요원 인원배정 명부 기준 배정인원 상위 100개 업체입니다." % YEAR, "\n".join(body), None, [("홈", "/"), ("인원배정 순위", "/rank/allocation/")]), "0.7")
    # 홈
    cnt_t = {t: len(by_typ[t]) for t in TYPES}
    cards = "".join('<a class="card" href="/type/%s/"><b>%s %s</b><span>%d곳 · %s</span></a>' % (t, TYPES[t][1], TYPES[t][0], cnt_t[t], esc(TYPES[t][2])) for t in TYPES)
    latest = sorted(jobs_all, key=lambda t: t[1].get("ccdatabalsaengDtm", ""), reverse=True)[:10]
    body = ['<div class="hero"><h1>병역지정업체 찾기</h1><p>산업기능요원·전문연구요원·승선근무예비역 지정업체 %s곳의 소재지·업종·선정년도·채용공고를 한 번에</p>'
            '<div class="today-box"><div><small>지정업체</small><b>%s곳</b></div><div><small>채용공고</small><b>%d건</b></div><div><small>%d 인원배정</small><b>%s명</b></div></div></div>' % (
                "{:,}".format(len(cs)), "{:,}".format(len(cs)), len(jobs_all), YEAR, "{:,}".format(total_alloc)),
            '<div class="search-box"><input id="q" type="search" placeholder="업체명 검색 (예: 삼성, 정보처리, 판교)" autocomplete="off"><div id="sr" class="sr-list"></div></div>',
            ad(), '<div class="card-grid">%s</div>' % cards,
            '<h2 class="group-title">최근 등록된 채용공고</h2>', '<div class="tbl-wrap"><table class="tbl"><tr><th>업체</th><th>요원</th><th>근무지</th><th>마감</th></tr>%s</table></div>' % "".join(
                "<tr><td>%s<br><small>%s</small></td><td>%s</td><td>%s</td><td>%s</td></tr>" % (cl(c), esc(p.get("cyjemokNm", "")), esc(p.get("yowonGbcdNm", "")), esc(p.get("geunmujysido", "") or ""), esc(fmt_date(p.get("magamDt")))) for c, p in latest),
            '<p><a class="btn" href="/jobs/">채용공고 전체 %d건 보기</a> <a class="btn" href="/rank/allocation/">%d년 인원배정 순위</a></p>' % (len(jobs_all), YEAR),
            '<h2 class="group-title">업종별</h2>', breakdown(cs, lambda c: c["ind"], "/industry/", cap=45),
            '<h2 class="group-title">지역별</h2>', breakdown(cs, lambda c: c["sido"], "/region/", lambda k: sdo(k)),
            '<script src="/assets/js/search.js"></script>']
    faq = [("병역지정업체란 무엇인가요?", "병무청장이 지정한 업체(연구기관)에서 일정 기간 근무하면 병역을 이행한 것으로 인정하는 제도의 근무처입니다. 산업기능요원(제조·정보처리 등), 전문연구요원(기업부설연구소 등), 승선근무예비역(해운·수산)으로 나뉩니다."),
           ("병역지정업체 목록은 어디서 가져왔나요?", "병무청이 공공데이터포털에 공개한 '전문연구/산업기능요원 지정업체 정보'와 '병역일터 채용공고', 산업기능요원 인원배정 명부를 매일 받아 정리했습니다."),
           ("지정업체라고 바로 근무할 수 있나요?", "아닙니다. 지정업체에 채용된 뒤 병무청의 편입 절차를 거쳐야 하고 요건과 가능 여부는 병무청이 판단합니다. 최신 기준은 병역일터와 관할 지방병무청에서 확인하세요.")]
    ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": "우아병역", "url": BASE + "/", "potentialAction": {"@type": "SearchAction", "target": BASE + "/?q={q}", "query-input": "required name=q"}}]
    write("/", layout("/", "병역지정업체 찾기 - 산업기능요원·전문연구요원 지정업체 %s곳 | 우아병역" % "{:,}".format(len(cs)), "산업기능요원·전문연구요원·승선근무예비역 병역지정업체 %s곳을 업종·지역별로 찾고 병역일터 채용공고와 %d년 인원배정을 확인하세요." % ("{:,}".format(len(cs)), YEAR), "\n".join(body), faq, None, "website", ld), "1.0")
    # 검색 인덱스
    idx = [[c["name"], c["slug"], c["ind"], (sdo(c["sido"]) + " " + (c["sgg"] or "")).strip() if c["sido"] else "", 1 if c["jobs"] else 0] for c in sorted(cs, key=order_key)]
    (OUT / "search_index.json").write_text(json.dumps(idx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    pages_static(cs, len(jobs_all), total_alloc)
    finish()


def pages_static(cs, njobs, total_alloc):
    G = [("/guide/", "이용 안내 — 병역지정업체 확인 방법")]
    body = ['<div class="page-head"><h1>병역지정업체 확인 방법과 이용 안내</h1><p>산업기능요원·전문연구요원·승선근무예비역을 준비한다면</p></div>', ad(),
            '<h2 class="group-title">1. 병역지정업체란</h2><p class="lead">병역지정업체는 병무청장이 지정해 <b>산업기능요원·전문연구요원·승선근무예비역</b>이 근무할 수 있는 업체(연구기관)입니다. 산업기능요원은 제조업·정보처리 등, 전문연구요원은 기업부설연구소 등, 승선근무예비역은 해운업·수산업 업체가 해당합니다. 업체는 기업별·업종별·소재지별로 검색할 수 있으며, 지정 사유가 사라지면 취소되기도 하고 매년 병무청 고시에 따라 신규 선정을 신청할 수도 있습니다.</p>',
            '<h2 class="group-title">2. 지정업체를 고르는 순서</h2><ol class="lead"><li>이 사이트의 <a href="/">검색</a>이나 <a href="/industry/정보처리/">업종별 목록</a>으로 후보 업체를 좁힙니다.</li><li>업체 상세의 <b>선정년도</b>, <b>채용공고</b>, <b>인원배정</b>을 확인합니다.</li><li>병무청 병역일터에서 지정 상태와 최신 공고를 다시 확인합니다.</li><li>업체에 직접 문의해 채용 계획과 편입 절차를 확인합니다.</li></ol>',
            '<h2 class="group-title">3. 이 사이트의 정보 읽는 법</h2><ul class="lead"><li><b>선정년도</b>: 지정업체로 선정된 해입니다. 오래될수록 지정 이력이 긴 업체입니다.</li><li><b>채용공고</b>: 병역일터에 등록된 공고가 있는 업체에만 표시됩니다. 없다고 채용하지 않는 것은 아닙니다.</li><li><b>인원배정</b>: 병무청이 공개한 산업기능요원 인원배정 명부 기준입니다(연 1회). 기간산업체·방위산업체만 있고 전문연구요원 업체는 포함되지 않습니다.</li></ul>',
            '<h2 class="group-title">4. 꼭 알아둘 점</h2><div class="note-box">편입 요건·복무 기간·가능 여부는 법령과 병무청 고시에 따라 바뀌고, 개인별 판단은 병무청이 합니다. 이 사이트는 공개된 업체 정보를 정리한 참고용이며 병무청의 공식 안내를 대신하지 않습니다.</div>']
    faq = [("지정업체 목록에 있는 곳이면 모두 채용 중인가요?", "아닙니다. 지정업체는 지정 사실을 뜻하며 채용 여부는 업체마다 다릅니다. 채용공고는 병역일터에서 확인하세요."),
           ("지정이 취소된 업체도 목록에 남아 있나요?", "공공데이터에 반영되는 시점에 따라 취소가 늦게 반영될 수 있습니다. 지원 전 병역일터에서 지정 상태를 확인하세요.")]
    write("/guide/", layout("/guide/", "병역지정업체 확인 방법과 이용 안내", "산업기능요원·전문연구요원 병역지정업체를 고르고 확인하는 순서와 이 사이트 정보를 읽는 법을 정리했습니다.", "\n".join(body), faq, [("홈", "/"), ("이용 안내", "/guide/")]), "0.7")
    body = ['<div class="page-head"><h1>데이터 설명</h1></div>',
            '<p class="lead">우아병역은 병무청이 공공데이터포털에 공개한 자료를 매일 받아 정리합니다.</p><ul class="lead">'
            '<li><b>병무청_전문연구/산업기능요원 지정업체 정보</b> (data.go.kr 3066759): 업체명·업종·소재지·선정년도·연락처·사업자번호. 현재 <b>%s</b>건 중 농어민후계자·기능특기자 등 업체가 아닌 항목을 제외한 <b>%s</b>곳을 게시합니다.</li>'
            '<li><b>병무청 병역일터 채용공고</b> (data.go.kr 3065599): 지정업체 채용공고 %d건. 사업자번호로 지정업체와 연결합니다.</li>'
            '<li><b>병무청_산업기능요원 인원배정 명부</b> (data.go.kr 3068267): %d년도 기간산업체·방위산업체 배정 결과(연 1회).</li></ul>'
            '<p class="lead">업종 구분은 병무청 업종코드를 채용공고·인원배정 명부의 업종명과 업체명으로 대조해 정리한 것이라 공식 분류와 표기가 다를 수 있습니다. 지정 취소·변경은 반영이 늦을 수 있습니다.</p>' % ("{:,}".format(len(cs) + 0), "{:,}".format(len(cs)), njobs, YEAR)]
    write("/about/", layout("/about/", "데이터 설명", "우아병역이 사용하는 병무청 공공데이터와 정리 방법을 설명합니다.", "\n".join(body), None, [("홈", "/"), ("데이터 설명", "/about/")]), "0.3")
    body = ['<div class="page-head"><h1>개인정보처리방침</h1></div>', '<p class="lead">우아병역은 회원가입·로그인 없이 이용하며 이용자의 개인정보를 수집하지 않습니다. 사이트 개선을 위해 Google Analytics가 익명 방문 통계를 수집하고, Google AdSense와 쿠팡 파트너스가 광고를 표시하면서 쿠키를 사용할 수 있습니다. 이 사이트에 게시된 업체 정보는 공공데이터포털에 공개된 자료입니다.</p>']
    write("/privacy/", layout("/privacy/", "개인정보처리방침", "우아병역 개인정보처리방침", "\n".join(body), None, [("홈", "/"), ("개인정보처리방침", "/privacy/")]), sitemap=False)


def finish():
    shutil.copytree(ROOT / "assets", OUT / "assets")
    for nf in ROOT.glob("naver*.html"):
        shutil.copy(nf, OUT / nf.name)
    today = TODAY.isoformat()
    urls = "".join("<url><loc>%s%s</loc><lastmod>%s</lastmod><priority>%s</priority></url>" % (BASE, q(p), today, pr) for p, pr in WRITTEN)
    (OUT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</urlset>\n' % urls, encoding="utf-8")
    (OUT / "robots.txt").write_text("User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % BASE, encoding="utf-8")
    (OUT / "CNAME").write_text("wooabyung.wooahouse.com\n", encoding="utf-8")
    nf = layout("/404.html", "페이지를 찾을 수 없습니다", "요청한 페이지를 찾을 수 없습니다.", '<div class="page-head"><h1>페이지를 찾을 수 없습니다</h1></div><div class="chips"><a class="chip" href="/">홈</a><a class="chip" href="/jobs/">채용공고</a></div>', None, None, noindex=True)
    (OUT / "404.html").write_text(nf, encoding="utf-8")
    print("페이지", len(WRITTEN), "(sitemap)")


if __name__ == "__main__":
    build()
