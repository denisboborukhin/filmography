"""Orchestrate imports, catalog enrichment, and atomic snapshot persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from filmography.ai import AIError, OpenAICompatibleClient, resolve_ai_suggestions
from filmography.markdown_notes import Diagnostic, ImportValidationError, import_markdown_notes
from filmography.models import (
    FilmMetadata,
    Recommendation,
    Snapshot,
    WatchedFilm,
    WatchlistFilm,
    film_matches_any,
)
from filmography.recommendations import preferred_genres, rank_deterministic
from filmography.tmdb import CatalogError, TMDBClient


@dataclass(frozen=True, slots=True)
class BuildResult:
    """A completed snapshot and non-fatal issues encountered while enriching it."""

    snapshot: Snapshot
    diagnostics: tuple[Diagnostic, ...] = ()


def build_snapshot(
    reviews_dir: Path,
    watchlist_path: Path,
    *,
    catalog: TMDBClient | None = None,
    previous: Snapshot | None = None,
    generated_at: datetime | None = None,
    deterministic_limit: int = 12,
) -> BuildResult:
    """Create a public snapshot, retaining the previous verified AI result set."""

    imported = import_markdown_notes(reviews_dir, watchlist_path)
    if imported.has_errors:
        raise ImportValidationError(imported.diagnostics)
    diagnostics = list(imported.diagnostics)
    watched = imported.watched
    watchlist = imported.watchlist
    if catalog is not None:
        watched = [_enrich_watched(film, catalog, diagnostics) for film in imported.watched]
        watchlist = [_enrich_watchlist(film, catalog, diagnostics) for film in imported.watchlist]

    now = _utc_datetime(generated_at)
    retained_ai = _retain_valid_ai(previous.ai_discoveries if previous else [], watched, watchlist)
    deterministic: list[Recommendation] = []
    deterministic_refreshed = False
    if catalog is not None:
        try:
            candidates = catalog.discover_movies(preferred_genres(watched))
            deterministic = rank_deterministic(
                watched,
                watchlist,
                candidates,
                generated_at=now,
                limit=deterministic_limit,
            )
            deterministic_refreshed = True
        except CatalogError as error:
            diagnostics.append(Diagnostic("warning", "catalog-discovery-failed", str(error)))
    retained_ids = {item.tmdb_id for item in retained_ai}
    deterministic = [item for item in deterministic if item.tmdb_id not in retained_ids]
    watched.sort(
        key=lambda film: (
            -(film.watched_at.toordinal() if film.watched_at is not None else 0),
            film.title.casefold(),
            film.year or 0,
        )
    )
    watchlist.sort(
        key=lambda film: (
            -(film.interest if film.interest is not None else -1),
            film.title.casefold(),
            film.year or 0,
        )
    )
    previous_recommendation_time = (
        previous.recommendations_generated_at if previous is not None and retained_ai else None
    )
    snapshot = Snapshot(
        generated_at=now,
        recommendations_generated_at=now
        if deterministic_refreshed
        else previous_recommendation_time,
        watched=watched,
        watchlist=watchlist,
        deterministic_discoveries=deterministic,
        ai_discoveries=retained_ai,
    )
    return BuildResult(snapshot, tuple(diagnostics))


def refresh_ai_recommendations(
    snapshot: Snapshot,
    ai_client: OpenAICompatibleClient,
    catalog: TMDBClient,
    *,
    prompt: str | None = None,
    generated_at: datetime | None = None,
    limit: int = 8,
) -> BuildResult:
    """Return a copy with a new verified AI set, or raise without altering the input."""

    now = _utc_datetime(generated_at)
    batch = ai_client.suggest(snapshot.watched, snapshot.watchlist, prompt=prompt, count=limit)
    resolved = resolve_ai_suggestions(
        batch,
        catalog,
        snapshot.watched,
        snapshot.watchlist,
        generated_at=now,
        provider=ai_client.provider,
        model=ai_client.model,
        limit=limit,
    )
    if not resolved.recommendations:
        raise AIError("AI returned no new recommendations that could be verified with TMDB")
    ai_ids = {item.tmdb_id for item in resolved.recommendations}
    updated = snapshot.model_copy(
        update={
            "recommendations_generated_at": now,
            "ai_discoveries": list(resolved.recommendations),
            "deterministic_discoveries": [
                item for item in snapshot.deterministic_discoveries if item.tmdb_id not in ai_ids
            ],
        }
    )
    # model_copy does not rerun model validators, so explicitly validate the serialized result.
    updated = Snapshot.model_validate(updated.model_dump())
    diagnostics = tuple(
        Diagnostic("warning", "ai-suggestion-rejected", warning) for warning in resolved.warnings
    )
    return BuildResult(updated, diagnostics)


def load_snapshot(path: Path) -> Snapshot | None:
    """Load a prior snapshot if it exists and strictly matches the current schema."""

    if not path.is_file():
        return None
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"existing snapshot is not valid JSON: {path}") from error
    try:
        return Snapshot.model_validate(raw)
    except ValidationError as error:
        raise ValueError(f"existing snapshot does not match schema: {path}: {error}") from error


def write_snapshot(snapshot: Snapshot, path: Path) -> None:
    """Validate and atomically write the generated public state."""

    validated = Snapshot.model_validate(snapshot.model_dump())
    content = json.dumps(
        validated.model_dump(mode="json", by_alias=True),
        ensure_ascii=False,
        indent=2,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(f"{content}\n", encoding="utf-8")
    temporary.replace(path)


def _enrich_watched(
    film: WatchedFilm,
    catalog: TMDBClient,
    diagnostics: list[Diagnostic],
) -> WatchedFilm:
    metadata = _catalog_metadata(film, catalog, diagnostics)
    if metadata is None:
        return film
    return WatchedFilm(
        **metadata.model_dump(),
        rating=film.rating,
        watched_at=film.watched_at,
        tags=film.tags,
        review=film.review,
        source_url=film.source_url,
    )


def _enrich_watchlist(
    film: WatchlistFilm,
    catalog: TMDBClient,
    diagnostics: list[Diagnostic],
) -> WatchlistFilm:
    metadata = _catalog_metadata(film, catalog, diagnostics, allow_popular_without_year=True)
    if metadata is None:
        return film
    return WatchlistFilm(
        **metadata.model_dump(),
        interest=film.interest,
        notes=film.notes,
        tags=film.tags,
        dismissed=film.dismissed,
    )


def _catalog_metadata(
    film: FilmMetadata,
    catalog: TMDBClient,
    diagnostics: list[Diagnostic],
    *,
    allow_popular_without_year: bool = False,
) -> FilmMetadata | None:
    try:
        if film.tmdb_id is not None:
            return catalog.get_movie(film.tmdb_id)
        match = catalog.match_movie(
            film.title,
            film.year,
            allow_popular_without_year=allow_popular_without_year,
        )
    except CatalogError as error:
        diagnostics.append(
            Diagnostic("warning", "catalog-request-failed", f"{film.title}: {error}")
        )
        return None
    if match.status == "matched":
        return match.film
    candidate_labels = ", ".join(
        f"{candidate.title} ({candidate.year or 'unknown'})" for candidate in match.candidates[:3]
    )
    detail = f"; candidates: {candidate_labels}" if candidate_labels else ""
    diagnostics.append(
        Diagnostic(
            "warning",
            f"catalog-{match.status}",
            f"{match.status} TMDB match for {film.title} ({film.year or 'unknown'}){detail}",
        )
    )
    return None


def _retain_valid_ai(
    recommendations: list[Recommendation],
    watched: list[WatchedFilm],
    watchlist: list[WatchlistFilm],
) -> list[Recommendation]:
    excluded = [*watched, *watchlist]
    retained: list[Recommendation] = []
    seen: set[int] = set()
    for item in recommendations:
        if item.tmdb_id in seen or film_matches_any(item, excluded):
            continue
        seen.add(item.tmdb_id)
        retained.append(item)
    return retained


def _utc_datetime(value: datetime | None) -> datetime:
    result = value or datetime.now(UTC)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("generated timestamp must be timezone-aware")
    return result.astimezone(UTC)
