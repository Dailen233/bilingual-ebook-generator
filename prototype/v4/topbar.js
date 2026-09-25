/* v4 共享顶栏脚本
   职责：模拟登录态渲染（头像/账号）、当前页标记、账号下拉菜单、移动抽屉兜底。
   说明：登录、账号、退出均为【原型模拟】，不接真实账号系统。 */
(function () {
  'use strict';

  function read(key, fb) {
    try { var v = JSON.parse(localStorage.getItem(key)); return v == null ? fb : v; }
    catch (e) { return fb; }
  }

  // 退出（模拟）：dashboard.html 内已有同名函数，这里提供兜底
  window.logout = window.logout || function () {
    try { localStorage.removeItem('v2_user_v1'); } catch (e) {}
    location.href = 'index.html';
  };

  function currentFile() {
    var p = location.pathname.split('/').pop() || 'index.html';
    return p;
  }

  // 子页面归属：阅读页归「我的书库」，任务详情归「创建任务」
  var PARENT = { 'reader.html': 'library.html', 'task-detail.html': 'new-task.html' };

  function markCurrent() {
    var here = currentFile();
    var own = PARENT[here] || here;
    var links = document.querySelectorAll('.topbar .nav a, #mobile-nav a');
    Array.prototype.forEach.call(links, function (a) {
      var target = (a.getAttribute('href') || '').split('?')[0];
      if (target && target === own) {
        a.classList.add('active');
        a.setAttribute('aria-current', 'page');
      } else {
        a.classList.remove('active');
        a.removeAttribute('aria-current');
      }
    });
  }

  // 抽屉的 Esc 关闭：内页由 app.js 负责开合，这里只补键盘关闭，不重复绑定点击
  function escapeClosesDrawer() {
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') return;
      var panel = document.getElementById('mobile-nav');
      var btn = document.getElementById('menu-btn');
      var mask = document.getElementById('nav-mask');
      if (!panel || !panel.classList.contains('open')) return;
      panel.classList.remove('open');
      if (mask) mask.classList.remove('show');
      if (btn) { btn.setAttribute('aria-expanded', 'false'); btn.focus(); }
    });
  }

  function syncAuth() {
    var user = read('v2_user_v1', null);
    var acct = document.querySelector('.acct');
    var guest = document.querySelector('.guest-actions');
    if (!acct && !guest) return;
    if (user) {
      if (acct) acct.hidden = false;
      if (guest) guest.hidden = true;
      var name = user.name || '示例用户';
      var mail = user.mail || 'example@example.com';
      var av = document.getElementById('u-av');
      var nn = document.getElementById('u-name');
      var mm = document.getElementById('u-mail');
      var am = document.getElementById('acct-mail');
      if (av) av.textContent = name.charAt(0);
      if (nn) nn.textContent = name;
      if (mm) mm.textContent = mail;
      if (am) am.textContent = mail;
    } else {
      if (acct) acct.hidden = true;
      if (guest) guest.hidden = false;
    }
  }

  function setupAccount() {
    var acct = document.querySelector('.acct');
    if (!acct) return;
    var btn = acct.querySelector('.acct-btn');
    var menu = acct.querySelector('.acct-menu');
    if (!btn || !menu) return;

    function close(focusBack) {
      menu.hidden = true;
      btn.setAttribute('aria-expanded', 'false');
      if (focusBack) btn.focus();
    }
    function open() {
      menu.hidden = false;
      btn.setAttribute('aria-expanded', 'true');
      var first = menu.querySelector('.acct-item');
      if (first) first.focus();
    }
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      if (menu.hidden) open(); else close(false);
    });
    btn.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); open(); }
      if (e.key === 'Escape') close(true);
    });
    menu.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { e.preventDefault(); close(true); }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        var items = Array.prototype.slice.call(menu.querySelectorAll('.acct-item'));
        var i = items.indexOf(document.activeElement);
        var next = e.key === 'ArrowDown' ? i + 1 : i - 1;
        if (next < 0) next = items.length - 1;
        if (next >= items.length) next = 0;
        items[next].focus();
      }
    });
    document.addEventListener('click', function (e) {
      if (!menu.hidden && !acct.contains(e.target)) close(false);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !menu.hidden) close(true);
    });
  }

  function setupDrawer() {
    // 内页由 app.js 负责抽屉；此处仅为未加载 app.js 的页面（如首页）兜底
    if (window.V2) return;
    var btn = document.getElementById('menu-btn');
    var panel = document.getElementById('mobile-nav');
    var mask = document.getElementById('nav-mask');
    if (!btn || !panel) return;
    function setOpen(open) {
      panel.classList.toggle('open', open);
      if (mask) mask.classList.toggle('show', open);
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    }
    btn.setAttribute('aria-expanded', 'false');
    btn.addEventListener('click', function () {
      setOpen(!panel.classList.contains('open'));
    });
    if (mask) mask.addEventListener('click', function () { setOpen(false); });
    panel.addEventListener('click', function (e) {
      if (e.target.tagName === 'A') setOpen(false);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && panel.classList.contains('open')) { setOpen(false); btn.focus(); }
    });
  }

  function init() {
    markCurrent();
    syncAuth();
    setupAccount();
    setupDrawer();
    escapeClosesDrawer();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
