from __future__ import annotations

from datetime import UTC, datetime

from filmography.models import FilmMetadata, WatchedFilm, WatchlistFilm
from filmography.recommendations import preferred_genres, rank_deterministic


def test_preferred_genres_uses_ratings_and_tags() -> None:
    watched = [
        WatchedFilm(
            title="Loved",
            rating=10,
            genres=["Science Fiction", "Drama"],
            tags=["Cerebral"],
        ),
        WatchedFilm(title="Disliked", rating=2, genres=["Comedy", "Drama"]),
    ]

    assert preferred_genres(watched) == ["Science Fiction", "Drama"]


def test_deterministic_ranking_excludes_existing_and_explains_matches() -> None:
    now = datetime(2026, 7, 20, tzinfo=UTC)
    watched = [
        WatchedFilm(
            tmdb_id=1,
            title="Seen",
            year=2020,
            rating=9,
            genres=["Science Fiction"],
        )
    ]
    watchlist = [WatchlistFilm(title="Saved", year=2021, dismissed=True)]
    candidates = [
        FilmMetadata(tmdb_id=1, title="Seen", year=2020, genres=["Science Fiction"]),
        FilmMetadata(tmdb_id=2, title="Saved", year=2021, genres=["Science Fiction"]),
        FilmMetadata(
            tmdb_id=3,
            title="Strong Match",
            year=2022,
            genres=["Science Fiction"],
            vote_average=8,
            popularity=10,
        ),
        FilmMetadata(
            tmdb_id=4,
            title="Outside Pick",
            year=2023,
            genres=["Comedy"],
            vote_average=9,
            popularity=100,
        ),
    ]

    recommendations = rank_deterministic(
        watched, watchlist, candidates, generated_at=now, limit=10
    )

    assert [item.tmdb_id for item in recommendations] == [3, 4]
    assert recommendations[0].predicted_rating > recommendations[1].predicted_rating
    assert "Science Fiction" in recommendations[0].rationale
    assert recommendations[0].provider is None


def test_deterministic_ranking_is_stable_without_history() -> None:
    now = datetime(2026, 7, 20, tzinfo=UTC)
    candidates = [
        FilmMetadata(tmdb_id=2, title="B", vote_average=7, popularity=1),
        FilmMetadata(tmdb_id=1, title="A", vote_average=8, popularity=1),
    ]

    first = rank_deterministic([], [], candidates, generated_at=now)
    second = rank_deterministic([], [], list(reversed(candidates)), generated_at=now)

    assert [item.tmdb_id for item in first] == [1, 2]
    assert first == second
