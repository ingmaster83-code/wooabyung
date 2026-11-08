# 우아병역 (wooabyung)

병무청 공공데이터로 만든 병역지정업체 검색 사이트 (Python 정적 생성기). https://wooabyung.wooahouse.com

- 데이터: `3066759` 전문연구/산업기능요원 지정업체 정보(`apis.data.go.kr/1300000/jjEopChe/list2/getjjEopChe`, 약 6.7k행), `3065599` 병역일터 채용공고(`1300000/CyJeongBo/list`, 약 420건, 사업자번호로 지정업체와 연결), `3068267` 산업기능요원 인원배정 명부(연 1회 zip → `data/roster_*.csv`, CP949).
- `scripts/fetch_data.py` — 두 API를 받아 `data/jj.json.gz`, `data/cy.json.gz` 저장. 키는 환경변수 `API_KEY`(Actions 시크릿) 또는 `../hosppass/.env`.
- `scripts/make_yeonbong_links.py` — 우아연봉 회사 페이지와 매칭표(`data/yeonbong_links.json`). 우아연봉을 다시 빌드한 뒤 가끔 수동 실행.
- `scripts/build_site.py` — `_site/` 생성(지정업체 상세·업종·지역·요원구분 허브·채용공고·인원배정 순위·안내). `scripts/check_site.py` — 링크/제목/JSON-LD 점검.
- 업종 코드는 병무청 코드를 채용공고 업종명·명부 업종·업체명 표본으로 정리한 것(`build_site.py`의 `CODE`). 13xxx(농어민후계자·농기계)·14xxx(기능특기자)는 업체가 아니라 제외.
- 새 업종 코드가 나오면 `CODE`에 없어 업체가 조용히 빠진다 → 빌드 로그의 업체 수가 급감하면 확인.
- Actions: 매일 KST 06:30 fetch → build → deploy. 인원배정 명부는 매년 1월경 새로 받아 `data/roster_*.csv`를 교체.
