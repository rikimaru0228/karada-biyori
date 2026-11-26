/* からだ日和：画面のファイルだけを保存して、通信できない時も開けるようにする。
   記録は IndexedDB にあり、ここでは扱わない（更新しても記録には触れない）。 */
const PREFIX = 'karada-shell-';   // からだ日和専用の名前。同じ公開元（github.io）の他のアプリのキャッシュには触れない
const CACHE = PREFIX + 'v1.1.0';
const SHELL = ['./', './index.html', './manifest.webmanifest', './icons/icon-180.png', './icons/icon-192.png', './icons/icon-512.png'];
self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener('activate', e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith(PREFIX) && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== location.origin) return; // 天気の問い合わせなどは通常どおり
  e.respondWith(fetch(e.request).then(r => { const copy = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); return r; })
    .catch(() => caches.match(e.request).then(r => r || caches.match('./index.html'))));
});
