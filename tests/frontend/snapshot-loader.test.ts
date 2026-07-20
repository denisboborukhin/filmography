// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  loadSnapshot,
  SNAPSHOT_STORAGE_KEY,
  SNAPSHOT_URL,
} from '../../src/lib/snapshot-loader'
import { snapshotFixture } from './fixtures'

describe('snapshot loader', () => {
  beforeEach(() => {
    const values = new Map<string, string>()
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      value: {
        clear: () => values.clear(),
        getItem: (key: string) => values.get(key) ?? null,
        removeItem: (key: string) => values.delete(key),
        setItem: (key: string, value: string) => values.set(key, value),
      },
    })
    vi.stubGlobal('fetch', vi.fn())
    Object.defineProperty(window, 'caches', {
      configurable: true,
      value: { match: vi.fn().mockResolvedValue(undefined) },
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('loads, validates, and remembers the published snapshot', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify(snapshotFixture), {
        headers: { 'Content-Type': 'application/json' },
        status: 200,
      }),
    )

    const result = await loadSnapshot()

    expect(fetch).toHaveBeenCalledWith(
      SNAPSHOT_URL,
      expect.objectContaining({ cache: 'no-cache' }),
    )
    expect(result).toEqual({ snapshot: snapshotFixture, source: 'network', warning: null })
    expect(JSON.parse(window.localStorage.getItem(SNAPSHOT_STORAGE_KEY) ?? '')).toEqual(
      snapshotFixture,
    )
  })

  it('uses the last valid local snapshot when the network and cache fail', async () => {
    window.localStorage.setItem(SNAPSHOT_STORAGE_KEY, JSON.stringify(snapshotFixture))
    vi.mocked(fetch).mockRejectedValue(new TypeError('offline'))

    const result = await loadSnapshot()

    expect(result.source).toBe('local-storage')
    expect(result.snapshot).toEqual(snapshotFixture)
    expect(result.warning).toMatch(/last journal saved/i)
  })

  it('does not use a saved snapshot that no longer satisfies the schema', async () => {
    window.localStorage.setItem(SNAPSHOT_STORAGE_KEY, JSON.stringify({ schemaVersion: 0 }))
    vi.mocked(fetch).mockRejectedValue(new TypeError('offline'))

    await expect(loadSnapshot()).rejects.toThrow(/no saved copy/i)
  })
})
