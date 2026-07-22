// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { snapshotFixture } from './fixtures'

vi.mock('../../src/hooks/useSnapshot', () => ({
  useSnapshot: () => ({
    status: 'success',
    result: { snapshot: snapshotFixture, warning: null },
    error: '',
    retry: vi.fn(),
  }),
}))

import { App } from '../../src/App'

beforeEach(() => {
  window.location.hash = '#watched'
})

afterEach(() => {
  cleanup()
  window.location.hash = ''
})

it('keeps the current view when the skip link changes the fragment', () => {
  render(<App />)
  expect(screen.getByRole('heading', { name: /^Watched/ })).toBeInTheDocument()

  window.location.hash = '#main-content'
  window.dispatchEvent(new HashChangeEvent('hashchange'))

  expect(screen.getByRole('heading', { name: /^Watched/ })).toBeInTheDocument()
})
