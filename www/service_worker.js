const PRECACHE = 'precache-v1';
const RUNTIME = 'runtime';

const addResourcesToCache = async (resources) => {
  const cache = await caches.open(PRECACHE);
  await cache.addAll(resources);
};

const putToCache = async (cacheName, request, response) => {
  const cache = await caches.open(cacheName);
  return await cache.put(request, response);
}

const fetchAndPutToCache = async (cacheName, request) => {
  const response = await fetch(request)
  return await putToCache(cacheName, request, response)
}

const log = (location.host === "test.hololive.zone") ? console.log : () => {}

const CACHED_URLS = [
  "stats.json",
  "/resources/css/main.css",
  "/resources/css/toastify.min.css",
  "/resources/icons/calendar.svg",
  "/resources/icons/heart.svg",
  "/resources/icons/radio.svg",
  "/resources/js/main.js",
  "/resources/js/vue.min.js",
  "/resources/js/axios.min.js",
  "/resources/js/proper.min.js",
  "/resources/js/tippy.min.js",
  "/resources/js/toastify.min.js",
]

let CACHED_PROFILE_PICTURES = []

self.addEventListener("install", event => {
  log("Installing service worker")
  addResourcesToCache(CACHED_URLS)
  event.waitUntil(
    fetch("/stats.json")
      .then(response => response.json())
      .then(data => {
        log("Got the stats")
        log(data)
        for (let group in data.groups) {
          for (let talent of data.groups[group].members) {
            CACHED_PROFILE_PICTURES.push("/" + talent.image)
          }
        }

        addResourcesToCache(CACHED_PROFILE_PICTURES)
        log("Filled the caches")
      })
  )
})

// The activate handler takes care of cleaning up old caches.
self.addEventListener('activate', event => {
  const currentCaches = [PRECACHE, RUNTIME];
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return cacheNames.filter(cacheName => !currentCaches.includes(cacheName));
    }).then(cachesToDelete => {
      return Promise.all(cachesToDelete.map(cacheToDelete => {
        return caches.delete(cacheToDelete);
      }));
    }).then(() => {
      self.clients.claim()
      log("claimed")
    })
  );
});

self.addEventListener('fetch', event => {
  if (event.request.url.startsWith(self.location.origin)) {
    event.respondWith(
      caches.match(event.request).then(cachedResponse => {
        // Update stats.json and return cached one if offline
        if (event.request.url.endsWith("/stats.json")) {
          return fetch(event.request)
            .then(response => {
              log("Update stats")
              return fetchAndPutToCache(PRECACHE, event.request, response)
                .then(() => {return response})
            })
            .catch(() => { return cachedResponse })
        }

        // Return cached files
        if (cachedResponse) {
          return cachedResponse;
        }

        // Fetch and add to runtime cache if we haven't cached anything yet
        log("Caching: ", event.request.url)
        return fetchAndPutToCache(RUNTIME, event.request)
          .then(response => {return response})
      })
    );
  }
});
