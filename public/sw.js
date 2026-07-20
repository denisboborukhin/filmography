/* global self, caches, fetch, Request, URL */

const CACHE_PREFIX = 'filmography-'
const SHELL_CACHE = `${CACHE_PREFIX}shell-v1`
const POSTER_CACHE = `${CACHE_PREFIX}posters-v1`
const MAX_POSTERS = 80
const NETWORK_TIMEOUT_MS = 4000
const scopeUrl = new URL(self.registration.scope)

function scopedUrl(path) {
  return new URL(path, scopeUrl).toString()
}

async function fetchAndCache(cache, input) {
  try {
    const request = new Request(input, { cache: 'reload' })
    const response = await fetch(request)
    if (response.ok) {
      await cache.put(request, response.clone())
    }
    return response
  } catch {
    return undefined
  }
}

async function cacheApplicationShell() {
  const cache = await caches.open(SHELL_CACHE)
  const homeResponse = await fetchAndCache(cache, scopeUrl)

  if (homeResponse?.ok) {
    const html = await homeResponse.text()
    const assetUrls = [...html.matchAll(/(?:src|href)=["']([^"']+)["']/g)]
      .map((match) => new URL(match[1], scopeUrl))
      .filter((url) => url.origin === scopeUrl.origin && url.pathname.startsWith(scopeUrl.pathname))
      .map((url) => url.toString())

    await Promise.allSettled(assetUrls.map((url) => fetchAndCache(cache, url)))
  }

  const stableAssets = [
    'manifest.webmanifest',
    'icon.svg',
    'icon-maskable.svg',
    'icon-192.png',
    'icon-512.png',
    'icon-maskable-512.png',
    'tmdb-logo.svg',
    'data/filmography.json',
  ]
  await Promise.allSettled(stableAssets.map((path) => fetchAndCache(cache, scopedUrl(path))))
}

self.addEventListener('install', (event) => {
  event.waitUntil(cacheApplicationShell().finally(() => self.skipWaiting()))
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter(
              (key) =>
                key.startsWith(CACHE_PREFIX) && key !== SHELL_CACHE && key !== POSTER_CACHE,
            )
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  )
})

async function trimCache(cacheName, maximumEntries) {
  const cache = await caches.open(cacheName)
  const keys = await cache.keys()
  if (keys.length > maximumEntries) {
    await cache.delete(keys[0])
    await trimCache(cacheName, maximumEntries)
  }
}

async function storeResponse(cache, request, response) {
  try {
    await cache.put(request, response.clone())
    return true
  } catch {
    return false
  }
}

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName)
  const cached = await cache.match(request)
  if (cached) return cached

  const response = await fetch(request)
  if (response.ok || response.type === 'opaque') {
    const stored = await storeResponse(cache, request, response)
    if (stored && cacheName === POSTER_CACHE) await trimCache(POSTER_CACHE, MAX_POSTERS)
  }
  return response
}

async function fetchWithTimeout(request, timeoutMs = NETWORK_TIMEOUT_MS) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)

  try {
    return await fetch(request, { signal: controller.signal })
  } finally {
    clearTimeout(timeout)
  }
}

async function networkFirst(request, fallbackUrl) {
  const cache = await caches.open(SHELL_CACHE)
  try {
    const response = await fetchWithTimeout(request)
    if (response.ok) {
      await storeResponse(cache, request, response)
      return response
    }

    const cached = await cache.match(request)
    if (cached) return cached
    if (fallbackUrl) {
      const fallback = await cache.match(fallbackUrl)
      if (fallback) return fallback
    }
    return response
  } catch {
    const cached = await cache.match(request)
    if (cached) return cached
    if (fallbackUrl) {
      const fallback = await cache.match(fallbackUrl)
      if (fallback) return fallback
    }
    return Response.error()
  }
}

async function cachedShell(request) {
  const cache = await caches.open(SHELL_CACHE)
  const matchOptions = { ignoreVary: true }
  const cached =
    (await cache.match(request, matchOptions)) ??
    (await cache.match(scopeUrl, matchOptions))
  return cached ?? networkFirst(request, scopeUrl)
}

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  if (request.mode === 'navigate') {
    event.respondWith(cachedShell(request))
    return
  }

  if (url.origin === scopeUrl.origin && url.pathname.endsWith('/data/filmography.json')) {
    event.respondWith(networkFirst(request))
    return
  }

  if (url.origin === scopeUrl.origin && url.pathname.startsWith(scopeUrl.pathname)) {
    event.respondWith(cacheFirst(request, SHELL_CACHE))
    return
  }

  if (request.destination === 'image') {
    event.respondWith(cacheFirst(request, POSTER_CACHE))
  }
})
