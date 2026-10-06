/* ============================================================
   v4 原型 · Service Worker（离线 shell）
   策略：导航与静态资源均 network-first（在线总是拿最新文件并回填缓存；
        离线回退缓存）。
   离线范围：下方 CORE 预缓存的页面壳（HTML/CSS/JS/图标/字体）+
        运行时访问过的同源资源。断网可重访已访问过的上述页面。
   离线不可用：未访问过的页面（回退缓存首页）、真实业务数据
        （登录/任务/书库/翻译均为模拟，不落库）。
   激活只清理「译伴」（yiban- 前缀）自己的旧缓存，不动同源其他应用缓存。
   规则：修改本目录 js/css/资源列表后必须升版 CACHE 名。
   ============================================================ */

var CACHE = 'yiban-v4-shell-v8';
var CORE = [
  // 页面
  './index.html', './login.html', './register.html',
  './dashboard.html', './library.html', './new-task.html',
  './task-detail.html', './reader.html',
  './admin.html', './admin-login.html', './admin-tasks.html', './admin-reviews.html',
  // 共享样式与脚本
  './styles.css', './pages.css', './topbar.css', './topbar.js', './app.js',
  // 页面专属样式
  './login.css', './dashboard.css', './admin.css', './admin-login.css', './admin-tasks.css',
  // 清单与图标
  './manifest.webmanifest', './icons/icon-192.png', './icons/icon-512.png',
  // 品牌/标题字体（产品页引用）
  './assets/fonts/lxgw-wenkai-mark.woff2',
  './assets/fonts/lxgw-wenkai-login.woff2',
  './assets/fonts/noto-serif-sc-semibold.woff2',
  './assets/fonts/noto-sans-sc-regular.woff2',
  './assets/fonts/mashanzheng-title.woff2'
];

self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE).then(function (cache) {
      // 逐条缓存并容错：单个资源失效不阻断整体安装（避免 addAll 因单个 404 全盘失败）
      return Promise.all(CORE.map(function (url) {
        return cache.add(url).catch(function () { /* 跳过失效项 */ });
      }));
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys
        .filter(function (k) { return k.indexOf('yiban-') === 0 && k !== CACHE; })
        .map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (e) {
  var req = e.request;
  if (req.method !== 'GET') return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // 导航请求：网络优先，失败回退缓存（离线回退首页）
  if (req.mode === 'navigate') {
    e.respondWith(
      fetch(req).then(function (res) {
        var copy = res.clone();
        caches.open(CACHE).then(function (c) { c.put(req, copy); });
        return res;
      }).catch(function () {
        return caches.match(req).then(function (hit) {
          return hit || caches.match('./index.html');
        });
      })
    );
    return;
  }

  // 静态资源：网络优先 + 回填缓存，离线回退缓存
  e.respondWith(
    fetch(req).then(function (res) {
      if (res && res.status === 200) {
        var copy = res.clone();
        caches.open(CACHE).then(function (c) { c.put(req, copy); });
      }
      return res;
    }).catch(function () {
      return caches.match(req);
    })
  );
});
