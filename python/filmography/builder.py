"""Orchestrate imports, catalog enrichment, and atomic snapshot persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from filmography.ai import (
    AIError,
    OpenAICompatibleClient,
    resolve_ai_scores,
    resolve_ai_suggestions,
    score_target_id,
)
from filmography.markdown_notes import Diagnostic, ImportValidationError, import_markdown_notes
from filmography.models import (
    FilmCredits,
    FilmMetadata,
    Recommendation,
    Snapshot,
    WatchedFilm,
    WatchlistFilm,
    films_match,
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
        previous_watched = previous.watched if previous is not None else []
        previous_watchlist = previous.watchlist if previous is not None else []
        watched = [
            _enrich_watched(
                film,
                catalog,
                diagnostics,
                previous_watched=previous_watched,
            )
            for film in imported.watched
        ]
        watchlist = [
            _enrich_watchlist(
                film,
                catalog,
                diagnostics,
                watched=watched,
                previous_watchlist=previous_watchlist,
            )
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
            deterministic = _retain_previous_ai_scores(
                deterministic,
                previous.deterministic_discoveries if previous is not None else [],
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
    limit: int = 10,
) -> BuildResult:
    """Return a copy with independently refreshed AI picks and target scores."""

    if not 1 <= limit <= 20:
        raise ValueError("AI recommendation limit must be between 1 and 20")
    now = _utc_datetime(generated_at)
    requested = min(20, limit * 3)
    diagnostics: list[Diagnostic] = []
    ai_discoveries = snapshot.ai_discoveries
    deterministic_discoveries = snapshot.deterministic_discoveries
    watchlist = snapshot.watchlist
    suggestion_failed = False
    scoring_failed = False
    suggestion_error: AIError | None = None
    scoring_error: AIError | None = None
    scoring_applied = False

    try:
        suggestion_batch = ai_client.suggest(
            snapshot.watched,
            snapshot.watchlist,
            prompt=prompt,
            count=requested,
        )
        resolved_suggestions = resolve_ai_suggestions(
            suggestion_batch,
            catalog,
            snapshot.watched,
            snapshot.watchlist,
            deterministic_discoveries=snapshot.deterministic_discoveries,
            generated_at=now,
            provider=ai_client.provider,
            model=ai_client.model,
            limit=limit,
        )
        required_recommendations = min(5, limit)
        if len(resolved_suggestions.recommendations) < required_recommendations:
            detail = "; ".join(resolved_suggestions.warnings[:5])
            suffix = f": {detail}" if detail else ""
            raise AIError(
                f"AI returned only {len(resolved_suggestions.recommendations)} verified "
                f"recommendations; at least {required_recommendations} required{suffix}"
            )
        ai_discoveries = list(resolved_suggestions.recommendations)
        deterministic_discoveries = unique_unmatched_films(
            deterministic_discoveries, ai_discoveries
        )
        diagnostics.extend(
            Diagnostic("warning", "ai-suggestion-rejected", warning)
            for warning in resolved_suggestions.warnings
        )
    except AIError as error:
        suggestion_failed = True
        suggestion_error = error
        diagnostics.append(Diagnostic("warning", "ai-suggestions-failed", str(error)))

    try:
        score_batch = ai_client.score_targets(
            snapshot.watched,
            watchlist,
            deterministic_discoveries=deterministic_discoveries,
            prompt=prompt,
        )
        resolved_scores = resolve_ai_scores(
            score_batch,
            snapshot.watched,
            watchlist,
            deterministic_discoveries,
        )
        scoring_applied = bool(resolved_scores.watchlist_scores or resolved_scores.discovery_scores)
        watchlist = _apply_ai_watchlist_scores(watchlist, dict(resolved_scores.watchlist_scores))
        deterministic_discoveries = _apply_ai_discovery_scores(
            deterministic_discoveries, dict(resolved_scores.discovery_scores)
        )
        diagnostics.extend(
            Diagnostic("warning", "ai-score-rejected", warning)
            for warning in resolved_scores.warnings
        )
    except AIError as error:
        scoring_failed = True
        scoring_error = error
        diagnostics.append(Diagnostic("warning", "ai-scoring-failed", str(error)))

    if suggestion_failed and not scoring_applied:
        if scoring_failed and scoring_error is not None:
            raise AIError(f"{suggestion_error}; {scoring_error}") from scoring_error
        if suggestion_error is not None:
            raise suggestion_error

    updated = snapshot.model_copy(
        update={
            "recommendations_generated_at": now,
            "watchlist": watchlist,
            "ai_discoveries": ai_discoveries,
            "deterministic_discoveries": unique_unmatched_films(
                deterministic_discoveries, ai_discoveries
            ),
        }
    )
    # model_copy does not rerun model validators, so explicitly validate the serialized result.
    updated = Snapshot.model_validate(updated.model_dump())
    return BuildResult(updated, tuple(diagnostics))


def _apply_ai_watchlist_scores(
    films: list[WatchlistFilm], scores: dict[str, float]
) -> list[WatchlistFilm]:
    result: list[WatchlistFilm] = []
    for film in films:
        score = scores.get(score_target_id("watchlist", film))
        result.append(
            film.model_copy(update={"interest": score, "interest_source": "ai"})
            if score is not None and film.interest_source != "manual"
            else film
        )
    result.sort(
        key=lambda film: (
            -(film.interest if film.interest is not None else -1),
            film.title.casefold(),
            film.year or 0,
        )
    )
    return result


def _apply_ai_discovery_scores(
    films: list[Recommendation], scores: dict[str, float]
) -> list[Recommendation]:
    result: list[Recommendation] = []
    for film in films:
        score = scores.get(score_target_id("discovery", film))
        result.append(
            film.model_copy(update={"predicted_rating": score, "score_source": "ai"})
            if score is not None
            else film
        )
    return sorted(
        result,
        key=lambda film: (-film.predicted_rating, film.title.casefold(), film.year or 0),
    )


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
    *,
    previous_watched: list[WatchedFilm],
) -> WatchedFilm:
    metadata = _catalog_metadata(film, catalog, diagnostics)
    if metadata is None:
        return film
    prior_credits = next(
        (previous.credits for previous in previous_watched if films_match(metadata, previous)),
        FilmCredits(),
    )
    credits = _catalog_credits(metadata, catalog, diagnostics, fallback=prior_credits)
    return WatchedFilm(
        **metadata.model_dump(),
        rating=film.rating,
        watched_at=film.watched_at,
        tags=film.tags,
        review=film.review,
        source_url=film.source_url,
        credits=credits,
    )


def _catalog_credits(
    film: FilmMetadata,
    catalog: TMDBClient,
    diagnostics: list[Diagnostic],
    *,
    fallback: FilmCredits,
) -> FilmCredits:
    if film.tmdb_id is None:
        return FilmCredits()
    try:
        return catalog.get_credits(film.tmdb_id, film.media_type)
    except CatalogError as error:
        diagnostics.append(
            Diagnostic("warning", "catalog-credits-failed", f"{film.title}: {error}")
        )
        return fallback


def _enrich_watchlist(
    film: WatchlistFilm,
    catalog: TMDBClient,
    diagnostics: list[Diagnostic],
    *,
    watched: list[WatchedFilm],
    previous_watchlist: list[WatchlistFilm],
) -> WatchlistFilm:
    metadata = _catalog_metadata(film, catalog, diagnostics, allow_popular_without_year=True)
    if metadata is None:
        previous_score = _previous_ai_watchlist_score(film, previous_watchlist)
        return (
            film.model_copy(
                update={
                    "interest": previous_score.interest,
                    "interest_source": "ai",
                }
            )
            if film.interest is None and previous_score is not None
            else film
        )
    previous_score = _previous_ai_watchlist_score(metadata, previous_watchlist)
    interest = film.interest
    interest_source = film.interest_source
    if interest is None and previous_score is not None:
        interest = previous_score.interest
        interest_source = "ai"
    elif interest is None:
        interest = predict_personal_rating(watched, metadata)
        interest_source = "local"
    return WatchlistFilm(
        **metadata.model_dump(),
        interest=interest,
        interest_source=interest_source,
        notes=film.notes,
        tags=film.tags,
        dismissed=film.dismissed,
    )


def _previous_ai_watchlist_score(
    film: FilmMetadata, previous_watchlist: list[WatchlistFilm]
) -> WatchlistFilm | None:
    return next(
        (
            previous
            for previous in previous_watchlist
            if previous.interest_source == "ai"
            and previous.interest is not None
            and films_match(film, previous)
        ),
        None,
    )


def _retain_previous_ai_scores(
    recommendations: list[Recommendation], previous: list[Recommendation]
) -> list[Recommendation]:
    retained: list[Recommendation] = []
    for recommendation in recommendations:
        previous_match = next(
            (
                candidate
                for candidate in previous
                if candidate.score_source == "ai" and films_match(recommendation, candidate)
            ),
            None,
        )
        retained.append(
            recommendation.model_copy(
                update={
                    "predicted_rating": previous_match.predicted_rating,
                    "score_source": "ai",
                }
            )
            if previous_match is not None
            else recommendation
        )
    return retained


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
        f"; possible TMDB TV match: {', '.join(tv_titles)}. "
        "Set mediaType to tv when the title should be treated as a series."
    )


def _utc_datetime(value: datetime | None) -> datetime:
    result = value or datetime.now(UTC)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("generated timestamp must be timezone-aware")
    return result.astimezone(UTC)
