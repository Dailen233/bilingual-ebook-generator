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
    task: 'v2_task_v1',      // 旧单任务键（仅用于迁移）
    tasks: 'v2_tasks_v1',    // 新任务集合键
    library: 'v2_library_v1',
    readerPref: 'v3_reader_pref_v1'
  };

  // 默认示例用户 / 管理员（原型演示用，模拟登录）
  var DEMO_USER = { name: '林一舟', mail: 'yizhou@example.com', role: 'user' };
  var DEMO_ADMIN = { name: '管理员', mail: 'admin@example.com', role: 'admin' };

  // ---- AI 翻译配置（集中配置 · 原型演示，尚未接入真实 API） ----
  // 普通用户页面不收集 API Key。选项依据各家官方文档：
  // - 有道智云文本翻译：请求参数为 q/from/to/appKey/salt/sign 等，官方 API 未提供模型选择
  //   （见 ai.youdao.com 文本翻译 API 文档），故不配置模型选项。
  // - DeepL 翻译：官方 API 提供 model_type 参数，取值 quality_optimized /
  //   prefer_quality_optimized / latency_optimized（见 developers.deepl.com
  //   translate 请求文档），按官方取值列出。
  // 翻译风格为本产品的偏好演示（应用层设定），不代表各服务原生支持该选项。
  var AI_TRANSLATE = {
    services: [
      { id: 'youdao-text', name: '有道智云文本翻译',
        note: '官方文本翻译 API 未提供模型选择（原型演示，尚未接入）',
        models: [] },
      { id: 'deepl', name: 'DeepL 翻译',
        note: '官方 API 提供 model_type 参数（原型演示，尚未接入）',
        models: [
          { id: 'quality_optimized', name: '质量优先（quality_optimized）' },
          { id: 'prefer_quality_optimized', name: '倾向质量优先（prefer_quality_optimized）' },
          { id: 'latency_optimized', name: '低延迟优先（latency_optimized）' }
        ] }
    ],
    styles: [
      { id: 'faithful', name: '忠实原文', desc: '尽量贴近原文结构与用词，不增删。' },
      { id: 'literary', name: '文学表达', desc: '译文更符合目标语言的文学语感。' },
      { id: 'term',      name: '术语一致', desc: '优先保持专有名词与术语前后统一。' }
    ]
  };

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
  function clearUser() { localStorage.removeItem(K.user); }
  function clearAdmin() { localStorage.removeItem(K.admin); }

  // ---- 任务集合（模拟：带稳定 taskId，支持并发多任务） ----
  // 兼容旧存储：v2_task_v1 单任务在首次读取时迁移进 v2_tasks_v1 数组。
  function readTasks() {
    var arr = read(K.tasks, null);
    if (arr == null) {
      var legacy = read(K.task, null);
      if (legacy && !Array.isArray(legacy)) {
        if (!legacy.id) legacy.id = 't_legacy';
        arr = [legacy];
      } else if (Array.isArray(legacy)) {
        arr = legacy;
      } else {
        arr = [];
      }
      write(K.tasks, arr);
      try { localStorage.removeItem(K.task); } catch (e) {}
    }
    return arr;
  }
  function writeTasks(arr) { write(K.tasks, arr); }
  function uid(prefix) {
    return prefix + '_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  }
  function createTask(fields) {
    var arr = readTasks();
    var id = uid('t');
    var t = Object.assign({
      id: id, state: 'running', cur: 0, total: 500, durMs: 9000,
      failedCount: 0, startedAt: Date.now(), updatedAt: Date.now()
    }, fields, { id: id });
    arr.unshift(t);
    writeTasks(arr);
    return t;
  }
  function getTask(id) {
    var arr = readTasks();
    if (id) {
      for (var i = 0; i < arr.length; i++) if (arr[i].id === id) return arr[i];
      return null;
    }
    return arr[0] || null;
  }
  function updateTask(id, patch) {
    var arr = readTasks();
    for (var i = 0; i < arr.length; i++) {
      if (arr[i].id === id) {
        arr[i] = Object.assign({}, arr[i], patch);
        writeTasks(arr);
        return arr[i];
      }
    }
    return null;
  }
  function getRunningTasks() {
    return readTasks().filter(function (t) { return t.state === 'running'; });
  }
  function getFailedTasks() {
    return readTasks().filter(function (t) { return t.state === 'failed'; });
  }

  // ---- 进度：按 wall-clock 确定性计算（多标签页重复读取不累加） ----
  function progressOf(t, now) {
    if (!t) return 0;
    if (t.state !== 'running') return t.cur || 0;
    now = now || Date.now();
    var per = (t.durMs || 9000) / (t.total || 500);
    var elapsed = Math.max(0, now - (t.startedAt || now));
    return Math.min(t.total, Math.floor(elapsed / per));
  }
  // 完成入库：幂等（按 taskId 去重），成果通过 taskId/bookId 关联
  function ensureLibraryBook(t) {
    var lib = read(K.library, []);
    for (var i = 0; i < lib.length; i++) if (lib[i].taskId === t.id) return lib[i];
    var book = {
      id: 'b_' + t.id,
      taskId: t.id,
      name: t.name, src: t.src, tgt: t.tgt,
      service: t.service, serviceName: t.serviceName,
      model: t.model, modelName: t.modelName,
      style: t.style, styleName: t.styleName,
      failedCount: t.failedCount || 0,
      time: new Date().toLocaleString('zh-CN'),
      status: 'done'
    };
    lib.unshift(book);
    write(K.library, lib);
    return book;
  }
  // 推进所有进行中任务到 done（确定性、幂等）；返回任务数组
  function advanceTasks(now) {
    now = now || Date.now();
    var arr = readTasks();
    var changed = false;
    arr.forEach(function (t) {
      if (t.state !== 'running') return;
      var cur = progressOf(t, now);
      if (cur !== t.cur) { t.cur = cur; changed = true; }
      if (t.cur >= t.total) {
        t.cur = t.total;
        t.state = 'done';
        t.updatedAt = now;
        if (!t.failedCount) t.failedCount = 1; // 示例：含 1 个失败单元（与结果/阅读示例一致）
        var book = ensureLibraryBook(t);
        t.bookId = book.id;
        changed = true;
      } else {
        t.updatedAt = now;
      }
    });
    if (changed) writeTasks(arr);
    return arr;
  }

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

  // ---- 管理员端登录态路由（模拟；真实权限由服务端校验，见管理页说明） ----
  // 管理页未登录管理员 → 管理登录页；管理登录页已登录管理员 → 后台；退出只清管理员态。
  var ADMIN_PAGES = ['admin.html', 'admin-tasks.html', 'admin-reviews.html'];
  function adminCurrentFile() {
    return location.pathname.split('/').pop() || 'index.html';
  }
  function adminRouteGuard() {
    var here = adminCurrentFile();
    if (here === 'admin-login.html') {
      if (isAdmin()) { location.replace('admin.html'); return true; }
    } else if (ADMIN_PAGES.indexOf(here) !== -1) {
      if (!isAdmin()) { location.replace('admin-login.html'); return true; }
    }
    return false;
  }
  window.adminLogout = function () {
    clearAdmin(); // 只清管理员态，不误清普通用户态
    location.replace('admin-login.html');
    return false;
  };
  adminRouteGuard();
  window.addEventListener('storage', adminRouteGuard);
  window.addEventListener('pageshow', adminRouteGuard);

  // ---- 暴露给页面（v2 命名保留，v3 增量见 V3） ----
  window.V2 = {
    K: K, read: read, write: write,
    isUser: isUser, isAdmin: isAdmin,
    setUser: setUser, setAdmin: setAdmin, clearAuth: clearAuth,
    clearUser: clearUser, clearAdmin: clearAdmin,
    getTasks: readTasks, getTask: getTask, createTask: createTask,
    updateTask: updateTask, getRunningTasks: getRunningTasks, getFailedTasks: getFailedTasks,
    advanceTasks: advanceTasks, progressOf: progressOf, ensureLibraryBook: ensureLibraryBook,
    DEMO_USER: DEMO_USER, DEMO_ADMIN: DEMO_ADMIN,
    requireUser: requireUser, requireAdmin: requireAdmin
  };
  window.AI_TRANSLATE = AI_TRANSLATE;
  window.V3 = {
    getReaderPref: getReaderPref, setReaderPref: setReaderPref, setRing: setRing,
    AI: AI_TRANSLATE
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
