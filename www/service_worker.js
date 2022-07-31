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
  "/resources/icons/heart-full.svg",
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

let FAVOURITES

const bc = new BroadcastChannel("sw")
bc.onmessage = event => {
  switch (event.data?.target) {
    case ("favourites"):
      FAVOURITES = event.data.data
      log("Update favourites to: ", FAVOURITES)
      break
    default:
      log("Received unknown message", event)
  }
}


let worker, stats, prevStats

const getMembers = function* (stats) {
  for (let groupName in stats.groups) {
    for (let talent of stats.groups[groupName].members) {
      yield talent
    }
  }
}

const mappedStats = stats => {
  const new_stats = {}
  for (let talent of getMembers(stats)) {
    new_stats[talent.twitter] = talent
  }
  return new_stats
}

const update = () => {
  fetch("/stats.json").then(response => response.json())
    .then(new_stats => {
      if (!prevStats) {
        prevStats = mappedStats(new_stats)
        return
      }

      stats = mappedStats(new_stats)

      for (let name in stats) {
        let talent = stats[name]
        if (FAVOURITES.includes(name) && talent?.video?.start === 0 && prevStats[name]?.video?.start !== 0) {
          self.registration.showNotification(`${talent.name} is live!`, {
            icon: talent.image,
            tag: name + "-isLive",
            data: {
              url: "https://youtu.be/" + talent.video.id,
            }
          })
        }
      }

      prevStats = stats
    })
}

// Notification click event listener
self.addEventListener('notificationclick', (e) => {
  // Close the notification popout
  e.notification.close();
  // Get all the Window clients
  e.waitUntil(clients.matchAll({ type: 'window' }).then((clientsArr) => {
    // If a Window tab matching the targeted URL already exists, focus that;
    const hadWindowToFocus = clientsArr.some((windowClient) => windowClient.url === e.notification.data.url ? (windowClient.focus(), true) : false);
    // Otherwise, open a new tab to the applicable URL and focus it.
    if (!hadWindowToFocus) clients.openWindow(e.notification.data.url).then((windowClient) => windowClient ? windowClient.focus() : null);
  }));
});

self.addEventListener("install", event => {
  log("Installing service worker")
  addResourcesToCache(CACHED_URLS)
  event.waitUntil(
    fetch("/stats.json")
      .then(response => response.json())
      .then(data => {
        log("Got the stats")
        stats = mappedStats(data)
        for (let group in data.groups) {
          for (let talent of data.groups[group].members) {
            CACHED_PROFILE_PICTURES.push("/" + talent.image)
          }
        }

        addResourcesToCache(CACHED_PROFILE_PICTURES)
        log("Filled the caches")
      })
  )

  worker = setInterval(update, 1000 * 3000)
  update()
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
            .catch(() => {return cachedResponse})
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
