// 네트워크 우선 · 실패하면 캐시 (오프라인일 때 마지막 화면).
// 같은 출처 GET만 캐시하고, 버전이 바뀌면 이전 캐시는 지운다.
const CACHE = 'odte-v2';
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== self.location.origin) return;
  e.respondWith(
    fetch(req).then(r => {
      if (r.ok) {
        const c = r.clone();
        e.waitUntil(caches.open(CACHE).then(k => k.put(req, c)).catch(() => {}));
      }
      return r;
    }).catch(() => caches.match(req))
  );
});
