/* 部件檢索 —— 「左邊是氵，右邊不認識」
 *
 * 資料：BabelStone IDS（表意文字描述序列，Unicode 16.0，97,680 字）
 *       事實資料，作者明確許可自由使用、無須署名。
 * 做法：ids.js 按需載入 → 本地解析成「部件 → 方位 → 字」的字串索引
 *       （字串比 Set 省記憶體，一個 1 個字的 CJK 只佔 2 bytes）。
 * 不依賴伺服器：file:// 直接雙擊可用。
 */
(function () {
  'use strict';

  var ARITY = {
    '\u2ff0': 2, '\u2ff1': 2, '\u2ff2': 3, '\u2ff3': 3, '\u2ff4': 2, '\u2ff5': 2,
    '\u2ff6': 2, '\u2ff7': 2, '\u2ff8': 2, '\u2ff9': 2, '\u2ffa': 2, '\u2ffb': 2,
    '\u2ffd': 2, '\u31ef': 2
  };
  /* 每個操作符的方位序列；⿻ 是重疊，方位不可判，歸「X」 */
  var SLOTS = {
    '\u2ff0': ['L', 'R'], '\u2ff1': ['T', 'B'],
    '\u2ff2': ['L', 'M', 'R'], '\u2ff3': ['T', 'M', 'B'],
    '\u2ff4': ['O', 'I'], '\u2ff5': ['O', 'I'], '\u2ff6': ['O', 'I'],
    '\u2ff7': ['O', 'I'], '\u2ff8': ['O', 'I'], '\u2ff9': ['O', 'I'],
    '\u2ffa': ['O', 'I'], '\u2ffb': ['X', 'X'],
    '\u2ffd': ['O', 'I'], '\u31ef': ['O', 'I']
  };
  var POS = [
    ['L', '左'], ['R', '右'], ['T', '上'], ['B', '下'],
    ['M', '中'], ['O', '外'], ['I', '內'], ['A', '任意']
  ];
  /* 常見異形部件：查氵時把水也帶上，查扌時把手帶上 */
  var ALIAS = {
    '氵': '水', '水': '氵', '扌': '手', '手': '扌', '亻': '人', '人': '亻',
    '讠': '言', '言': '讠', '忄': '心', '心': '忄', '艹': '艸', '艸': '艹',
    '钅': '金', '金': '钅', '纟': '糸', '糸': '纟', '衤': '衣', '衣': '衤',
    '礻': '示', '示': '礻', '攵': '攴', '攴': '攵', '饣': '食', '食': '饣',
    '犭': '犬', '犬': '犭', '牜': '牛', '牛': '牜', '刂': '刀', '刀': '刂',
    '灬': '火', '火': '灬', '讠': '言', '辶': '辵', '辵': '辶',
    '阝': '阜', '阜': '阝', '丬': '爿', '爿': '丬', '氺': '水'
  };
  /* 常駐的 28 個高頻部件；其餘收在「更多」裡，避免一進頁就被部件牆淹沒 */
  var PAL_TOP = ('氵亻扌讠忄艹竹木火土金女口日月目石禾糸衤宀广疒阝攵刂心辶').split('');
  var PAL_MORE = ('丶丿乙十八人大山工己干彳廴小士寸尢巛川幺彡攴斤方无曰欠止歹殳毋比毛氏气爪父爻爿片牙玄瓜瓦甘生用疋癶白皮矛矢禸穴立米缶网羊羽老而耒耳聿肉臣自至臼舌舛舟艮色虍血行衣襾角谷豆豕貝赤走身辛辰邑酉釆里長阜隶隹雨青非面革韋韭音頁風飛食首香馬骨高髟鬥鬯鬲鬼魚鳥鹵鹿麥麻黃黍黑黹黽鼎鼓鼠鼻齊齒龍龜龠').split('');

  var $ = function (s, r) { return (r || document).querySelector(s); };
  function el(tag, cls, txt) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt != null) n.textContent = txt;
    return n;
  }
  function chars(s) { return Array.from(s); }

  var IDS = null;          // { meta, src:[ '字'+ids, ... ] }
  var idxAny = {};         // 部件 -> {L:'字串', ...}
  var idxTop = {};         // 只算根節點那一層
  var idsOf = {};          // 字 -> IDS 顯示串
  var loading = null;
  var st = { pos: 'L', comp: '', onlyAncient: false };

  /* ---------- 解析 ---------- */
  function parse(s) {
    var i = 0;
    function atom() {
      var c = s[i];
      if (!c) return null;
      if (c === '{') {                       // {nn} 無編碼部件，整體當一個原子
        var j = s.indexOf('}', i);
        if (j < 0) return null;
        var a = s.slice(i, j + 1);
        i = j + 1;
        return { ch: a };
      }
      var n = ARITY[c];
      if (!n) { i++; return { ch: c }; }
      i++;
      var kids = [];
      for (var k = 0; k < n; k++) {
        var kid = atom();
        if (!kid) return null;
        kids.push(kid);
      }
      return { op: c, kids: kids };
    }
    var t = atom();
    return (t && i === s.length) ? t : null;
  }

  function addTo(box, comp, slot, ch) {
    if (!box[comp]) box[comp] = {};
    var v = box[comp][slot];
    box[comp][slot] = v ? v + ch : ch;
  }

  function walk(node, ch, top) {
    if (!node || !node.op) return;
    var slots = SLOTS[node.op] || ['L', 'R'];
    for (var k = 0; k < node.kids.length; k++) {
      var kid = node.kids[k];
      var c = kid.ch;
      if (c && c.length === 1 && !ARITY[c] && c !== '\uff1f') {
        addTo(idxAny, c, slots[k] || 'X', ch);
        if (top) addTo(idxTop, c, slots[k] || 'X', ch);
      }
      walk(kid, ch, false);
    }
  }

  function buildIndex() {
    var src = IDS.src;
    for (var i = 0; i < src.length; i++) {
      var e = src[i];
      var ch = String.fromCodePoint(e.codePointAt(0));   // 非 BMP 字不能用 e[0]
      var d = e.slice(ch.length);
      if (!d) { idsOf[ch] = ''; continue; }
      idsOf[ch] = d;
      var t = parse(d);
      if (t) walk(t, ch, true);
    }
  }

  /* ---------- 資料載入 ---------- */
  function loadIds() {
    if (IDS) return Promise.resolve(IDS);
    if (loading) return loading;
    loading = new Promise(function (res, rej) {
      var s = document.createElement('script');
      s.src = 'data/ids.js';
      s.onload = function () {
        IDS = window.GA_IDS;
        if (!IDS || !IDS.src) { rej(new Error('ids.js 格式錯誤')); return; }
        buildIndex();
        res(IDS);
      };
      s.onerror = function () { rej(new Error('缺少 data/ids.js')); };
      document.head.appendChild(s);
    });
    return loading;
  }

  /* ---------- 檢索 ---------- */
  function layersEnabled() {
    return (window.GA_LAYERS || []).filter(function (L) {
      return window.GA_IS_ON ? window.GA_IS_ON(L.id) : false;
    });
  }

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

  var GB1 = {}, GB2 = {};
  function gbInit() {
    if (!IDS || !IDS.meta) return;
    chars(IDS.meta.gb1 || '').forEach(function (c) { GB1[c] = 1; });
    chars(IDS.meta.gb2 || '').forEach(function (c) { GB2[c] = 1; });
  }

  function search() {
    var comp = st.comp;
    if (!comp) return [];
    var want = [comp];
    if (ALIAS[comp]) want.push(ALIAS[comp]);
    var seen = {}, out = [];
    var pos = st.pos;
    want.forEach(function (c) {
      if (pos === 'A') {
        /* 任意位置：直接在 IDS 字串裡找字符（97,680 條線性掃描，約 20ms） */
        var src = IDS.src;
        for (var i = 0; i < src.length; i++) {
          var e = src[i];
          var ch0 = String.fromCodePoint(e.codePointAt(0));
          var off = ch0.length;
          if (e.length > off && e.indexOf(c, off) >= 0 && !seen[ch0]) {
            seen[ch0] = 1; out.push([ch0, 0]);
          }
        }
      } else {
        var top = (idxTop[c] || {})[pos] || '';
        chars(top).forEach(function (x) { if (!seen[x]) { seen[x] = 1; out.push([x, 1]); } });
        var all = (idxAny[c] || {})[pos] || '';
        chars(all).forEach(function (x) { if (!seen[x]) { seen[x] = 1; out.push([x, 0]); } });
      }
    });
    return out;
  }

  function rank(rows) {
    var Ls = layersEnabled();
    return rows.map(function (r) {
      var ch = r[0], cp = ch.codePointAt(0), n = 0;
      for (var i = 0; i < Ls.length; i++) if (hasCp(Ls[i], cp)) n++;
      var g = GB1[ch] ? 2 : (GB2[ch] ? 1 : 0);
      return { ch: ch, top: r[1], anc: n, score: n * 6 + g * 3 + r[1] * 2 };
    }).sort(function (a, b) {
      return (b.score - a.score) || (a.ch.codePointAt(0) - b.ch.codePointAt(0));
    });
  }

  /* ---------- 畫面 ---------- */
  function renderPos() {
    var box = $('#ppos');
    box.innerHTML = '';
    POS.forEach(function (p) {
      var b = el('button', 'pos' + (st.pos === p[0] ? ' on' : ''), p[1]);
      b.onclick = function () { st.pos = p[0]; renderPos(); run(); };
      box.appendChild(b);
    });
  }

  function renderPalette() {
    var box = $('#palette');
    box.innerHTML = '';
    box.classList.toggle('more', !!st.more);
    function tile(c) {
      var b = el('button', 'pc' + (c === st.comp ? ' on' : ''), c);
      b.title = c;
      b.onclick = function () {
        st.comp = c;
        $('#pc').value = c;
        renderPalette();
        run();
      };
      box.appendChild(b);
    }
    PAL_TOP.forEach(tile);
    if (st.more) PAL_MORE.forEach(tile);
    var t = el('button', 'pc more-t', st.more ? '收起' : '更多');
    t.onclick = function () { st.more = !st.more; renderPalette(); };
    box.appendChild(t);
  }

  function renderResults(rows, total) {
    var box = $('#pres');
    box.innerHTML = '';
    if (!st.comp) { box.appendChild(el('div', 'phint', '輸入一個部件，或點下面的常用部件。')); return; }
    if (!rows.length) {
      var pn = (POS.filter(function (p) { return p[0] === st.pos; })[0] || ['', '該方位'])[1];
      box.appendChild(el('div', 'phint', st.pos === 'A'
        ? '沒有包含「' + st.comp + '」的字。'
        : '沒有以「' + st.comp + '」為' + pn + '部件的字。'));
      return;
    }
    var Ls = layersEnabled().length;
    var alias = ALIAS[st.comp];
    box.appendChild(el('div', 'ptitle',
      '「' + st.comp + (alias ? '／' + alias : '') + '」' +
      (POS.filter(function (p) { return p[0] === st.pos; })[0] || ['', ''])[1] +
      ' · 共 ' + total + ' 字' + (total > rows.length ? '（顯示前 ' + rows.length + '）' : '') +
      (Ls ? '' : '　·　側欄未啟用任何字體層')));
    var grid = el('div', 'pgrid');
    rows.forEach(function (r) {
      var c = el('div', 'pcell');
      c.appendChild(el('span', 'pg', r.ch));
      if (r.anc) {
        var b = el('span', 'pn', String(r.anc));
        b.title = r.anc + ' 個已啟用字體層有此字';
        c.appendChild(b);
      }
      c.title = r.ch + '　' + (idsOf[r.ch] || '（無結構資料）') + (r.anc ? '　' + r.anc + ' 層有字形' : '');
      c.onclick = function () { openChar(r.ch); };
      grid.appendChild(c);
    });
    box.appendChild(grid);
  }

  function openChar(ch) {
    if (window.GA_OPEN_CHAR) window.GA_OPEN_CHAR(ch);
    setMode('find');
  }

  var timer = null;
  function run() {
    clearTimeout(timer);
    timer = setTimeout(function () {
      if (!IDS) return;
      var rows = search();
      var ranked = rank(rows);
      renderResults(ranked.slice(0, 240), ranked.length);
    }, 30);
  }

  /* ---------- 模式切換 ---------- */
  function setMode(m) {
    if (document.body.dataset.mode !== m) window.scrollTo(0, 0);
    document.body.dataset.mode = m;
    if ($('#partspane')) $('#partspane').hidden = m !== 'parts';
    if ($('#findpane')) $('#findpane').hidden = m === 'parts';
    Array.prototype.forEach.call(document.querySelectorAll('.mt'), function (b) {
      b.classList.toggle('on', b.dataset.mode === m);
    });
    if (m === 'parts') {
      if (!IDS) {
        renderResults([], 0);
        var ph = $('#pres');
        if (ph) { ph.innerHTML = ''; ph.appendChild(el('div', 'phint', '正在載入部件索引（1.7 MB，僅首次）…')); }
        loadIds().then(function () {
          gbInit();
          renderPalette();
          renderResults([], 0);
        }).catch(function (e) {
          var ph2 = $('#pres');
          if (ph2) { ph2.innerHTML = ''; ph2.appendChild(el('div', 'phint', '載入失敗：' + e.message)); }
        });
      }
    }
  }

  function boot() {
    if (!$('#partspane')) return;
    document.querySelectorAll('.mt').forEach(function (b) {
      b.onclick = function () { setMode(b.dataset.mode); };
    });
    renderPos();
    renderPalette();
    var pc = $('#pc');
    pc.addEventListener('input', function () {
      var v = Array.from(pc.value).filter(function (c) { return !/\s/.test(c); });
      st.comp = v.length ? v[v.length - 1] : '';
      renderPalette();
      run();
    });
    $('#pgo').onclick = function () { run(); };
    pc.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); run(); } });
    setMode('find');
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();