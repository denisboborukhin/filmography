import { useCallback, useEffect, useState } from 'react'
import type { LoadedSnapshot } from '../domain/snapshot'
import { loadSnapshot } from '../lib/snapshot-loader'

type SnapshotState =
  | { status: 'loading'; result: null; error: null }
  | { status: 'ready'; result: LoadedSnapshot; error: null }
  | { status: 'error'; result: null; error: string }

export function useSnapshot() {
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState<SnapshotState>({
    status: 'loading',
    result: null,
    error: null,
  })

  useEffect(() => {
    const controller = new AbortController()

    void loadSnapshot(controller.signal)
      .then((result) => {
        setState({ status: 'ready', result, error: null })
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setState({
            status: 'error',
            result: null,
            error: error instanceof Error ? error.message : 'The film journal could not be loaded.',
          })
        }
      })

    return () => controller.abort()
  }, [attempt])

  const retry = useCallback(() => {
    setState({ status: 'loading', result: null, error: null })
    setAttempt((current) => current + 1)
  }, [])

  return { ...state, retry }
}
