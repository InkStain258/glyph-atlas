/* 字體與版權頁 —— 数据来自 data/licenses.js（window.GA_LICENSES）
 * 本页不加载任何字体分片，只渲染元数据与协议全文，所以秒开。
 */
(function () {
  'use strict';

  var D = window.GA_LICENSES || { texts: {}, fonts: [], counts: {} };
  var fonts = D.fonts || [];
  var texts = D.texts || {};
  var $ = function (s) { return document.querySelector(s); };

  function h(tag, cls, txt) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt != null) n.textContent = txt;
    return n;
  }

  var BADGE_ALIAS = { 'PROPRIETARY': '專有授權', 'UNKNOWN': '許可不明', 'UNVERIFIED': '許可待核' };

  var LIC_LABEL = {
    'OFL-1.1': 'SIL OFL 1.1',
    'CC0-1.0': 'CC0 1.0',
    'CC-BY-4.0': 'CC BY 4.0',
    'PD': '公有領域',
    'PROJECT-GRANT': '項目組授權',
    'Arphic-PL-1.0': '文鼎公共許可',
    'GPL-3.0+FE': 'GPL + 字體例外',
    'GPL-2.0': 'GPL v2',
    'IPA-1.0': 'IPA 許可'
  };

  var state = { filter: 'all' };

  function shipped() { return fonts.filter(function (f) { return f.shipped; }); }
  function rejected() { return fonts.filter(function (f) { return !f.shipped; }); }

  function lede() {
    var c = D.counts || {};
    var sh = shipped();
    var FREE = ['OFL-1.1', 'CC0-1.0', 'CC-BY-4.0', 'PD', 'GPL-2.0', 'GPL-3.0+FE', 'Arphic-PL-1.0'];
    var free = sh.filter(function (f) { return FREE.indexOf(f.license_spdx) >= 0; }).length;
    var grant = sh.filter(function (f) { return FREE.indexOf(f.license_spdx) < 0; });
    var grantLic = {};
    grant.forEach(function (f) { grantLic[f.license_spdx] = (grantLic[f.license_spdx] || 0) + 1; });
    var el = $('#lede');
    el.innerHTML = '';
    el.appendChild(h('b', null, '共 ' + (c.shipped || 0) + ' 款字體，許可全部可查、可合法使用。'));
    el.appendChild(document.createTextNode(
      ' 其中古文字字形源 ' + (c.ancient || 0) + ' 款、書法與手寫 ' + (c.calligraphy || 0) +
      ' 款、刻本與活字 ' + (c.print || 0) + ' 款、現代排版 ' + (c.modern || 0) + ' 款。' +
      ' ' + free + ' 款為 SIL OFL 1.1 / CC0 1.0 / CC BY 4.0 / 公有領域 / GPL v2 / GPL + 字體例外 / 文鼎公共許可，' +
      '可商用、可修改、可再分發；' +
      (grant.length ? (function () {
        var keys = Object.keys(grantLic);
        var label = keys.length === 1 ? (LIC_LABEL[keys[0]] || keys[0]) : keys.map(function (k) { return (LIC_LABEL[k] || k) + ' ' + grantLic[k]; }).join('、');
        return ' 另有 ' + grant.length + ' 款（' + label + '）不走標準開源許可，而是作者／項目組的書面授權：需署名、禁商用，可隨本工具公開分發，卡片上單獨標注。';
      })() : '') +
      ' 每款字体在仓库 fonts/ 下都有独立目录，内含 LICENSE.txt（协议全文）、license.json（结构化条款）与 NOTICE.md（来源与改动声明）。'));
  }

  function filters() {
    var el = $('#filters');
    el.innerHTML = '';
    var c = D.counts || {};
    var items = [
      ['all', '全部', c.shipped || 0],
      ['ancient', '古文字字形源', c.ancient || 0],
      ['calligraphy', '書法 · 手寫', c.calligraphy || 0],
      ['print', '刻本 · 活字', c.print || 0],
      ['modern', '現代 · 排版', c.modern || 0],
      ['OFL-1.1', 'OFL 1.1', null],
      ['CC0-1.0', 'CC0', null],
      ['PD', '公有領域', null],
      ['other', '其他授權', null]
    ];
    items.forEach(function (it) {
      var b = h('button', state.filter === it[0] ? 'on' : '', it[1] + (it[2] != null ? ' ' + it[2] : ''));
      b.onclick = function () { state.filter = it[0]; filters(); render(); };
      el.appendChild(b);
    });
  }

  function pass(f) {
    if (!f.shipped) return false;
    var k = state.filter;
    if (k === 'all') return true;
    if (k === 'ancient' || k === 'calligraphy' || k === 'print' || k === 'modern') return f.group === k;
    if (k === 'CC0-1.0') return f.license_spdx === 'CC0-1.0';
    if (k === 'other') return ['OFL-1.1', 'CC0-1.0', 'PD'].indexOf(f.license_spdx) < 0;
    return f.license_spdx === k;
  }

  function openReader(f) {
    var body = $('#rbody');
    body.innerHTML = '';
    var list = [f.license_spdx];
    if (f.license_spdx_extra && f.license_spdx_extra !== f.license_spdx) list.push(f.license_spdx_extra);
    list.forEach(function (spdx) {
      var t = texts[spdx];
      var sec = h('div', 'rsec');
      sec.appendChild(h('h3', null, (LIC_LABEL[spdx] || spdx) + (t && t.name ? '　' + t.name : '')));
      if (t && t.summary) sec.appendChild(h('p', 'rsum', '本项目的理解：' + t.summary));
      if (t && t.url) {
        var a = h('a', 'rurl', t.url);
        a.href = t.url; a.target = '_blank'; a.rel = 'noopener';
        sec.appendChild(a);
      }
      sec.appendChild(h('pre', 'licbody', (t && t.body) || '（未收录全文）'));
      body.appendChild(sec);
    });
    $('#rtitle').textContent = f.name_zh + ' · 許可全文';
    $('#reader').hidden = false;
    $('#rclose').focus();
  }

  function closeReader() { $('#reader').hidden = true; }

  function card(f) {
    var c = h('div', 'card' + (f.shipped ? '' : ' q'));
    var top = h('div', 'top');
    top.appendChild(h('div', 'mono', f.mono));
    var tt = h('div', 'tt');
    var nm = h('div', 'nm', f.name_zh);
    // 隔离分两种：条款不允许（徽章报许可名）vs 条款干净但来源存疑（徽章报「來源存疑」，
    // 否则读者会以为 GPL v2 不能用）。
    var btext = f.shipped ? (LIC_LABEL[f.license_spdx] || f.license_spdx)
      : (f.quarantine_basis === 'provenance' ? '來源存疑' : (LIC_LABEL[f.license_spdx] || f.license_spdx));
    var badge = h('span', 'badge ' + (f.shipped ? 'ok' : 'warn'), btext);
    nm.appendChild(document.createTextNode(' '));
    nm.appendChild(badge);
    tt.appendChild(nm);
    if (f.name_en) tt.appendChild(h('div', 'en', f.name_en));
    top.appendChild(tt);
    c.appendChild(top);

    if (!f.shipped) {
      c.appendChild(h('div', 'meta', (f.era ? f.era + ' · ' : '') + (f.reject_reason || '许可不兼容')));
      c.appendChild(h('div', 'meta', '未採用：不進入構建，字體文件不隨倉庫分發，僅在本機留檔備查。'));
      if (f.source_url) {
        var acts0 = h('div', 'acts');
        var a0 = h('a', null, '来源 ↗');
        a0.href = f.source_url; a0.target = '_blank'; a0.rel = 'noopener';
        acts0.appendChild(a0);
        c.appendChild(acts0);
      }
      return c;
    }

    var meta = [];
    if (f.era) meta.push(f.era);
    if (f.chars) meta.push(f.chars + ' 字');
    if (f.glyphs && f.glyphs !== f.chars) meta.push(f.glyphs + ' 字形');
    if (f.variants) meta.push(f.variants + ' 异写');
    c.appendChild(h('div', 'meta', meta.join(' · ')));

    var row = h('div', 'row');
    if (f.license_spdx_extra) {
      row.appendChild(h('span', 'badge', '+ ' + (LIC_LABEL[f.license_spdx_extra] || f.license_spdx_extra) + '（部分）'));
    }
    row.appendChild(h('span', 'badge', f.attribution_required ? '需署名' : '無需署名'));
    row.appendChild(h('span', 'badge', f.modification_allowed ? '可修改' : '禁改'));
    row.appendChild(h('span', 'badge', f.commercial_use_allowed ? '可商用' : '禁商用'));
    if (f.web_shipped === false) row.appendChild(h('span', 'badge', '僅歸檔'));
    c.appendChild(row);

    var facts = h('dl', 'facts');
    facts.hidden = true;
    function frow(k, v) {
      if (!v) return;
      facts.appendChild(h('dt', null, k));
      facts.appendChild(h('dd', null, v));
    }
    frow('版权方', f.copyright_holder);
    frow('作者', f.author);
    frow('内容', f.source_detail);
    frow('目录', f.folder + '/');
    if (f.attribution_text) frow('署名文字', f.attribution_text);
    c.appendChild(facts);

    var acts = h('div', 'acts');
    var btn = h('button', null, '許可全文');
    acts.appendChild(btn);
    var a = h('a', null, '来源 ↗');
    a.href = f.source_url || '#'; a.target = '_blank'; a.rel = 'noopener';
    acts.appendChild(a);
    acts.appendChild(h('span', 'sp'));
    var who = h('button', null, '详情');
    acts.appendChild(who);
    c.appendChild(acts);

    btn.onclick = function () { openReader(f); };
    who.onclick = function () { facts.hidden = !facts.hidden; };
    return c;
  }

  function render() {
    var host = $('#cards');
    host.innerHTML = '';
    var list = shipped().filter(pass);
    if (!list.length) host.appendChild(h('div', 'empty', '没有符合这个筛选的字體'));
    list.forEach(function (f) { host.appendChild(card(f)); });

    var rej = rejected();
    $('#rej-count').textContent = rej.length + ' 款';
    var rhost = $('#rejected');
    rhost.innerHTML = '';
    rej.forEach(function (f) { rhost.appendChild(card(f)); });
  }

  $('#rclose').onclick = closeReader;
  $('#reader').onclick = function (e) { if (e.target.id === 'reader') closeReader(); };
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeReader(); });

  lede();
  filters();
  render();
})();