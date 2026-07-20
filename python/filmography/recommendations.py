"""Token-free preference learning and transparent recommendation ranking."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from filmography.models import (
    FilmMetadata,
    Recommendation,
    WatchedFilm,
    WatchlistFilm,
    film_identity,
)


def preferred_genres(watched: list[WatchedFilm], *, limit: int = 4) -> list[str]:
    """Return the strongest positively rated catalog genres in a stable order."""

    if limit < 1:
        return []
    weights = _preference_weights(watched)
    catalog_genres = {
        genre.casefold(): genre for film in watched for genre in film.genres if genre.strip()
    }
    ranked = sorted(
        (
            (weights.get(_normalize_label(name), 0.0), canonical)
            for name, canonical in catalog_genres.items()
        ),
        key=lambda item: (-item[0], item[1].casefold()),
    )
    positive = [name for weight, name in ranked if weight > 0]
    return positive[:limit]


def rank_deterministic(
    watched: list[WatchedFilm],
    watchlist: list[WatchlistFilm],
    candidates: list[FilmMetadata],
    *,
    generated_at: datetime,
    limit: int = 12,
) -> list[Recommendation]:
    """Rank unseen TMDB films from explicit rating and genre/tag affinity."""

    if limit < 0:
        raise ValueError("limit cannot be negative")
    excluded_ids = {
        film.tmdb_id for film in [*watched, *watchlist] if film.tmdb_id is not None
    }
    excluded_titles = {
        film_identity(film.title, film.year) for film in [*watched, *watchlist]
    }
    preferences = _preference_weights(watched)
    baseline = sum(film.rating for film in watched) / len(watched) if watched else 6.0

    ranked: list[tuple[float, float, float, str, FilmMetadata, list[str]]] = []
    seen_ids: set[int] = set()
    for film in candidates:
        if film.tmdb_id is None or film.tmdb_id in seen_ids or film.tmdb_id in excluded_ids:
            continue
        if film_identity(film.title, film.year) in excluded_titles:
            continue
        seen_ids.add(film.tmdb_id)
        matches = sorted(
            (
                (preferences.get(_normalize_label(genre), 0.0), genre)
                for genre in film.genres
                if preferences.get(_normalize_label(genre), 0.0) > 0
            ),
            key=lambda item: (-item[0], item[1].casefold()),
        )
        affinity = sum(weight for weight, _ in matches[:3])
        catalog_score = film.vote_average if film.vote_average is not None else 5.0
        ranking_score = affinity * 2 + catalog_score * 0.25
        ranked.append(
            (
                ranking_score,
                catalog_score,
                film.popularity or 0,
                film.title.casefold(),
                film,
                [genre for _, genre in matches[:2]],
            )
        )

    ranked.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
    recommendations: list[Recommendation] = []
    for _, _, _, _, film, matches in ranked[:limit]:
        catalog_score = film.vote_average if film.vote_average is not None else 5.0
        affinity = sum(preferences.get(_normalize_label(genre), 0.0) for genre in matches)
        predicted = _predicted_score(baseline, affinity, catalog_score)
        rationale = (
            f"Matches your strong preference for {_join_labels(matches)}."
            if matches
            else "A highly rated catalog discovery outside your usual genre signals."
        )
        recommendations.append(
            Recommendation(
                **film.model_dump(),
                predicted_rating=predicted,
                rationale=rationale,
                source="deterministic",
                generated_at=generated_at,
            )
        )
    return recommendations


def _preference_weights(watched: list[WatchedFilm]) -> dict[str, float]:
    totals: defaultdict[str, float] = defaultdict(float)
    counts: defaultdict[str, int] = defaultdict(int)
    for film in watched:
        signal = film.rating - 5.0
        labels = {*film.genres, *film.tags}
        for label in labels:
            normalized = _normalize_label(label)
            if normalized:
                totals[normalized] += signal
                counts[normalized] += 1
    return {label: totals[label] / counts[label] for label in totals}


def _normalize_label(value: str) -> str:
    return " ".join("".join(char.casefold() if char.isalnum() else " " for char in value).split())


def _half_step(value: float) -> float:
    return round(value * 2) / 2


def _predicted_score(baseline: float, affinity: float, catalog_score: float) -> float:
    raw_score = baseline + min(affinity * 0.35, 2.0) + (catalog_score - 5) * 0.15
    return _half_step(_clamp(raw_score))


def _clamp(value: float) -> float:
    return min(10.0, max(0.0, value))


def _join_labels(values: list[str]) -> str:
    if len(values) == 1:
        return values[0]
    return " and ".join(values)
