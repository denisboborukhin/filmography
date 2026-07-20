import { snapshotSchema, type FilmographySnapshot, type LoadedSnapshot } from '../domain/snapshot'

export const SNAPSHOT_URL = `${import.meta.env.BASE_URL}data/filmography.json`
export const SNAPSHOT_STORAGE_KEY = 'filmography:last-valid-snapshot:v1'

function validateSnapshot(value: unknown): FilmographySnapshot {
  return snapshotSchema.parse(value)
}

function readStoredSnapshot(): FilmographySnapshot | null {
  try {
    const stored = window.localStorage.getItem(SNAPSHOT_STORAGE_KEY)
    return stored ? validateSnapshot(JSON.parse(stored) as unknown) : null
  } catch {
    return null
  }
}

function rememberSnapshot(snapshot: FilmographySnapshot): void {
  try {
    window.localStorage.setItem(SNAPSHOT_STORAGE_KEY, JSON.stringify(snapshot))
  } catch {
    // Storage can be unavailable in private browsing. The current response is still usable.
  }
}

async function readResponse(response: Response): Promise<FilmographySnapshot> {
  if (!response.ok) {
    throw new Error(`Snapshot request failed with status ${response.status}`)
  }

  return validateSnapshot((await response.json()) as unknown)
}

async function readCacheStorage(): Promise<FilmographySnapshot | null> {
  if (!('caches' in window)) {
    return null
  }

  try {
    const response = await window.caches.match(SNAPSHOT_URL)
    return response ? await readResponse(response) : null
  } catch {
    return null
  }
}

export async function loadSnapshot(signal?: AbortSignal): Promise<LoadedSnapshot> {
  try {
    const response = await fetch(SNAPSHOT_URL, {
      cache: 'no-cache',
      headers: { Accept: 'application/json' },
      signal,
    })
    const snapshot = await readResponse(response)
    rememberSnapshot(snapshot)
    return { snapshot, source: 'network', warning: null }
  } catch (error) {
    if (signal?.aborted) {
      throw error
    }

    const cached = await readCacheStorage()
    if (cached) {
      rememberSnapshot(cached)
      return {
        snapshot: cached,
        source: 'cache-storage',
        warning: 'The network is unavailable. Showing the last cached journal.',
      }
    }

    const stored = readStoredSnapshot()
    if (stored) {
      return {
        snapshot: stored,
        source: 'local-storage',
        warning: 'The network is unavailable. Showing the last journal saved in this browser.',
      }
    }

    throw new Error(
      'The film journal could not be loaded, and this browser has no saved copy yet.',
      { cause: error },
    )
  }
}
