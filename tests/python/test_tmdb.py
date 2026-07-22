from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from filmography.tmdb import CatalogError, TMDBClient


def _movie(
    tmdb_id: int,
    title: str,
    year: int,
    *,
    original_title: str | None = None,
    genre_ids: list[int] | None = None,
    popularity: float = 42.0,
) -> dict[str, object]:
    return {
        "id": tmdb_id,
        "title": title,
        "original_title": original_title or title,
        "release_date": f"{year}-01-02",
        "poster_path": f"/{tmdb_id}.jpg",
        "overview": f"Overview for {title}",
        "vote_average": 8.1,
        "popularity": popularity,
        **({"genre_ids": genre_ids} if genre_ids is not None else {}),
    }


def _client(
    tmp_path: Path, handler: Callable[[httpx.Request], httpx.Response]
) -> tuple[TMDBClient, httpx.Client]:
    http_client = httpx.Client(
        base_url="https://catalog.test/3/",
        transport=httpx.MockTransport(handler),
    )
    return TMDBClient("token", tmp_path / "cache", http_client=http_client), http_client


def test_matches_unique_exact_title_and_year_and_caches_response(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [_movie(1, "Arrival", 2016)]})

    catalog, http_client = _client(tmp_path, handler)
    try:
        first = catalog.match_movie("Arrival", 2016)
        second = catalog.match_movie("Arrival", 2016)
    finally:
        http_client.close()

    assert first.status == "matched"
    assert first.film is not None and first.film.tmdb_id == 1
    assert second.film == first.film
    assert len(requests) == 1
    assert requests[0].url.path == "/3/search/movie"
    assert requests[0].url.params["year"] == "2016"
    cached_files = list((tmp_path / "cache").glob("*.json"))
    assert len(cached_files) == 1
    assert "token" not in cached_files[0].read_text(encoding="utf-8")


def test_reports_ambiguous_and_unresolved_matches(tmp_path: Path) -> None:
    responses = [
        {"results": [_movie(1, "Crash", 1996), _movie(2, "Crash", 1996)]},
        {"results": [_movie(3, "A Different Film", 2020)]},
    ]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=responses.pop(0))

    catalog, http_client = _client(tmp_path, handler)
    try:
        ambiguous = catalog.match_movie("Crash", 1996)
        unresolved = catalog.match_movie("Missing", 2020)
    finally:
        http_client.close()

    assert ambiguous.status == "ambiguous"
    assert ambiguous.film is None
    assert len(ambiguous.candidates) == 2
    assert unresolved.status == "unresolved"
    assert unresolved.film is None


def test_matches_localized_same_year_candidate_without_title_equality(tmp_path: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [_movie(70160, "The Hunger Games", 2012)]})

    catalog, http_client = _client(tmp_path, handler)
    try:
        match = catalog.match_movie("Голодные игры", 2012)
    finally:
        http_client.close()

    assert match.status == "matched"
    assert match.film is not None
    assert match.film.title == "The Hunger Games"


def test_movie_search_resolves_genres_from_movie_catalog(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/3/genre/movie/list":
            return httpx.Response(200, json={"genres": [{"id": 18, "name": "Drama"}]})
        assert request.url.path == "/3/search/movie"
        return httpx.Response(
            200,
            json={"results": [_movie(1, "Arrival", 2016, genre_ids=[18])]},
        )

    catalog, http_client = _client(tmp_path, handler)
    try:
        match = catalog.match_movie("Arrival", 2016)
    finally:
        http_client.close()

    assert match.film is not None
    assert match.film.genres == ["Drama"]


def test_picks_unique_popularity_winner_for_duplicate_exact_matches(tmp_path: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    _movie(274479, "Joy", 2015, popularity=80),
                    _movie(111, "Joy", 2015, popularity=5),
                ]
            },
        )

    catalog, http_client = _client(tmp_path, handler)
    try:
        match = catalog.match_movie("Joy", 2015)
    finally:
        http_client.close()

    assert match.status == "matched"
    assert match.film is not None
    assert match.film.tmdb_id == 274479


def test_yearless_popularity_fallback_is_explicit(tmp_path: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    _movie(1, "Menu", 2012, popularity=10),
                    _movie(593643, "The Menu", 2022, popularity=90),
                ]
            },
        )

    catalog, http_client = _client(tmp_path, handler)
    try:
        conservative = catalog.match_movie("Меню")
        popular = catalog.match_movie("Меню", allow_popular_without_year=True)
    finally:
        http_client.close()

    assert conservative.status == "unresolved"
    assert popular.status == "matched"
    assert popular.film is not None
    assert popular.film.tmdb_id == 593643


def test_finds_exact_tv_title_for_movie_miss_diagnostics(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/3/search/tv"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 97546,
                        "name": "Ted Lasso",
                        "original_name": "Ted Lasso",
                        "first_air_date": "2020-08-14",
                    }
                ]
            },
        )

    catalog, http_client = _client(tmp_path, handler)
    try:
        assert catalog.find_tv_titles("Ted Lasso") == ("Ted Lasso (2020)",)
    finally:
        http_client.close()


def test_matches_tv_series_and_maps_metadata(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/3/genre/tv/list":
            return httpx.Response(200, json={"genres": [{"id": 35, "name": "Comedy"}]})
        assert request.url.path == "/3/search/tv"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 97546,
                        "name": "Ted Lasso",
                        "original_name": "Ted Lasso",
                        "first_air_date": "2020-08-14",
                        "poster_path": "/ted.jpg",
                        "overview": "An American coach manages a football club.",
                        "genre_ids": [35],
                        "vote_average": 8.5,
                        "popularity": 100,
                    }
                ]
            },
        )

    catalog, http_client = _client(tmp_path, handler)
    try:
        match = catalog.match_tv("Ted Lasso", allow_popular_without_year=True)
    finally:
        http_client.close()

    assert match.status == "matched"
    assert match.film is not None
    assert match.film.media_type == "tv"
    assert match.film.title == "Ted Lasso"
    assert match.film.year == 2020
    assert match.film.genres == ["Comedy"]
    assert match.film.poster_url == "https://image.tmdb.org/t/p/w780/ted.jpg"


def test_fetches_tv_details(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/3/tv/97546"
        return httpx.Response(
            200,
            json={
                "id": 97546,
                "name": "Ted Lasso",
                "original_name": "Ted Lasso",
                "first_air_date": "2020-08-14",
                "poster_path": "/ted.jpg",
                "overview": "An American coach manages a football club.",
                "genres": [{"id": 35, "name": "Comedy"}],
                "vote_average": 8.5,
                "popularity": 100,
            },
        )

    catalog, http_client = _client(tmp_path, handler)
    try:
        series = catalog.get_tv(97546)
    finally:
        http_client.close()

    assert series.media_type == "tv"
    assert series.title == "Ted Lasso"
    assert series.genres == ["Comedy"]


def test_fetches_details_and_maps_catalog_metadata(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/3/movie/603"
        payload = _movie(603, "The Matrix", 1999)
        payload["genres"] = [{"id": 28, "name": "Action"}]
        return httpx.Response(200, json=payload)

    catalog, http_client = _client(tmp_path, handler)
    try:
        film = catalog.get_movie(603)
    finally:
        http_client.close()

    assert film.title == "The Matrix"
    assert film.year == 1999
    assert film.genres == ["Action"]
    assert film.poster_url == "https://image.tmdb.org/t/p/w780/603.jpg"


def test_fetches_principal_cast_and_prefers_director_as_lead_filmmaker(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/3/movie/603/credits"
        return httpx.Response(
            200,
            json={
                "cast": [
                    {
                        "id": 1,
                        "name": "Lead Actor",
                        "character": "The Lead",
                        "profile_path": "/actor.jpg",
                    }
                ],
                "crew": [
                    {
                        "id": 2,
                        "name": "Film Director",
                        "job": "Director",
                        "department": "Directing",
                        "profile_path": None,
                    },
                    {
                        "id": 3,
                        "name": "Film Producer",
                        "job": "Executive Producer",
                        "department": "Production",
                        "profile_path": "/producer.jpg",
                    },
                    {
                        "id": 4,
                        "name": "Visual Effects Producer",
                        "job": "VFX Producer",
                        "department": "Visual Effects",
                    },
                ],
            },
        )

    catalog, http_client = _client(tmp_path, handler)
    try:
        credits = catalog.get_credits(603, "movie")
    finally:
        http_client.close()

    assert [(person.name, person.role) for person in credits.cast] == [("Lead Actor", "The Lead")]
    assert credits.filmmaker is not None
    assert (credits.filmmaker.name, credits.filmmaker.role) == ("Film Director", "Director")
    assert credits.cast[0].profile_url == "https://image.tmdb.org/t/p/w185/actor.jpg"


def test_uses_producer_when_credits_have_no_director(tmp_path: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "cast": [],
                "crew": [
                    {
                        "id": 3,
                        "name": "Executive",
                        "job": "Executive Producer",
                        "department": "Production",
                    },
                    {
                        "id": 2,
                        "name": "Lead Producer",
                        "job": "Producer",
                        "department": "Production",
                    },
                ],
            },
        )

    catalog, http_client = _client(tmp_path, handler)
    try:
        credits = catalog.get_credits(603, "movie")
    finally:
        http_client.close()

    assert credits.filmmaker is not None
    assert (credits.filmmaker.name, credits.filmmaker.role) == ("Lead Producer", "Producer")


def test_discovers_movies_using_preferred_genre_ids(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/3/genre/movie/list":
            return httpx.Response(200, json={"genres": [{"id": 878, "name": "Science Fiction"}]})
        assert request.url.path == "/3/discover/movie"
        assert request.url.params["with_genres"] == "878"
        return httpx.Response(
            200,
            json={"results": [_movie(11, "Moon", 2009, genre_ids=[878])]},
        )

    catalog, http_client = _client(tmp_path, handler)
    try:
        films = catalog.discover_movies(["Science Fiction"], pages=1)
    finally:
        http_client.close()

    assert len(films) == 1
    assert films[0].genres == ["Science Fiction"]


def test_wraps_http_and_invalid_json_errors_without_exposing_token(tmp_path: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=json.dumps({"error": "nope"}))

    catalog, http_client = _client(tmp_path, handler)
    try:
        with pytest.raises(CatalogError) as raised:
            catalog.match_movie("Arrival", 2016)
    finally:
        http_client.close()

    assert "token" not in str(raised.value)


def test_wraps_invalid_json_success_response(tmp_path: Path) -> None:
    catalog, http_client = _client(
        tmp_path,
        lambda _request: httpx.Response(200, text="not json"),
    )
    try:
        with pytest.raises(CatalogError, match="not valid JSON"):
            catalog.match_movie("Arrival", 2016)
    finally:
        http_client.close()

    assert list((tmp_path / "cache").glob("*.json")) == []


def test_rejects_invalid_success_payload_without_poisoning_cache(tmp_path: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        invalid = _movie(1, "Broken", 2020)
        invalid["vote_average"] = 99
        return httpx.Response(200, json={"results": [invalid]})

    catalog, http_client = _client(tmp_path, handler)
    try:
        with pytest.raises(CatalogError, match="metadata is invalid"):
            catalog.match_movie("Broken", 2020)
    finally:
        http_client.close()

    assert list((tmp_path / "cache").glob("*.json")) == []


def test_discards_corrupt_cache_and_refetches_valid_payload(tmp_path: Path) -> None:
    request_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, json={"results": [_movie(1, "Arrival", 2016)]})

    catalog, http_client = _client(tmp_path, handler)
    try:
        assert catalog.match_movie("Arrival", 2016).status == "matched"
        cache_file = next((tmp_path / "cache").glob("*.json"))
        cache_file.write_text("not json", encoding="utf-8")
        assert catalog.match_movie("Arrival", 2016).status == "matched"
    finally:
        http_client.close()

    assert request_count == 2
    assert json.loads(cache_file.read_text(encoding="utf-8"))["results"][0]["id"] == 1
