/* ============================================================
   v3 原型 · Service Worker（PWA 离线 shell，G10）
   策略：导航请求 network-first（回退缓存首页）；
        静态资源（css/js/图标/页面）cache-first + 运行时回填。
   说明：原型仅缓存 shell 以支持"可安装 + 断网打开已访问页"，
        不声称业务数据离线可用（数据均为模拟，不落库）。
   ============================================================ */

var CACHE = 'yiban-v3-shell-v1';
var CORE = [
  './index.html',
  './styles.css',
  './app.js',
  './manifest.webmanifest',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './login.html',
  './register.html',
  './dashboard.html',
  './library.html',
  './new-task.html',
  './task-detail.html',
  './reader.html',
  './admin.html',
  './admin-login.html',
  './admin-tasks.html',
  './admin-reviews.html'
];

self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE).then(function (c) { return c.addAll(CORE); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (e) {
  var req = e.request;
  if (req.method !== 'GET') return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // 导航请求：网络优先，失败回退缓存首页（离线可回到入口）
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

  // 静态资源：缓存优先 + 运行时回填
  e.respondWith(
    caches.match(req).then(function (hit) {
      if (hit) return hit;
      return fetch(req).then(function (res) {
        if (res && res.status === 200 && (res.type === 'basic' || res.type === 'cors')) {
          var copy = res.clone();
          caches.open(CACHE).then(function (c) { c.put(req, copy); });
        }
        return res;
      });
    })
  );
});
