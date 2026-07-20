# Updating and deployment

The committed JSON snapshot is the publication boundary. Updating Obsidian does not change the site
until you deliberately regenerate, review, commit, and push that file.

## Generate an update

From the repository root:

```bash
uv sync --dev
npm ci
uv run filmography check --reviews "/path/to/Reviews" --watchlist "/path/to/Watchlist.md"
```

For an ordinary journal/watchlist refresh:

```bash
export TMDB_ACCESS_TOKEN="your-tmdb-read-access-token"
uv run filmography build --reviews "/path/to/Reviews" --watchlist "/path/to/Watchlist.md"
```

For a new AI discovery set, also configure the provider and run:

```bash
export FILMOGRAPHY_AI_API_KEY="your-provider-key"
export FILMOGRAPHY_AI_BASE_URL="https://api.openai.com/v1"
export FILMOGRAPHY_AI_MODEL="your-model-name"
uv run filmography recommend \
  --reviews "/path/to/Reviews" \
  --watchlist "/path/to/Watchlist.md" \
  --prompt "Optional mood or constraints"
```

AI output is accepted only after each title is reconciled with TMDB. Watched, watchlisted, dismissed,
duplicate, ambiguous, and unresolved titles are excluded. If generation or validation fails, the
updater retains the still-valid subset of the last successful AI set. Entries newly added to watched
or watchlist are removed, while journal data and token-free discoveries may still be refreshed.

Both writing commands default to `public/data/filmography.json` and the ignored
`.filmography-cache/tmdb` directory. Use `--output`, `--cache-dir`, or `--deterministic-limit` when
needed. `recommend --count N` requests between 1 and 20 AI suggestions; the default is 8.

## Review public data

Everything in `public/data/filmography.json` will be downloadable by any site visitor. Before a
commit:

1. Inspect the complete generated file and its diff.

   ```bash
   git diff -- public/data/filmography.json
   less public/data/filmography.json
   ```

2. Confirm that each review and watchlist note is intended to be public. Look especially for names,
   contact details, private links, spoilers you did not intend to expose, and quoted correspondence.
3. Search for values or labels that should never be present.

   ```bash
   rg -n "API_KEY|ACCESS_TOKEN|Authorization|/Users/|/home/" public/data
   ```

4. Confirm recommendation rationales reveal no private detail from the source reviews.
5. Run the full verification suite and inspect the production site locally.

   ```bash
   make check
   make test
   VITE_BASE_PATH=/filmography/ npm run build
   VITE_BASE_PATH=/filmography/ npm run preview
   ```

Use the same base path as the intended repository name for the subpath check. Test narrow and wide
layouts, keyboard navigation, missing posters, and an offline reload after one successful online
visit. With the example command, open `http://localhost:4173/filmography/`.

## Commit the snapshot

The repository uses readable Conventional Commit-style messages with `feat`, for example:

```bash
git add public/data/filmography.json
git commit -m "feat(content): update journal and recommendations"
```

Do not commit `.env`, API keys, vault paths, local caches, or provider response dumps.

## Enable GitHub Pages later

No command in project setup pushes or publishes the repository. When the branch is ready:

1. Create or choose the GitHub repository and push the completed branch yourself.
2. Merge it into `main`, or change the branch filter in `.github/workflows/pages.yml` to your chosen
   default branch.
3. In **Repository settings → Pages → Build and deployment**, choose **GitHub Actions** as the source.
4. Run **Deploy static journal to GitHub Pages** manually, or push a commit to `main`.
5. In the workflow summary, open the deployment URL and verify routes, posters, and refresh behavior.

The workflow obtains the Pages base path from GitHub, installs npm dependencies, validates the
committed snapshot with the frontend schema tests, builds the site, and uploads `dist`. It never runs
`filmography build` or `filmography recommend`, so GitHub does not need TMDB or AI secrets and cannot
refresh personal content on its own.

For a `username.github.io` repository, the base path is `/`. For a project site such as
`username.github.io/filmography`, it is `/filmography/`; the workflow configures Vite automatically.

## Offline updates and recovery

The service worker caches the app shell, the latest successfully fetched snapshot, and a bounded
number of posters. Navigation uses the cached shell immediately; snapshot refreshes use a bounded
network attempt and then fall back to CacheStorage or the last valid browser copy. An offline visitor
therefore sees the last version that the browser successfully loaded, which may be older than the latest
deployment.

After publishing an urgent removal, visitors who previously loaded the site may still have that data
in browser storage. Ask them to clear site data, and update the service-worker cache version when an
immediate global cache invalidation is required. Git history and third-party archives may still
retain previously committed content.

If a deployment is bad, revert the content commit or restore the last known-good snapshot, run the
checks, and push the corrective commit. The next Pages run will publish it; no external API call is
needed.
