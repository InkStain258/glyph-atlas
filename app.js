/* 古籍字形查询 —— 纯前端，无框架、无构建
 * 数据：window.GA_LAYERS / window.GA_VARIANTS / window.GA_META[层]
 * 字体：css/<层>.css 里的 @font-face + unicode-range，按需分片下载
 */
(function () {
  'use strict';

  var LAYERS = (window.GA_LAYERS || []).slice();
  var V = window.GA_VARIANTS || { canon: {}, same: {}, related: {} };
  var META = window.GA_META = window.GA_META || {};

  var MAX_INPUT = 400;
  var MAX_VARIANTS = 9;

  var state = {
    enabled: new Set(),
    text: '',
    chars: [],        // 去重后的字，按首次出现顺序
    counts: {},       // 字 -> 在原串里出现次数
    sel: 0,
    layers: {},       // 字 -> { layerId: matchedChar }
    focusLayer: null,
    focusVariant: 0,
    preview: 'ink',   // ink | zhuwen | baiwen
    cellSize: 'm'     // s | m | l —— 字形对照图的大小
  };
  try {
    var cs = localStorage.getItem('ga.cellsize');
    if (cs === 's' || cs === 'm' || cs === 'l') state.cellSize = cs;
  } catch (e) {}

  var $ = function (s, r) { return (r || document).querySelector(s); };
  function el(tag, cls, txt) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt != null) n.textContent = txt;
    return n;
  }

  /* ---------- 层数据 ---------- */
  LAYERS.sort(function (a, b) {
    return (a.era_order - b.era_order) || String(a.name_zh).localeCompare(String(b.name_zh));
  });
  LAYERS.forEach(function (L) { L._hasCache = null; });

  /** 二分查 has 区间，判断该层是否有这个码位 */
  function hasCp(L, cp) {
    var r = L.has;
    if (!r || !r.length) return false;
    var lo = 0, hi = r.length - 1;
    while (lo <= hi) {
      var m = (lo + hi) >> 1;
      if (cp < r[m][0]) hi = m - 1;
      else if (cp > r[m][1]) lo = m + 1;
      else return true;
    }
    return false;
  }

  /** 该字的等价类候选（先用户自己输入的字，再规范字，再同组异体） */
  function candidates(ch) {
    var out = [ch], seen = {};
    seen[ch] = 1;
    var c = V.canon[ch] || ch;
    if (!seen[c]) { seen[c] = 1; out.push(c); }
    var grp = V.same[c] || [];
    for (var i = 0; i < grp.length; i++) {
      if (!seen[grp[i]]) { seen[grp[i]] = 1; out.push(grp[i]); }
    }
    return out;
  }

  /** 在某层里为某字找字形：把同一等价类（简/繁/异体）里该层收过的字**全部并起来**，
   *  返回 [{ch, vi}]，vi 表示该字在本层的第几个写法（0 = 主形走 cmap，>0 = GSUB ss0N）。
   *  这样「说 / 說 / 説」不会各查各的，而是当一个字的多种写法一起列出来——
   *  这正好过滤掉「有的字库按简体收、有的按繁体收」这个干扰因素。找不到返回 null。 */
  function matchIn(L, ch) {
    var cands = candidates(ch), out = [];
    for (var i = 0; i < cands.length; i++) {
      var c = cands[i];
      if (!hasCp(L, c.codePointAt(0))) continue;
      var gi = glyphInfo(L, c);
      for (var k = 0; k < gi.n; k++) out.push({ ch: c, vi: k, src: gi.list[k] || null });
    }
    return out.length ? out : null;
  }

  /* ---------- 资源按需加载 ---------- */
  var cssLoaded = {};
  function ensureCss(id) {
    if (cssLoaded[id]) return;
    cssLoaded[id] = true;
    var l = document.createElement('link');
    l.rel = 'stylesheet';
    l.href = 'css/' + id + '.css';
    l.id = 'css-' + id;
    document.head.appendChild(l);
  }

  var metaLoading = {};
  function loadMeta(id) {
    if (META[id]) return Promise.resolve(META[id]);
    if (metaLoading[id]) return metaLoading[id];
    metaLoading[id] = new Promise(function (res) {
      var s = document.createElement('script');
      s.src = 'data/meta/' + id + '.js';
      s.onload = function () { res(META[id] || {}); };
      s.onerror = function () { res({}); };
      document.head.appendChild(s);
    });
    return metaLoading[id];
  }

  /** 只触发一次：元数据到位后补渲染，不会自激 */
  var metaAsked = {};
  function ensureMeta(id) {
    if (!id || metaAsked[id]) return;
    metaAsked[id] = true;
    if (META[id]) return;
    /* 元数据到位后必须整轮重算：异写条数是算 matchIn 时从 meta 数出来的，
       只重画 renderDetail 会拿着旧的结果（永远 1 种）画。 */
    loadMeta(id).then(function () { render(); });
  }

  function glyphInfo(L, matched) {
    var m = META[L.id] && META[L.id][matched];
    if (!m || !m.length) return { n: 1, list: [] };
    return { n: Math.min(m.length, MAX_VARIANTS), list: m };
  }

  function makeGlyph(L, ch, vi, cls) {
    var s = el('span', cls || 'g', ch);
    s.style.fontFamily = "'" + L.id + "', serif";
    if (vi > 0) s.style.fontFeatureSettings = '"ss0' + vi + '" 1';
    return s;
  }

  /* ---------- 侧栏 ---------- */
  function renderSidebar() {
    var box = $('#layers');
    box.innerHTML = '';
    function isModern(L) { return L.kind === 'modern-font' && L.group !== 'ancient'; }
    var groups = [
      { key: 'ancient', t: '古文字 · 字形源', test: function (L) { return !isModern(L); } },
      { key: 'calligraphy', t: '書法 · 手寫', test: function (L) { return isModern(L) && L.group === 'calligraphy'; } },
      { key: 'print', t: '刻本 · 活字', test: function (L) { return isModern(L) && L.group === 'print'; } },
      { key: 'modern', t: '現代 · 排版', test: function (L) { return isModern(L) && L.group !== 'calligraphy' && L.group !== 'print'; } }
    ];
    groups.forEach(function (g) {
      var list = LAYERS.filter(g.test);
      if (!list.length) return;
      /* 書法组按书体排：楷 → 行 → 草 → 隶 → 魏碑 → 篆 → 其他，同体按名字 */
      if (g.key === 'calligraphy') {
        var RANK = { '楷书': 1, '楷': 1, '行书': 2, '行': 2, '草书': 3, '草': 3, '隶书': 4, '隶': 4, '魏碑': 5, '篆书': 6, '篆': 6 };
        list = list.slice().sort(function (a, b) {
          var ra = RANK[a.style] || 9, rb = RANK[b.style] || 9;
          return ra !== rb ? ra - rb : (a.name_zh || '').localeCompare(b.name_zh || '', 'zh');
        });
      }
      box.appendChild(el('div', 'grp', g.t));
      list.forEach(function (L) {
        var row = el('div', 'lay' + (state.enabled.has(L.id) ? ' on' : ''));
        row.dataset.id = L.id;
        row.appendChild(el('span', 'box'));
        row.appendChild(el('span', 'nm', L.name_zh));
        var ct = el('span', 'ct', formatCount(L.chars));
        row.appendChild(ct);
        row.title = L.name_zh + '｜' + (L.era || '') + '｜' + formatCount(L.chars) + ' 字｜' + (L.license || '');
        row.onclick = function () {
          if (state.enabled.has(L.id)) state.enabled.delete(L.id);
          else { state.enabled.add(L.id); ensureCss(L.id); }
          renderSidebar(); render();
        };
        box.appendChild(row);
      });
    });
    var stc = $('#stcount');
    if (stc) stc.textContent = state.enabled.size + ' / ' + LAYERS.length;
  }

  function formatCount(n) {
    if (n >= 10000) return (n / 10000).toFixed(1) + '万';
    return String(n);
  }

  /* ---------- 主区 ---------- */
  function currentChar() { return state.chars[state.sel] || null; }

  function computeMatches() {
    state.layers = {};
    state.chars.forEach(function (ch) {
      var hit = {};
      LAYERS.forEach(function (L) {
        if (!state.enabled.has(L.id)) return;
        var m = matchIn(L, ch);
        if (m) hit[L.id] = m;
      });
      state.layers[ch] = hit;
    });
  }

  function enabledLayers() {
    return LAYERS.filter(function (L) { return state.enabled.has(L.id); });
  }

  function render() {
    computeMatches();
    renderChips();
    renderDetail();
    renderMatrix();
  }

  function renderChips() {
    var bar = $('#chips');
    bar.innerHTML = '';
    if (state.chars.length <= 1) { bar.style.display = 'none'; return; }
    bar.style.display = 'flex';
    state.chars.forEach(function (ch, i) {
      var hit = state.layers[ch] || {};
      var n = Object.keys(hit).length;
      var c = el('div', 'chip' + (i === state.sel ? ' sel' : '') + (n ? '' : ' none'), ch);
      c.title = ch + '：' + n + '/' + enabledLayers().length + ' 层有字形' +
        (state.counts[ch] > 1 ? '，出现 ' + state.counts[ch] + ' 次' : '');
      c.appendChild(el('span', 'dot'));
      c.onclick = function () { state.sel = i; state.focusVariant = 0; render(); };
      bar.appendChild(c);
    });
  }

  function renderDetail() {
    var host = $('#detail');
    host.innerHTML = '';
    var ch = currentChar();
    if (!ch) { host.style.display = 'none'; return; }
    host.style.display = 'flex';

    var hit = state.layers[ch] || {};
    var avail = enabledLayers().filter(function (L) { return hit[L.id] && hit[L.id].length; });
    if (!state.focusLayer || !hit[state.focusLayer]) {
      state.focusLayer = avail.length ? avail[0].id : null;
      state.focusVariant = 0;
    }
    var L = null;
    for (var i = 0; i < LAYERS.length; i++) if (LAYERS[i].id === state.focusLayer) { L = LAYERS[i]; break; }

    /* 大字预览 */
    var fm = L ? hit[L.id] : null;
    if (fm && state.focusVariant >= fm.length) state.focusVariant = 0;
    var wrap = el('div', 'bigwrap' + (state.preview === 'zhuwen' ? ' zhuwen' : state.preview === 'baiwen' ? ' baiwen' : ''));
    var badge = el('div', 'badge', L ? L.name_zh : '无字形');
    wrap.appendChild(badge);
    if (L) {
      var f0 = fm[state.focusVariant];
      var big = makeGlyph(L, f0.ch, f0.vi, 'big');
      wrap.appendChild(big);
    } else {
      wrap.appendChild(el('div', 'big', '—'));
    }
    var col = el('div');
    col.appendChild(wrap);
    var opts = el('div', 'bigopts');
    [['ink', '墨'], ['zhuwen', '朱文'], ['baiwen', '白文']].forEach(function (p) {
      var b = el('button', state.preview === p[0] ? 'on' : '', p[1]);
      b.onclick = function () { state.preview = p[0]; renderDetail(); };
      opts.appendChild(b);
    });
    col.appendChild(opts);
    host.appendChild(col);

    /* 右侧信息 */
    var info = el('div', 'info');
    info.appendChild(el('h2', null, ch));
    var cp = ch.codePointAt(0);
    info.appendChild(el('div', 'uc', 'U+' + cp.toString(16).toUpperCase().padStart(4, '0') +
      '　共 ' + avail.length + ' / ' + enabledLayers().length + ' 层收录' +
      (state.counts[ch] > 1 ? '　原文出现 ' + state.counts[ch] + ' 次' : '')));

    var kv = el('dl', 'kv');
    function kvRow(k, v) {
      kv.appendChild(el('dt', null, k));
      var dd = el('dd');
      if (v instanceof Node) dd.appendChild(v); else dd.textContent = v;
      kv.appendChild(dd);
    }
    if (L) {
      kvRow('書體', L.name_zh + (L.style_detail ? '（' + L.style_detail + '）' : ''));
      if (L.era) kvRow('時代', L.era);
      if (L.license) kvRow('許可', L.license);
      /* 该层收录的是繁体/异体，而用户输入的是简体（或反过来）时，明确标出来 */
      var other = [];
      fm.forEach(function (f) { if (f.ch !== ch && other.indexOf(f.ch) < 0) other.push(f.ch); });
      if (other.length) kvRow('源用字', other.join(' / '));
      kvRow('寫法', fm.length + (fm.length > 1 ? ' 種　↓ 點選切換' : ' 種'));
      var srcs = fm.map(function (f) { return f.src && (f.src[1] || f.src[0]); }).filter(Boolean);
      if (srcs.length) {
        var tg = el('span');
        srcs.slice(0, 6).forEach(function (s) { tg.appendChild(el('span', 'tag', trimSrc(s))); });
        kvRow('出處', tg);
      }
    } else {
      kvRow('字形', '所選層未收');
    }
    info.appendChild(kv);

    /* 反向入口：拿着这个字的字形去「以形查字」里找形近字 */
    var jump = el('div', 'xjump');
    var ja = el('a', 'xlink', '以形反查此字 →');
    ja.href = 'shape.html?ch=' + encodeURIComponent(ch);
    ja.title = '用「' + ch + '」的字形當樣本，在古文字層裡找形近字';
    jump.appendChild(ja);
    jump.appendChild(el('span', 'xhint', '認不出手裡的拓片？反過來查'));
    info.appendChild(jump);

    /* 异写 */
    if (L && fm.length > 1) {
      var vbox = el('div', 'variants');
      vbox.appendChild(el('h3', null, L.name_zh + ' · 异写 ' + fm.length + ' 种'));
      var vr = el('div', 'vrow');
      fm.forEach(function (f, k) {
        var card = el('div', 'vcard' + (k === state.focusVariant ? ' sel' : ''));
        card.appendChild(makeGlyph(L, f.ch, f.vi, 'g'));
        card.appendChild(el('div', 's', trimSrc((f.src && (f.src[1] || f.src[0])) || '')));
        card.appendChild(el('div', 'n',
          k === 0 ? '主形' : (f.ch !== ch ? '异体 ' + f.ch : (f.vi > 0 ? 'ss0' + f.vi : '写法 ' + (k + 1)))));
        card.onclick = function () { state.focusVariant = k; renderDetail(); };
        vr.appendChild(card);
      });
      vbox.appendChild(vr);
      info.appendChild(vbox);
    }

    /* 弱关联提示 */
    var rel = V.related && V.related[ch];
    if (rel && rel.length) {
      var rb = el('dl', 'kv');
      var dd = el('span');
      rel.slice(0, 12).forEach(function (r) {
        var t = el('span', 'tag', r);
        t.onclick = function () { setQuery(r); };
        dd.appendChild(t);
      });
      rb.appendChild(el('dt', null, '相关字'));
      rb.appendChild(dd);
      info.appendChild(rb);
    }

    host.appendChild(info);
    ensureMeta(L ? L.id : null);
  }

  function trimSrc(s) {
    s = String(s).replace(/\s+/g, ' ').trim();
    return s.length > 26 ? s.slice(0, 25) + '…' : s;
  }

  function renderMatrix() {
    var stage = $('#stage');
    stage.innerHTML = '';
    var ch = currentChar();
    if (!ch) return;
    var hit = state.layers[ch] || {};
    var avail = enabledLayers().filter(function (L) { return hit[L.id] && hit[L.id].length; });
    var missing = enabledLayers().filter(function (L) { return !hit[L.id]; });

    var head = el('div', 'sec-title');
    head.appendChild(el('span', null, '字形对照 · ' + ch + '（' + avail.length + ' / ' +
      enabledLayers().length + ' 层）'));
    /* 字形大小：对照时看小图，考释时看大图。记在本机。 */
    var sizes = el('div', 'msize');
    [['s', '小'], ['m', '中'], ['l', '大']].forEach(function (p) {
      var b = el('button', state.cellSize === p[0] ? 'on' : '', p[1]);
      b.title = '字形' + p[1] + '圖';
      b.onclick = function () {
        state.cellSize = p[0];
        try { localStorage.setItem('ga.cellsize', p[0]); } catch (e) {}
        renderMatrix();
      };
      sizes.appendChild(b);
    });
    head.appendChild(sizes);
    stage.appendChild(head);

    var grid = el('div', 'matrix');
    grid.dataset.size = state.cellSize;
    avail.forEach(function (L) {
      var fm2 = hit[L.id];
      var cell = el('div', 'cell' + (L.id === state.focusLayer ? ' sel' : ''));
      cell.appendChild(makeGlyph(L, fm2[0].ch, fm2[0].vi, 'g'));
      cell.appendChild(el('div', 'm', L.name_zh));
      cell.appendChild(el('div', 'e', L.era || ''));
      if (fm2.length > 1) cell.appendChild(el('span', 'v', fm2.length));
      var srcChars = [];
      fm2.forEach(function (f) { if (srcChars.indexOf(f.ch) < 0) srcChars.push(f.ch); });
      cell.title = L.name_zh + '｜' + srcChars.join('/') +
        (fm2.length > 1 ? '｜' + fm2.length + ' 种异写' : '') + '｜' + (L.license || '');
      cell.onclick = function () {
        state.focusLayer = L.id; state.focusVariant = 0;
        renderDetail(); renderMatrix();
        window.scrollTo({ top: 0, behavior: 'smooth' });
      };
      grid.appendChild(cell);
    });
    if (!avail.length) {
      grid.appendChild(el('div', 'empty', '当前启用的层里没有「' + ch + '」的字形'));
    }
    stage.appendChild(grid);

    if (missing.length) {
      stage.appendChild(el('div', 'missnote', '未收錄 ' + missing.length + ' 層：' +
        missing.map(function (L) { return L.name_zh; }).join('、')));
    }

    avail.forEach(function (L) { ensureMeta(L.id); });
  }

  /* ---------- 查询 ---------- */
  function setQuery(text) {
    $('#q').value = text;
    run(true);
  }

  function run(reset) {
    var raw = $('#q').value || '';
    state.text = raw;
    var seen = {}, uniq = [], counts = {};
    var arr = Array.from(raw);
    for (var i = 0; i < arr.length; i++) {
      var ch = arr[i];
      if (/\s/.test(ch)) continue;
      counts[ch] = (counts[ch] || 0) + 1;
      if (!seen[ch]) { seen[ch] = 1; uniq.push(ch); }
      if (uniq.length >= MAX_INPUT) break;
    }
    state.chars = uniq;
    state.counts = counts;
    if (reset) { state.sel = 0; state.focusLayer = null; state.focusVariant = 0; }
    if (state.sel >= uniq.length) state.sel = 0;
    render();
  }

  /* ---------- 初始化 ---------- */
  function boot() {
    var ancient = LAYERS.filter(function (L) { return L.kind !== 'modern-font' || L.group === 'ancient'; });
    ancient.forEach(function (L) { state.enabled.add(L.id); });
    /* 默认摆出「楷、行、草」各一款书法字体，而不是排版字体——
       用户要的是看字形，不是排正文。 */
    ['mashanzheng', 'lxgwwenkai', 'zhimangxing', 'liujianmaocao'].forEach(function (id) {
      if (LAYERS.some(function (L) { return L.id === id; })) state.enabled.add(id);
    });
    LAYERS.forEach(function (L) { if (state.enabled.has(L.id)) ensureCss(L.id); });

    var nm = LAYERS.filter(function (L) { return L.kind === 'modern-font' && L.group !== 'ancient'; }).length;
    if ($('#fontcount')) $('#fontcount').textContent = window.GA_FONTCOUNT || LAYERS.length;
    if ($('#nf2')) $('#nf2').textContent = nm;

    renderSidebar();

    /* 窄屏：36 层会把查询框顶到首屏之外，默认收起，点标题展开 */
    var st = $('#sidetoggle'), side = $('#side');
    if (st && side) {
      st.onclick = function () {
        var open = side.classList.toggle('open');
        st.setAttribute('aria-expanded', open ? 'true' : 'false');
      };
    }

    $('#go').onclick = function () { run(true); };
    var tm = null;
    $('#q').addEventListener('input', function () {
      clearTimeout(tm);
      tm = setTimeout(function () { run(true); }, 260);
    });

    $('#all-on').onclick = function () {
      LAYERS.forEach(function (L) { state.enabled.add(L.id); ensureCss(L.id); });
      renderSidebar(); render();
    };
    $('#ancient-on').onclick = function () {
      state.enabled.clear();
      LAYERS.forEach(function (L) { if (L.kind !== 'modern-font' || L.group === 'ancient') { state.enabled.add(L.id); ensureCss(L.id); } });
      renderSidebar(); render();
    };
    $('#all-off').onclick = function () {
      state.enabled.clear(); renderSidebar(); render();
    };

    var seed = new URLSearchParams(location.search).get('q');
    $('#q').value = seed || '永受嘉福長樂未央';
    run(true);
    if (location.hash === '#parts') {
      var t = document.querySelector('.mt[data-mode="parts"]');
      if (t) t.click();
    }
  }

  /* ---------- 給部件檢索用的接口 ---------- */
  window.GA_IS_ON = function (id) { return state.enabled.has(id); };
  window.GA_OPEN_CHAR = function (ch) {
    setQuery(ch);
    var q = $('#q');
    if (q) { q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
  };
  window.GA_SET_ENABLED = function (ids) {
    state.enabled.clear();
    ids.forEach(function (id) { state.enabled.add(id); ensureCss(id); });
    renderSidebar(); render();
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
