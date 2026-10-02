// 앱 설치(PWA)용 서비스 워커. 항상 네트워크를 먼저 쓰고, 오프라인일 때만 저장해 둔 화면 껍데기를 보여준다.
// 암호화된 데이터(data.enc.json)와 GitHub API 요청은 저장하지 않는다.
const CACHE = 'real-ops-shell-v1';
const SHELL = ['./', './index.html', './icon.svg', './icon-192.png', './manifest.webmanifest'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin || url.pathname.endsWith('data.enc.json')) return;
  e.respondWith(fetch(e.request).then(res => {
    if (res.ok && (e.request.mode === 'navigate' || /\.(css|js|png|svg|webmanifest)$/.test(url.pathname))) {
      const copy = res.clone();
      caches.open(CACHE).then(c => c.put(e.request, copy));
    }
    return res;
  }).catch(() => caches.match(e.request, { ignoreSearch: true }).then(r => r || caches.match('./index.html'))));
});
