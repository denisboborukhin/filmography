"""Token-free preference learning and transparent recommendation ranking."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime

from filmography.models import (
    FilmMetadata,
    Recommendation,
    WatchedFilm,
    WatchlistFilm,
    film_matches_any,
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
    excluded = [*watched, *watchlist]
    preferences = _preference_weights(watched)
    preference_names = _preference_names(watched)
    baseline = sum(film.rating for film in watched) / len(watched) if watched else 6.0

    ranked: list[tuple[float, float, float, str, FilmMetadata, list[str]]] = []
    seen_ids: set[int] = set()
    for film in candidates:
        if film.tmdb_id is None or film.tmdb_id in seen_ids:
            continue
        if film_matches_any(film, excluded):
            continue
        seen_ids.add(film.tmdb_id)
        matches = _candidate_matches(preferences, preference_names, film)
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
        rationale = _rationale(film, matches)
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


def predict_personal_rating(watched: list[WatchedFilm], film: FilmMetadata) -> float:
    """Estimate a personal rating for a known TMDB record without adding it as a discovery."""

    preferences = _preference_weights(watched)
    preference_names = _preference_names(watched)
    baseline = sum(item.rating for item in watched) / len(watched) if watched else 6.0
    matches = _candidate_matches(preferences, preference_names, film)
    affinity = sum(preferences.get(_normalize_label(genre), 0.0) for _, genre in matches[:2])
    catalog_score = film.vote_average if film.vote_average is not None else 5.0
    return _predicted_score(baseline, affinity, catalog_score)


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


def _preference_names(watched: list[WatchedFilm]) -> dict[str, str]:
    names: dict[str, str] = {}
    for film in watched:
        for label in [*film.genres, *film.tags]:
            normalized = _normalize_label(label)
            if normalized and normalized not in names:
                names[normalized] = label.strip()
    return names


def _candidate_matches(
    preferences: dict[str, float],
    preference_names: dict[str, str],
    film: FilmMetadata,
) -> list[tuple[float, str]]:
    matches: dict[str, tuple[float, str]] = {}
    for genre in film.genres:
        normalized = _normalize_label(genre)
        weight = preferences.get(normalized, 0.0)
        if weight > 0:
            matches[normalized] = (weight, genre)

    searchable = (
        f" {_normalize_label(' '.join((film.title, film.original_title or '', film.overview)))} "
    )
    for normalized, weight in preferences.items():
        if weight > 0 and normalized not in matches and f" {normalized} " in searchable:
            matches[normalized] = (weight, preference_names.get(normalized, normalized))
    return sorted(matches.values(), key=lambda item: (-item[0], item[1].casefold()))


def _normalize_label(value: str) -> str:
    return " ".join("".join(char.casefold() if char.isalnum() else " " for char in value).split())


def _tenth_step(value: float) -> float:
    return round(value * 10) / 10


def _predicted_score(baseline: float, affinity: float, catalog_score: float) -> float:
    raw_score = baseline + min(affinity * 0.35, 2.0) + (catalog_score - 5) * 0.15
    return _tenth_step(_clamp(raw_score))


def _rationale(film: FilmMetadata, matches: list[str]) -> str:
    description = _short_description(film.overview)
    if description and matches:
        return f"{description} The {_join_labels(matches[:2])} angle is the clearest fit."
    if description:
        return description
    if matches:
        return f"A {_join_labels(matches[:2])} pick with enough catalog strength to investigate."
    if film.genres:
        return (
            f"A {_join_labels(film.genres[:2])} discovery with enough catalog strength "
            "to investigate."
        )
    return "A catalog discovery worth checking before it goes onto the watchlist."


def _clamp(value: float) -> float:
    return min(10.0, max(0.0, value))


def _join_labels(values: list[str]) -> str:
    if len(values) == 1:
        return values[0]
    return " and ".join(values)


def _short_description(value: str) -> str:
    text = " ".join(value.split())
    if not text:
        return ""
    first_sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0].strip()
    if len(first_sentence) <= 180:
        return first_sentence
    return f"{first_sentence[:177].rstrip()}..."
