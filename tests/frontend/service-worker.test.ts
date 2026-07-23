import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { describe, expect, it, vi } from 'vitest'

const scope = 'https://example.test/filmography/'
const workerSource = readFileSync(new URL('../../public/sw.js', import.meta.url), 'utf-8')

interface RequestStub {
  method: string
  mode: string
  url: string
  destination: string
}

interface FetchEventStub {
  request: RequestStub
  respondWith(response: Promise<Response>): void
}

function loadWorker(cachedUrls: Map<string, string>) {
  const listeners = new Map<string, (event: FetchEventStub) => void>()
  const fetchMock = vi.fn().mockRejectedValue(new TypeError('offline'))
  const cacheMatch = vi.fn(async (input: string | RequestStub) => {
    const url = typeof input === 'string' ? input : input.url
    const body = cachedUrls.get(url)
    return body === undefined ? undefined : new Response(body)
  })
  const cache = {
    match: cacheMatch,
    put: vi.fn(),
    keys: vi.fn().mockResolvedValue([]),
    delete: vi.fn(),
  }
  const open = vi.fn().mockResolvedValue(cache)

  runInNewContext(workerSource, {
    self: {
      registration: { scope },
      clients: { claim: vi.fn() },
      addEventListener: (
        name: string,
        listener: (event: FetchEventStub) => void,
      ) => listeners.set(name, listener),
    },
    caches: { open, keys: vi.fn().mockResolvedValue([]), delete: vi.fn() },
    fetch: fetchMock,
    Request,
    Response,
    URL,
    AbortController,
    setTimeout,
    clearTimeout,
  })

  return { listeners, fetchMock, cacheMatch, open }
}

async function dispatchFetch(
  listener: (event: FetchEventStub) => void,
  request: RequestStub,
): Promise<Response> {
  let responsePromise: Promise<Response> | undefined
  listener({
    request,
    respondWith: (response) => {
      responsePromise = response
    },
  })
  if (!responsePromise) throw new Error('service worker did not respond to request')
  return responsePromise
}

describe('service worker offline routing', () => {
  it('tries the network for navigation before falling back to the cached shell', async () => {
    const worker = loadWorker(new Map([[scope, '<main>cached journal</main>']]))
    const listener = worker.listeners.get('fetch')
    expect(listener).toBeDefined()

    const response = await dispatchFetch(listener!, {
      method: 'GET',
      mode: 'navigate',
      url: scope,
      destination: 'document',
    })

    expect(await response.text()).toContain('cached journal')
    expect(worker.open).toHaveBeenCalledWith('filmography-shell-v1')
    expect(worker.fetchMock).toHaveBeenCalled()
  })

  it('uses the shell cache for same-origin images before the poster cache', async () => {
    const iconUrl = `${scope}icon.svg`
    const worker = loadWorker(new Map([[iconUrl, '<svg></svg>']]))
    const listener = worker.listeners.get('fetch')

    const response = await dispatchFetch(listener!, {
      method: 'GET',
      mode: 'cors',
      url: iconUrl,
      destination: 'image',
    })

    expect(await response.text()).toBe('<svg></svg>')
    expect(worker.open).toHaveBeenCalledWith('filmography-shell-v1')
    expect(worker.open).not.toHaveBeenCalledWith('filmography-posters-v1')
  })
})
