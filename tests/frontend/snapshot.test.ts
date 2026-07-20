import { describe, expect, it } from 'vitest'
import { snapshotSchema } from '../../src/domain/snapshot'
import { snapshotFixture } from './fixtures'

describe('snapshot schema', () => {
  it('accepts the public snapshot contract', () => {
    expect(snapshotSchema.parse(snapshotFixture)).toEqual(snapshotFixture)
  })

  it('rejects unknown fields rather than leaking unpublished data', () => {
    expect(() =>
      snapshotSchema.parse({
        ...snapshotFixture,
        localVaultPath: '/private/film-notes',
      }),
    ).toThrow()
  })

  it('rejects scores that are not half-step values', () => {
    const invalid = structuredClone(snapshotFixture)
    invalid.watched[0].rating = 9.2

    expect(() => snapshotSchema.parse(invalid)).toThrow()
  })

  it('keeps recommendation sources in their matching collections', () => {
    const invalid = structuredClone(snapshotFixture)
    invalid.deterministicDiscoveries[0].source = 'ai'

    expect(() => snapshotSchema.parse(invalid)).toThrow()
  })
})
