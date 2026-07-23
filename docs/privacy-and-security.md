# Privacy and security

Filmography is local-first, not private-by-default. The updater runs locally, but its output is a
public website. Treat the generated snapshot exactly like any other file committed to a public Git
repository.

## Data boundaries

| Data | Where it is used | Published? |
| --- | --- | --- |
| Review text, rating, tags, watched date, optional public source URL | Local updater and generated snapshot | Yes |
| Watchlist title, interest, note, tags, dismissed state | Local updater and generated snapshot | Yes |
| Recommendation title, score, rationale, model name, date | Generated snapshot | Yes |
| TMDB IDs, metadata, poster URLs, and watched-title people credits | TMDB request and generated snapshot | Yes |
| Local notes path and source file path | Local updater only | No |
| TMDB token | Local updater process only | No |
| AI key and endpoint credentials | Local updater process only | No |
| Optional recommendation prompt | AI request only | No, unless reflected in rationale |

The static site makes no runtime calls to TMDB or an AI provider. Poster images are fetched by the
visitor's browser from the public image host recorded in the snapshot and may reveal the visitor's IP
address to that host. When review frontmatter has no title, the source filename stem is intentionally
published as the film title even though the file path itself is not included.

The generated snapshot publishes the TMDB IDs, names, profile image URLs, and credited roles of the
principal cast and one lead filmmaker attached to each watched title. The director is preferred;
the most important producer credit is used only as a fallback. Favorite-person rankings and
the relationship map are calculated in the browser from this already-public snapshot; they do not
send personal scores or browsing behavior to another service.

## What leaves the computer

`filmography check` parses local files without network access. When a TMDB token is configured,
`filmography build` sends film titles, years, or TMDB IDs to TMDB for metadata matching and discovery.
`filmography recommend` additionally sends the configured provider a taste profile derived from
ratings, tags, full review text, the watchlist, local taste-match candidates, and the optional
prompt. The provider returns expected scores for non-manual watchlist entries and taste matches as
well as new-film suggestions.

Review the selected AI provider's retention and training policy before use. If reviews contain
sensitive information, use token-free recommendations or redact those notes before running
`recommend`. Use an HTTPS provider endpoint unless it is a service running on your own machine.

## Credential handling

- Supply credentials through environment variables only.
- Keep `.env` and local tool configuration ignored by Git.
- Never place secrets in `VITE_*` variables: Vite embeds those values into browser JavaScript.
- Treat every `sourceUrl` as public. Do not use signed links or include tokens in URL query strings;
  the validated HTTP(S) URL is copied to the snapshot.
- Never add TMDB or AI secrets to the GitHub Pages workflow; the deploy job does not need them.
- Rotate a credential immediately if it appears in a terminal recording, generated JSON, commit, or
  workflow log. Removing the latest commit alone does not revoke it.
- Review `git diff --staged` before every commit and enable GitHub secret scanning when available.

Only derived, intentionally public data belongs under `public/data/`.

## Public-history warning

Deleting a review from the current snapshot does not erase it from Git history, forks, search caches,
archives, or browsers that stored the offline site. Do not publish material that must be retractable.
If sensitive data is accidentally committed, rotate affected credentials first, remove the deployed
content, then follow GitHub's sensitive-data removal guidance for repository history.

## Browser storage

The service worker caches the static application, snapshot, and recent posters on each visitor's
device. It stores no credentials and cannot edit local notes. A visitor can remove cached content by
clearing site data or unregistering the service worker in browser settings.

The app should be served over HTTPS. GitHub Pages supplies HTTPS for its standard domains; enforce
HTTPS when configuring a custom domain.
