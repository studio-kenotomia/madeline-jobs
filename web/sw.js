const SHELL = "jr-shell-v1";
const DATA = "jr-data-v1";
const ASSETS = ["./", "index.html", "app.css", "app.js", "ui.js", "store.js", "icons.js", "crypto.js", "studio.js", "unlock.js", "vendor/editor.js", "manifest.webmanifest",
  "art/thessaloniki.jpg", "art/greece.jpg", "art/remote.jpg", "icons/icon-192.png", "icons/icon-512.png"];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(SHELL).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => ![SHELL, DATA].includes(k)).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== location.origin) return;
  const path = url.pathname;
  const isData = /feed\.json$|private\.enc$|\/files\//.test(path);
  const isMedia = /\/media\/|\/art\//.test(path);
  if (isData) {
    event.respondWith(fetch(event.request).then(response => {
      const copy = response.clone();
      caches.open(DATA).then(cache => cache.put(path, copy));
      return response;
    }).catch(() => caches.open(DATA).then(cache => cache.match(path))));
    return;
  }
  if (isMedia) {
    event.respondWith(caches.open(DATA).then(cache => cache.match(event.request).then(hit => hit || fetch(event.request).then(response => { cache.put(event.request, response.clone()); return response; }))));
    return;
  }
  event.respondWith(fetch(event.request).then(response => {
    const copy = response.clone();
    caches.open(SHELL).then(cache => cache.put(event.request, copy));
    return response;
  }).catch(() => caches.match(event.request)));
});
