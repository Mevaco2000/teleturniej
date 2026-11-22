/* Service worker działa tylko przez HTTPS lub na localhost. Sieć ma pierwszeństwo, żeby po
   aktualizacji serwera telefon nie został ze starą wersją, a pamięć podręczna pozwala otworzyć
   aplikację, gdy serwer jest chwilowo niedostępny. */
var CACHE = "teleturniej-v4";
var SHELL = [
  "/app/",
  "/app/app.css",
  "/app/app.js",
  "/app/manifest.webmanifest",
  "/app/icons/icon-192.png",
  "/app/icons/icon-512.png",
  "/shared/core.js",
  "/shared/fonts.css"
];

self.addEventListener("install", function (event) {
  event.waitUntil(caches.open(CACHE).then(function (cache) {
    return cache.addAll(SHELL);
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (event) {
  event.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener("fetch", function (event) {
  var url = new URL(event.request.url);
  var inShell = url.pathname.indexOf("/app/") === 0 || url.pathname.indexOf("/shared/") === 0;
  if (event.request.method !== "GET" || url.origin !== location.origin || !inShell) return;
  event.respondWith(fetch(event.request).then(function (response) {
    // Każdy kod QR ma inny adres (?r=KOD), a strona jest ta sama, więc pamiętamy ją bez kodu.
    if (response.ok) {
      var copy = response.clone();
      caches.open(CACHE).then(function (cache) { cache.put(url.origin + url.pathname, copy); });
    }
    return response;
  }).catch(function () {
    return caches.match(event.request, { ignoreSearch: true }).then(function (hit) {
      return hit || caches.match("/app/");
    });
  }));
});
