/**
 * Service Worker for VidyaBot PWA
 * Enables offline-first functionality with caching strategies
 */

const CACHE_VERSION = 'vidyabot-v1';
const CACHE_URLS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/css/style.css',
  '/js/app.js',
  '/js/api.js',
  '/js/ui.js'
];

// Install event - cache app shell
self.addEventListener('install', event => {
  console.log('Service Worker installing...');
  
  event.waitUntil(
    caches.open(CACHE_VERSION).then(cache => {
      console.log('Caching app shell');
      return cache.addAll(CACHE_URLS)
        .catch(err => console.warn('Some files could not be cached:', err));
    })
  );
  
  self.skipWaiting();
});

// Activate event - clean up old caches
self.addEventListener('activate', event => {
  console.log('Service Worker activating...');
  
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames
          .filter(name => name !== CACHE_VERSION)
          .map(name => {
            console.log('Deleting old cache:', name);
            return caches.delete(name);
          })
      );
    })
  );
  
  self.clients.claim();
});

// Fetch event - network-first for API, cache-first for assets
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // API calls: network-first with cache fallback
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(request)
        .then(response => {
          // Cache successful responses
          if (response.ok) {
            const cache_clone = response.clone();
            caches.open(CACHE_VERSION).then(cache => {
              cache.put(request, cache_clone);
            });
          }
          return response;
        })
        .catch(() => {
          // Network failed, try cache
          return caches.match(request)
            .then(cached => {
              if (cached) {
                console.log('Using cached API response for:', url.pathname);
                return cached;
              }
              // No cache available
              return new Response(
                JSON.stringify({
                  error: 'offline',
                  message: 'You are offline and this API call has not been cached.'
                }),
                {
                  status: 503,
                  statusText: 'Service Unavailable',
                  headers: { 'Content-Type': 'application/json' }
                }
              );
            });
        })
    );
    return;
  }

  // Static assets: cache-first with network fallback
  event.respondWith(
    caches.match(request)
      .then(cached => cached || fetch(request))
      .then(response => {
        // Cache new responses
        if (response && response.status === 200) {
          const cache_clone = response.clone();
          caches.open(CACHE_VERSION).then(cache => {
            cache.put(request, cache_clone);
          });
        }
        return response;
      })
      .catch(() => {
        // Fallback to offline page if available
        return caches.match('/index.html');
      })
  );
});

// Background sync for offline queries (future enhancement)
self.addEventListener('sync', event => {
  if (event.tag === 'sync-queries') {
    event.waitUntil(
      // Sync cached queries when back online
      Promise.resolve()
    );
  }
});

console.log('Service Worker loaded');
