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

  it('supplies empty credits for an older snapshot', () => {
    const legacy = structuredClone(snapshotFixture) as unknown as {
      watched: Array<{ credits?: unknown }>
    }
    delete legacy.watched[0].credits

    expect(snapshotSchema.parse(legacy).watched[0].credits).toEqual({
      cast: [],
      filmmaker: null,
    })
  })

  it('rejects unknown fields rather than leaking unpublished data', () => {
    expect(() =>
      snapshotSchema.parse({
        ...snapshotFixture,
        localNotesPath: '/private/film-notes',
      }),
    ).toThrow()
  })

  it('rejects scores that are not tenth-step values', () => {
    const valid = structuredClone(snapshotFixture)
    valid.watched[0].rating = 9.2
    expect(snapshotSchema.parse(valid).watched[0].rating).toBe(9.2)

    const invalid = structuredClone(snapshotFixture)
    invalid.watched[0].rating = 9.25

    expect(() => snapshotSchema.parse(invalid)).toThrow()
  })

  it('keeps expected-score provenance consistent', () => {
    const missingWatchlistScore = structuredClone(snapshotFixture)
    missingWatchlistScore.watchlist[0].interest = null
    missingWatchlistScore.watchlist[0].interestSource = 'ai'
    expect(() => snapshotSchema.parse(missingWatchlistScore)).toThrow()

    const localAiScore = structuredClone(snapshotFixture)
    localAiScore.aiDiscoveries[0].scoreSource = 'local'
    expect(() => snapshotSchema.parse(localAiScore)).toThrow()
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

  it('rejects TV series in movie recommendation collections', () => {
    const invalid = structuredClone(snapshotFixture)
    Object.assign(invalid.deterministicDiscoveries[0], { mediaType: 'tv' })

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

  it('does not collapse movie and TV records that share a TMDB ID', () => {
    const valid = structuredClone(snapshotFixture)
    valid.watchlist[0] = {
      ...valid.watchlist[0],
      tmdbId: valid.watched[0].tmdbId,
      mediaType: 'tv',
      title: valid.watched[0].title,
      year: valid.watched[0].year,
    }

    expect(snapshotSchema.parse(valid).watchlist[0].mediaType).toBe('tv')
  })
})
