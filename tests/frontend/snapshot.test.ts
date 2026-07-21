import { describe, expect, it } from 'vitest'
import demoSnapshot from '../../public/data/filmography.json'
import { snapshotSchema } from '../../src/domain/snapshot'
import { snapshotFixture } from './fixtures'

describe('snapshot schema', () => {
  it('accepts the public snapshot contract', () => {
    expect(snapshotSchema.parse(snapshotFixture)).toEqual(snapshotFixture)
  })

  it('accepts the committed public snapshot', () => {
    expect(snapshotSchema.parse(demoSnapshot).schemaVersion).toBe(1)
  })

  it('rejects unknown fields rather than leaking unpublished data', () => {
    expect(() =>
      snapshotSchema.parse({
        ...snapshotFixture,
        localNotesPath: '/private/film-notes',
      }),
    ).toThrow()
  })

  it('rejects scores that are not half-step values', () => {
    const invalid = structuredClone(snapshotFixture)
    invalid.watched[0].rating = 9.2

    expect(() => snapshotSchema.parse(invalid)).toThrow()
  })

  it('rejects local review paths and URLs with embedded credentials', () => {
    const localPath = structuredClone(snapshotFixture)
    localPath.watched[0].sourceUrl = '/Users/person/private-review.md'
    expect(() => snapshotSchema.parse(localPath)).toThrow()

    const credentialUrl = structuredClone(snapshotFixture)
    credentialUrl.watched[0].sourceUrl = 'https://token@example.test/review'
    expect(() => snapshotSchema.parse(credentialUrl)).toThrow()
  })

  it('keeps recommendation sources in their matching collections', () => {
    const invalid = structuredClone(snapshotFixture)
    invalid.deterministicDiscoveries[0].source = 'ai'

    expect(() => snapshotSchema.parse(invalid)).toThrow()
  })

  it('treats a missing year as a wildcard when excluding discoveries', () => {
    const invalid = structuredClone(snapshotFixture)
    invalid.watched[0].tmdbId = null
    invalid.watched[0].title = 'My Neighbor Totoro'
    invalid.watched[0].year = null

    expect(() => snapshotSchema.parse(invalid)).toThrow(/already watched/i)
  })

  it('rejects the same film across watched and watchlist collections', () => {
    const invalid = structuredClone(snapshotFixture)
    invalid.watchlist[0] = {
      ...invalid.watchlist[0],
      tmdbId: null,
      title: invalid.watched[0].title,
      year: null,
    }

    expect(() => snapshotSchema.parse(invalid)).toThrow(/watched and watchlist/i)
  })
})
