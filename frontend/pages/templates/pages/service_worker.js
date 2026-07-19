const CACHE_NAME = "loup-garou-shell-v4";
const STATIC_ASSETS = [
  "/static/css/styles.css",
  "/static/images/favicon-wolf.png",
  "/static/images/favicon.svg",
  "/static/images/wolf-login.png"
];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || !url.pathname.startsWith("/static/")) return;
  const networkUpdate = fetch(event.request).then(async response => {
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      await cache.put(event.request, response.clone());
    }
    return response;
  });
  event.waitUntil(networkUpdate.catch(() => undefined));
  event.respondWith(caches.match(event.request).then(cached => cached || networkUpdate));
});
