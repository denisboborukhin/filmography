import { z } from 'zod'

const yearSchema = z.number().int().min(1878).max(2200).nullable()
const scoreSchema = z.number().min(0).max(10).multipleOf(0.5)
const optionalScoreSchema = scoreSchema.nullable()
const nullableTextSchema = z.string().trim().nullable()
const dateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable()
const dateTimeSchema = z.string().datetime({ offset: true })
const stringListSchema = z
  .array(z.string().trim().min(1))
  .refine(
    (values) => new Set(values.map((value) => value.toLocaleLowerCase())).size === values.length,
    'Values must be unique',
  )

export const filmSchema = z
  .object({
    tmdbId: z.number().int().positive().nullable(),
    title: z.string().trim().min(1),
    originalTitle: nullableTextSchema,
    year: yearSchema,
    releaseDate: dateSchema,
    posterUrl: nullableTextSchema,
    overview: z.string().trim(),
    genres: stringListSchema,
    voteAverage: z.number().min(0).max(10).nullable(),
    popularity: z.number().min(0).nullable(),
  })
  .strict()

export const watchedFilmSchema = filmSchema
  .extend({
    rating: scoreSchema,
    watchedAt: dateSchema,
    tags: stringListSchema,
    review: z.string().trim(),
    sourceUrl: nullableTextSchema,
  })
  .strict()

export const watchlistFilmSchema = filmSchema
  .extend({
    interest: optionalScoreSchema,
    notes: z.string().trim(),
    tags: stringListSchema,
    dismissed: z.boolean(),
  })
  .strict()

export const recommendationSchema = filmSchema
  .extend({
    tmdbId: z.number().int().positive(),
    predictedRating: scoreSchema,
    rationale: z.string().trim().min(1),
    source: z.enum(['deterministic', 'ai']),
    provider: nullableTextSchema,
    model: nullableTextSchema,
    generatedAt: dateTimeSchema,
  })
  .strict()
  .superRefine((recommendation, context) => {
    if (
      recommendation.source === 'deterministic' &&
      (recommendation.provider !== null || recommendation.model !== null)
    ) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Deterministic recommendations cannot include an AI provider or model',
        path: ['provider'],
      })
    }
    if (recommendation.source === 'ai' && (!recommendation.provider || !recommendation.model)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'AI recommendations require a provider and model',
        path: ['provider'],
      })
    }
  })

export const snapshotSchema = z
  .object({
    schemaVersion: z.literal(1),
    generatedAt: dateTimeSchema,
    recommendationsGeneratedAt: dateTimeSchema.nullable(),
    watched: z.array(watchedFilmSchema),
    watchlist: z.array(watchlistFilmSchema),
    deterministicDiscoveries: z.array(recommendationSchema),
    aiDiscoveries: z.array(recommendationSchema),
  })
  .strict()
  .superRefine((snapshot, context) => {
    snapshot.deterministicDiscoveries.forEach((recommendation, index) => {
      if (recommendation.source !== 'deterministic') {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Deterministic discoveries must use the deterministic source',
          path: ['deterministicDiscoveries', index, 'source'],
        })
      }
    })

    snapshot.aiDiscoveries.forEach((recommendation, index) => {
      if (recommendation.source !== 'ai') {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'AI discoveries must use the ai source',
          path: ['aiDiscoveries', index, 'source'],
        })
      }
    })
  })

export type Film = z.infer<typeof filmSchema>
export type WatchedFilm = z.infer<typeof watchedFilmSchema>
export type WatchlistFilm = z.infer<typeof watchlistFilmSchema>
export type Recommendation = z.infer<typeof recommendationSchema>
export type FilmographySnapshot = z.infer<typeof snapshotSchema>

export type SnapshotLoadSource = 'network' | 'cache-storage' | 'local-storage'

export interface LoadedSnapshot {
  snapshot: FilmographySnapshot
  source: SnapshotLoadSource
  warning: string | null
}
