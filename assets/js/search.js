/* 우아병역 — 업체명·업종·지역 검색 (search_index.json: [이름, slug, 업종, 지역, 채용공고있음]) */
(function () {
  var input = document.getElementById('q'), box = document.getElementById('sr');
  if (!input || !box) return;
  var data = null, loading = false;
  function load(cb) {
    if (data) return cb();
    if (loading) return;
    loading = true;
    fetch('/search_index.json').then(function (r) { return r.json(); }).then(function (j) { data = j; cb(); }).catch(function () { loading = false; });
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function render() {
    var q = input.value.trim().toLowerCase();
    if (!q) { box.style.display = 'none'; return; }
    var terms = q.split(/\s+/), out = [];
    for (var i = 0; i < data.length && out.length < 12; i++) {
      var d = data[i], hay = (d[0] + ' ' + d[2] + ' ' + d[3]).toLowerCase(), ok = true;
      for (var t = 0; t < terms.length; t++) if (hay.indexOf(terms[t]) < 0) { ok = false; break; }
      if (ok) out.push(d);
    }
    if (!out.length) { box.innerHTML = '<div style="padding:12px 16px;color:#6B7280;font-size:.9rem">검색 결과가 없습니다.</div>'; box.style.display = 'block'; return; }
    box.innerHTML = out.map(function (d) {
      return '<a href="/company/' + encodeURI(d[1]) + '/" style="display:block;padding:10px 16px;border-bottom:1px solid #F3F4F6;color:#1F2937">' +
        '<b>' + esc(d[0]) + '</b> <span style="font-size:.8rem;color:#6B7280">' + esc(d[2]) + (d[3] ? ' · ' + esc(d[3]) : '') + (d[4] ? ' · 채용공고' : '') + '</span></a>';
    }).join('');
    box.style.display = 'block';
  }
  input.addEventListener('input', function () { load(render); });
  input.addEventListener('focus', function () { load(function () { if (input.value) render(); }); });
  document.addEventListener('click', function (e) { if (!box.contains(e.target) && e.target !== input) box.style.display = 'none'; });
  var m = /[?&]q=([^&]+)/.exec(location.search);
  if (m) { input.value = decodeURIComponent(m[1].replace(/\+/g, ' ')); load(render); }
})();
