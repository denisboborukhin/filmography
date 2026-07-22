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
    unique_unmatched_films,
)
from filmography.recommendations import (
    predict_personal_rating,
    preferred_genres,
    rank_deterministic,
)
from filmography.tmdb import CatalogError, CatalogMatch, TMDBClient


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
        watchlist = [
            _enrich_watchlist(film, catalog, diagnostics, watched=watched)
            for film in imported.watchlist
        ]

    now = _utc_datetime(generated_at)
    retained_ai = unique_unmatched_films(
        previous.ai_discoveries if previous else [], [*watched, *watchlist]
    )
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
    deterministic = unique_unmatched_films(deterministic, retained_ai)
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
    requested = min(20, max(limit, limit * 3))
    batch = ai_client.suggest(snapshot.watched, snapshot.watchlist, prompt=prompt, count=requested)
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
        detail = "; ".join(resolved.warnings[:5])
        suffix = f": {detail}" if detail else ""
        raise AIError(
            f"AI returned no new recommendations that could be verified with TMDB{suffix}"
        )
    updated = snapshot.model_copy(
        update={
            "recommendations_generated_at": now,
            "ai_discoveries": list(resolved.recommendations),
            "deterministic_discoveries": unique_unmatched_films(
                snapshot.deterministic_discoveries, resolved.recommendations
            ),
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
    *,
    watched: list[WatchedFilm],
) -> WatchlistFilm:
    metadata = _catalog_metadata(film, catalog, diagnostics, allow_popular_without_year=True)
    if metadata is None:
        return film
    return WatchlistFilm(
        **metadata.model_dump(),
        interest=film.interest
        if film.interest is not None
        else predict_personal_rating(watched, metadata),
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
            if film.media_type == "tv":
                return catalog.get_tv(film.tmdb_id)
            return catalog.get_movie(film.tmdb_id)
        match = (
            catalog.match_tv(
                film.title,
                film.year,
                allow_popular_without_year=allow_popular_without_year,
            )
            if film.media_type == "tv"
            else catalog.match_movie(
                film.title,
                film.year,
                allow_popular_without_year=allow_popular_without_year,
            )
        )
    except CatalogError as error:
        diagnostics.append(
            Diagnostic("warning", "catalog-request-failed", f"{film.title}: {error}")
        )
        return None
    if match.status == "matched":
        return match.film
    if film.media_type == "movie":
        tv_match = _match_series(film, catalog, allow_popular_without_year)
        if tv_match.status == "matched":
            return tv_match.film
    candidate_labels = ", ".join(
        f"{candidate.title} ({candidate.year or 'unknown'})" for candidate in match.candidates[:3]
    )
    detail = f"; candidates: {candidate_labels}" if candidate_labels else ""
    tv_detail = _tv_diagnostic_detail(film.title, catalog) if film.media_type == "movie" else ""
    catalog_label = "TMDB TV" if film.media_type == "tv" else "TMDB movie"
    diagnostics.append(
        Diagnostic(
            "warning",
            f"catalog-{match.status}",
            f"{match.status} {catalog_label} match for {film.title} "
            f"({film.year or 'unknown'}){detail}{tv_detail}",
        )
    )
    return None


def _match_series(
    film: FilmMetadata,
    catalog: TMDBClient,
    allow_popular_without_year: bool,
) -> CatalogMatch:
    try:
        return catalog.match_tv(
            film.title,
            film.year,
            allow_popular_without_year=allow_popular_without_year,
        )
    except CatalogError:
        return CatalogMatch("unresolved", None)


def _tv_diagnostic_detail(title: str, catalog: TMDBClient) -> str:
    try:
        tv_titles = catalog.find_tv_titles(title)
    except CatalogError:
        return ""
    if not tv_titles:
        return ""
    return (
        f"; TMDB TV match: {', '.join(tv_titles)}. "
        "Series are kept as plain watchlist text and are not enriched in this film-only snapshot."
    )


def _utc_datetime(value: datetime | None) -> datetime:
    result = value or datetime.now(UTC)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("generated timestamp must be timezone-aware")
    return result.astimezone(UTC)
