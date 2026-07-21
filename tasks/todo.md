# Filmography implementation

- [x] Scaffold React/TypeScript and Python projects.
- [x] Define shared snapshot models and demo data.
- [x] Parse Markdown reviews and watchlist notes.
- [x] Enrich films through a cached TMDB client.
- [x] Generate deterministic and optional AI recommendations.
- [x] Build the responsive read-only journal UI.
- [x] Cache the last published snapshot for offline use.
- [x] Configure GitHub Pages without runtime secrets.
- [x] Complete automated and browser verification.
- [x] Document local generation and publishing workflows.

## Review

Implemented the complete local-to-static workflow with strict matching Python/TypeScript/JSON
contracts, conservative TMDB resolution, deterministic and optional AI recommendations, and a
read-only responsive PWA. The generated snapshot contains no runtime credentials or local note paths.

Verification completed:

- 63 Python tests and 17 frontend tests pass.
- Ruff, Pyright, ESLint, and TypeScript checks pass.
- The production build succeeds at the `/filmography/` GitHub Pages subpath.
- Desktop and mobile layouts were inspected in headless Chrome.
- A persistent Chrome profile rendered the full journal after the preview server was stopped,
  proving offline shell and snapshot recovery.
- No push, Pages activation, or deployment was performed.

# General Markdown notes cleanup

- [x] Replace app-specific notes wording with Markdown notes wording.
- [x] Rename importer internals away from app-specific names where practical.
- [x] Update tests and docs to match the broader Markdown positioning.
- [x] Run focused and full verification.

## Review

Removed product-specific Markdown-app language from the UI, docs, package metadata, importer module
names, and tests. The public input contract now describes generic Markdown review notes and a
Markdown watchlist note.

Verification completed:

- No remaining matches for app-specific notes terminology, old importer imports, or old docs paths.
- Focused Python importer/model tests passed.
- Frontend snapshot schema tests passed.
- `make check test` passed: TypeScript, ESLint, Ruff, Pyright, Vitest, and Pytest.
- `VITE_BASE_PATH=/filmography/ npm run build` passed.

# Personal Markdown format support

- [x] Support review `categories` frontmatter as public tags.
- [x] Normalize wiki-style category links into plain tag text.
- [x] Document filename-based reviews and plain-title watchlists as first-class formats.
- [x] Add tests for the user's review template and plain watchlist.
- [x] Run focused and full verification.

## Review

Added first-class support for the user's current Markdown format. Review notes can use filename
titles, `date`, `categories`, and `rating`; category wiki links and hash tags normalize into public
tags. Plain watchlist files with one title per line are supported and documented.

Verification completed:

- Focused Markdown importer tests passed.
- `make check test` passed: TypeScript, ESLint, Ruff, Pyright, Vitest, and Pytest.
- `VITE_BASE_PATH=/filmography/ npm run build` passed.

# AI provider error handling

- [x] Make OpenAI 429 failures actionable.
- [x] Keep API keys out of provider error messages.
- [x] Verify failed AI calls preserve the previous recommendation set.
- [x] Run focused and full verification.

## Review

Improved AI HTTP error handling so OpenAI 429 responses explain rate limits/quota and suggest
concrete local actions. Authentication, access, and provider server failures also now produce
sanitized messages without API keys.

Verification completed:

- Focused AI and CLI preservation tests passed.
- `make check test` passed: TypeScript, ESLint, Ruff, Pyright, Vitest, and Pytest.
- `VITE_BASE_PATH=/filmography/ npm run build` passed.
