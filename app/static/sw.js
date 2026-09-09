/* Minimal offline shell: caches static assets only (never media or API). */
const CACHE = 'soa-edm-v1';
const ASSETS = ['/static/app.css', '/static/app.js', '/static/share.js', '/static/icon-192.png', '/static/icon-512.png', '/manifest.webmanifest'];
self.addEventListener('install', (e) => { e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).catch(() => {})); self.skipWaiting(); });
self.addEventListener('activate', (e) => { e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))); });
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || !url.pathname.startsWith('/static/')) return;
  e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));
});
