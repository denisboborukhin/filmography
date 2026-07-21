# Markdown notes input format

Filmography reads two inputs: a directory containing one Markdown note per watched film, and one
Markdown note containing the watchlist. Review files are found recursively; hidden Markdown files
whose names start with `.` are skipped. Keep unrelated Markdown outside the configured directory.

## Review notes

The filename is the title fallback. A note may start with YAML frontmatter delimited by `---`. The
text after frontmatter becomes the public Markdown review; leading and trailing whitespace is
trimmed.

Minimal review note:

```markdown
---
date: "2026-07-21"
categories:
- "[[films resumes]]"
rating: 8.5
---

Your review text.
```

With that format, the film title comes from the filename, for example `Menu.md` or
`Perfect Days (2023).md`. The release year is optional in the filename, and TMDB can fill public
catalog metadata during `build` or `recommend`.

More explicit review note:

```markdown
---
title: Perfect Days
year: 2023
rating: 9
ratingScale: 10
watchedAt: 2025-01-18
tags:
  - contemplative
  - japan
tmdbId: 976893
source: https://www.themoviedb.org/movie/976893-perfect-days
---

A quiet film that notices the texture of ordinary routines.

## What stayed with me

The final sequence changes the meaning of everything before it.
```

Supported fields:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `title` | text | No | Film title; otherwise the filename without `.md`. |
| `year` | integer | No | Release year used to disambiguate catalog matches. |
| `rating` | number or score text | Yes | Personal score; aliases: `score`, `stars`. |
| `ratingScale` | `5` or `10` | No | Makes an otherwise ambiguous numeric score explicit; aliases: `rating_scale`, `scale`. |
| `watchedAt` | `YYYY-MM-DD` | No | Date watched. |
| `tags` | YAML list or strings | No | Personal taste signals. Markdown `#tags` in prose remain prose. |
| `categories` | YAML list or strings | No | Alias for tags; wiki-style links such as `[[films resumes]]` become plain text. |
| `tmdbId` | positive integer | No | Canonical TMDB movie ID; avoids title matching. |
| `sourceUrl` | URL | No | Optional public reference; aliases: `source_url`, `source`. |

The parser also accepts `film` or `movie` for title, `watched`, `date`, or `watched_at` for the watched
date, `genres` for tags, and `tmdb` or `tmdb_id` for the catalog ID. Tags and categories may be a YAML
list or a comma/space-separated string; leading `#` characters and wiki-style link wrappers are
removed. Unknown frontmatter is not copied. `sourceUrl` must be an absolute HTTP(S) URL without
embedded credentials, so local paths and `file:` URLs are rejected. When `title` is absent, the
filename still becomes the public title.

### Score rules

- The published scale is 0–10 in increments of 0.5.
- A bare `rating` or `score` value is already on the 0–10 scale, including values from 0–5.
- Five-point values are doubled only when explicit: use `rating: 4/5`, add `ratingScale: 5`, use the
  `stars` field, or write star characters such as `★★★★☆`.
- Explicit ten-point forms such as `rating: 8.5/10` are also accepted.
- Values outside 0–10, non-numeric values, and values that cannot normalize to a half-step are
  validation errors.

This avoids guessing about ambiguous values: bare `rating: 5` means five out of ten, while
`rating: 5/5` and `stars: 5` both normalize to ten.

### Title matching and duplicates

Matching compares both `tmdbId` and normalized title/year. A missing year is treated as unknown and
therefore overlaps the same title with a known year; two different known years can represent distinct
remakes. Catalog enrichment reports ambiguous and unresolved matches instead of selecting silently.
Mixed records where only one note has a TMDB ID are still detected as duplicates.

## Watchlist note

Every Markdown bullet, numbered-list item, or non-empty plain line represents one film. Headings,
blank lines, and lines beginning with an HTML comment are ignored.

Plain-title lists are valid:

```markdown
В диких условиях
Меню
Dumb money
Ted lesso
Social dilema
```

Optional structured lines are also valid:

```markdown
# Watchlist

- The Beast (2023) — interest: 9 — note: Léa Seydoux and speculative romance
- A Matter of Life and Death (1946) — interest: 8.5
- Yi Yi (2000)
Perfect Blue (1997) — interest: 8
- [[Persona (1966)]] | interest: 9 | tags: psychological, classic
- [After Life (1998)](https://www.themoviedb.org/movie/1794) — dismissed: true
```

Each line contains:

1. A title.
2. An optional four-digit release year in parentheses.
3. Optional named segments separated by an em dash (`—`), en dash (`–`), or pipe (`|`). Supported
   keys are `interest`/`score`, `year`, `note`/`notes`, `tag`/`tags`, and `dismissed`.

An unlabelled segment after the title is appended to the notes, so `| quiet evening` is valid.

Interest uses the 0–10 half-step scale and is not inferred as a five-point score. If interest is
omitted, it remains unset so the UI does not invent a preference. `dismissed` accepts `true`, `yes`,
`1`, `false`, `no`, or `0`. Dismissed films stay in the snapshot as a record of that choice but are
excluded from recommendations. Markdown task markers such as `- [ ]` are accepted as list syntax;
they do not change film status. Wiki-style links use their link target as the title; ordinary
Markdown links use their visible label.

Use a year or a TMDB-backed review entry whenever remakes share a title. Repeated watchlist entries,
and films already present in the watched collection, are validation errors.

## Validation workflow

Run the non-writing check before every build:

```bash
uv run filmography check --reviews "/path/to/Reviews" --watchlist "/path/to/Watchlist.md"
```

Fix all reported malformed lines, invalid scores, and duplicate source identities before publishing.
`check` never contacts TMDB and never modifies notes or the public snapshot. Catalog-specific
unresolved or ambiguous matches are reported by `build` and `recommend`.
