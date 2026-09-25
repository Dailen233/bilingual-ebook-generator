/* ============================================================
   v3 原型 · 共享脚本（模拟态）
   说明：本原型为高保真可点击原型，登录、管理员权限、生成结果、
   审核操作均为【模拟】，不接真实后端，不声称具备真实安全能力。
   v3 在 v2 基础上增加：阅读偏好（视图/字号）持久化、进度环工具、
   PWA Service Worker 注册。
   ============================================================ */

(function () {
  'use strict';

  var K = {
    user: 'v2_user_v1',
    admin: 'v2_admin_v1',
    task: 'v2_task_v1',
    library: 'v2_library_v1',
    readerPref: 'v3_reader_pref_v1'
  };

  // 默认示例用户 / 管理员（原型演示用，模拟登录）
  var DEMO_USER = { name: '林一舟', mail: 'yizhou@example.com', role: 'user' };
  var DEMO_ADMIN = { name: '管理员', mail: 'admin@example.com', role: 'admin' };

  function read(key, fallback) {
    try { var v = JSON.parse(localStorage.getItem(key)); return v == null ? fallback : v; }
    catch (e) { return fallback; }
  }
  function write(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) {}
  }

  // ---- 默认书库示例数据 ----
  function seedLibrary() {
    if (read(K.library, null) != null) return;
    write(K.library, [
      { id: 'b1', name: 'The Harbor Fog · 港口雾', src: '英语', tgt: '中文', time: '2026-09-22 14:02', status: 'done' },
      { id: 'b2', name: 'Der Leuchtturm · 灯塔', src: '德语', tgt: '中文', time: '2026-09-18 09:31', status: 'done' }
    ]);
  }

  // ---- 登录态（模拟） ----
  function isUser() { return !!read(K.user, null); }
  function isAdmin() { return !!read(K.admin, null); }
  function setUser() { write(K.user, DEMO_USER); }
  function setAdmin() { write(K.admin, DEMO_ADMIN); }
  function clearAuth() { localStorage.removeItem(K.user); localStorage.removeItem(K.admin); }

  // ---- 任务状态（模拟处理进度） ----
  function getTask() { return read(K.task, null); }
  function setTask(t) { write(K.task, t); }

  // ---- 阅读偏好（视图/字号，P1 阅读位置与处理进度分离，此处仅存阅读偏好） ----
  function getReaderPref() {
    return read(K.readerPref, { view: 'split', font: 2 });
  }
  function setReaderPref(p) {
    var cur = getReaderPref();
    write(K.readerPref, Object.assign(cur, p));
  }

  // ---- 进度环工具（G4 可见进度） ----
  function setRing(el, pct, cls) {
    if (!el) return;
    el.style.setProperty('--pct', Math.max(0, Math.min(100, pct)));
    var txt = el.querySelector('.ring-txt b');
    if (txt) txt.textContent = Math.round(pct) + '%';
    if (cls) { el.classList.remove('gold', 'err'); el.classList.add(cls); }
  }

  // ---- 移动端导航抽屉 ----
  function setupDrawer() {
    var btn = document.getElementById('menu-btn');
    var panel = document.getElementById('mobile-nav');
    var mask = document.getElementById('nav-mask');
    if (!btn || !panel) return;
    function open() { panel.classList.add('open'); if (mask) mask.classList.add('show'); }
    function close() { panel.classList.remove('open'); if (mask) mask.classList.remove('show'); }
    btn.addEventListener('click', open);
    if (mask) mask.addEventListener('click', close);
    panel.querySelectorAll('a').forEach(function (a) { a.addEventListener('click', close); });
  }

  // ---- 受保护页守卫（模拟，真实场景由服务端校验） ----
  function requireUser() {
    if (!isUser()) { location.href = 'login.html'; return false; }
    return true;
  }
  function requireAdmin() {
    if (!isAdmin()) { location.href = 'admin-login.html'; return false; }
    return true;
  }

  // ---- 暴露给页面（v2 命名保留，v3 增量见 V3） ----
  window.V2 = {
    K: K, read: read, write: write,
    isUser: isUser, isAdmin: isAdmin,
    setUser: setUser, setAdmin: setAdmin, clearAuth: clearAuth,
    getTask: getTask, setTask: setTask,
    DEMO_USER: DEMO_USER, DEMO_ADMIN: DEMO_ADMIN,
    requireUser: requireUser, requireAdmin: requireAdmin
  };
  window.V3 = {
    getReaderPref: getReaderPref, setReaderPref: setReaderPref, setRing: setRing
  };

  document.addEventListener('DOMContentLoaded', function () {
    seedLibrary();
    setupDrawer();
    // 全局：给所有标注 [data-sim] 的元素追加模拟提示（保持文案一致）
    document.querySelectorAll('[data-sim]').forEach(function (el) {
      if (!el.querySelector('.sim-note')) {
        var s = document.createElement('span');
        s.className = 'sim-note';
        s.textContent = '· 原型模拟';
        el.appendChild(s);
      }
    });
    // PWA：注册 Service Worker（仅 http/https；file:// 下静默跳过）
    if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.protocol === 'http:')) {
      navigator.serviceWorker.register('sw.js').catch(function () { /* 原型环境忽略 */ });
    }
  });
})();
