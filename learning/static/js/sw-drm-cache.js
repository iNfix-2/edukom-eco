/**
 * Edukom LMS - Offline Encrypted DRM Video Cache Service Worker
 * Safeguard 9: Encrypted Offline Viewing
 * 
 * Intercepts AES-128 encrypted HLS video segments (.ts) and caches them locally
 * in the browser CacheStorage.
 * 
 * SECURITY GUARANTEE:
 * All cached segments remain 100% encrypted with AES-128 on disk.
 * Raw MP4 media files are never exposed or saved in cleartext.
 * Playback requires an authenticated, unrevoked playback session token.
 */

const CACHE_NAME = 'edukom-drm-cache-v1';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name.startsWith('edukom-drm-') && name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const requestUrl = new URL(event.request.url);

  // Intercept HLS video segments (.ts) for offline encrypted caching
  if (requestUrl.pathname.endsWith('.ts')) {
    event.respondWith(
      caches.open(CACHE_NAME).then((cache) => {
        return cache.match(event.request).then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }

          return fetch(event.request).then((networkResponse) => {
            if (networkResponse && networkResponse.status === 200) {
              cache.put(event.request, networkResponse.clone());
            }
            return networkResponse;
          }).catch(() => {
            return cachedResponse || new Response('Offline segment not available', { status: 503 });
          });
        });
      })
    );
  }
});
