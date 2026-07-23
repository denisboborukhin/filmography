from __future__ import annotations

import json
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import httpx
import pytest
from filmography.ai import AIError, OpenAICompatibleClient, score_target_id
from filmography.builder import (
    build_snapshot,
    load_snapshot,
    refresh_ai_recommendations,
    write_snapshot,
)
from filmography.cli import build_parser, main
from filmography.models import (
    FilmCredits,
    FilmMetadata,
    PersonCredit,
    Recommendation,
    Snapshot,
    WatchedFilm,
    WatchlistFilm,
)
from filmography.tmdb import CatalogMatch, TMDBClient


def _sources(tmp_path: Path) -> tuple[Path, Path]:
    reviews = tmp_path / "reviews"
    reviews.mkdir()
    (reviews / "Arrival (2016).md").write_text(
        "---\nrating: 9\nwatchedAt: 2026-01-01\n---\nThoughtful science fiction.",
        encoding="utf-8",
    )
    watchlist = tmp_path / "Watchlist.md"
    watchlist.write_text("- Persona (1966) — interest: 8\n", encoding="utf-8")
    return reviews, watchlist


def _previous_snapshot() -> Snapshot:
    generated = datetime(2026, 7, 19, tzinfo=UTC)
    return Snapshot(
        generated_at=generated,
        recommendations_generated_at=generated,
        ai_discoveries=[
            Recommendation(
                tmdb_id=100,
                title="Previous Pick",
                year=2000,
                predicted_rating=8,
                rationale="Previously verified.",
                source="ai",
                generated_at=generated,
                provider="openai-compatible",
                model="old-model",
            )
        ],
    )


def test_builder_is_deterministic_with_injected_time_and_preserves_previous_ai(
    tmp_path: Path,
) -> None:
    reviews, watchlist = _sources(tmp_path)
    now = datetime(2026, 7, 20, tzinfo=UTC)

    first = build_snapshot(
        reviews,
        watchlist,
        previous=_previous_snapshot(),
        generated_at=now,
    ).snapshot
    second = build_snapshot(
        reviews,
        watchlist,
        previous=_previous_snapshot(),
        generated_at=now,
    ).snapshot

    assert first == second
    assert [item.title for item in first.ai_discoveries] == ["Previous Pick"]
    assert first.recommendations_generated_at == datetime(2026, 7, 19, tzinfo=UTC)


def test_builder_drops_previous_recommendation_that_is_now_watchlisted(tmp_path: Path) -> None:
    reviews, watchlist = _sources(tmp_path)
    watchlist.write_text("- Previous Pick\n", encoding="utf-8")

    snapshot = build_snapshot(
        reviews,
        watchlist,
        previous=_previous_snapshot(),
        generated_at=datetime(2026, 7, 20, tzinfo=UTC),
    ).snapshot

    assert snapshot.ai_discoveries == []
    assert snapshot.recommendations_generated_at is None


def test_builder_preserves_previous_ai_scores_until_a_successful_refresh(
    tmp_path: Path,
) -> None:
    reviews = tmp_path / "reviews"
    reviews.mkdir()
    watchlist = tmp_path / "Watchlist.md"
    watchlist.write_text("Moon (2009)\n", encoding="utf-8")
    generated_at = datetime(2026, 7, 20, tzinfo=UTC)
    previous = Snapshot(
        generated_at=generated_at,
        watchlist=[
            WatchlistFilm(
                tmdb_id=17431,
                title="Moon",
                year=2009,
                interest=8.4,
                interest_source="ai",
            )
        ],
        deterministic_discoveries=[
            Recommendation(
                tmdb_id=200,
                title="Discovery",
                year=2022,
                predicted_rating=8.6,
                score_source="ai",
                rationale="Catalog description.",
                source="deterministic",
                generated_at=generated_at,
            )
        ],
    )

    class StableCatalog:
        def match_movie(
            self,
            title: str,
            _year: int | None = None,
            *,
            allow_popular_without_year: bool = False,
        ) -> CatalogMatch:
            assert title == "Moon"
            return CatalogMatch(
                "matched",
                FilmMetadata(tmdb_id=17431, title="Moon", year=2009, vote_average=7.6),
            )

        def discover_movies(self, _genres: list[str]) -> list[FilmMetadata]:
            return [
                FilmMetadata(
                    tmdb_id=200,
                    title="Discovery",
                    year=2022,
                    vote_average=8,
                )
            ]

    snapshot = build_snapshot(
        reviews,
        watchlist,
        catalog=cast(TMDBClient, StableCatalog()),
        previous=previous,
        generated_at=generated_at,
    ).snapshot

    assert snapshot.watchlist[0].interest == 8.4
    assert snapshot.watchlist[0].interest_source == "ai"
    assert snapshot.deterministic_discoveries[0].predicted_rating == 8.6
    assert snapshot.deterministic_discoveries[0].score_source == "ai"


def test_builder_enriches_series_when_movie_lookup_is_unresolved(tmp_path: Path) -> None:
    reviews = tmp_path / "reviews"
    reviews.mkdir()
    watchlist = tmp_path / "Watchlist.md"
    watchlist.write_text("Ted Lasso\n", encoding="utf-8")

    class SeriesAwareCatalog:
        def match_movie(
            self,
            _title: str,
            _year: int | None = None,
            *,
            allow_popular_without_year: bool = False,
        ) -> CatalogMatch:
            assert allow_popular_without_year
            return CatalogMatch("unresolved", None)

        def match_tv(
            self,
            title: str,
            _year: int | None = None,
            *,
            allow_popular_without_year: bool = False,
        ) -> CatalogMatch:
            assert title == "Ted Lasso"
            assert allow_popular_without_year
            return CatalogMatch(
                "matched",
                FilmMetadata(
                    tmdb_id=97546,
                    media_type="tv",
                    title="Ted Lasso",
                    year=2020,
                    overview="An American coach manages a football club.",
                    genres=["Comedy"],
                    vote_average=8.5,
                    popularity=100,
                ),
            )

        def discover_movies(self, _genres: list[str]) -> list[object]:
            return []

    result = build_snapshot(reviews, watchlist, catalog=cast(TMDBClient, SeriesAwareCatalog()))

    assert all(diagnostic.code != "catalog-unresolved" for diagnostic in result.diagnostics)
    assert result.snapshot.watchlist[0].media_type == "tv"
    assert result.snapshot.watchlist[0].tmdb_id == 97546
    assert result.snapshot.watchlist[0].overview == "An American coach manages a football club."


def test_builder_enriches_watched_credits_and_keeps_metadata_when_credits_fail(
    tmp_path: Path,
) -> None:
    reviews = tmp_path / "reviews"
    reviews.mkdir()
    (reviews / "Arrival (2016).md").write_text("---\nrating: 9\n---\nReview", encoding="utf-8")
    watchlist = tmp_path / "Watchlist.md"
    watchlist.write_text("", encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/3/search/movie":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 329865,
                            "title": "Arrival",
                            "release_date": "2016-11-10",
                            "vote_average": 7.6,
                        }
                    ]
                },
            )
        if request.url.path == "/3/movie/329865/credits":
            return httpx.Response(503)
        if request.url.path == "/3/genre/movie/list":
            return httpx.Response(200, json={"genres": []})
        if request.url.path == "/3/discover/movie":
            return httpx.Response(200, json={"results": []})
        raise AssertionError(f"unexpected path: {request.url.path}")

    http_client = httpx.Client(
        base_url="https://catalog.test/3/",
        transport=httpx.MockTransport(handler),
    )
    catalog = TMDBClient("token", tmp_path / "cache", http_client=http_client)
    try:
        result = build_snapshot(
            reviews,
            watchlist,
            catalog=catalog,
            previous=Snapshot(
                generated_at=datetime(2026, 7, 20, tzinfo=UTC),
                watched=[
                    WatchedFilm(
                        tmdb_id=329865,
                        title="Arrival",
                        year=2016,
                        rating=8,
                        credits=FilmCredits(
                            filmmaker=PersonCredit(tmdb_id=137427, name="Denis Villeneuve")
                        ),
                    )
                ],
            ),
        )
    finally:
        http_client.close()

    assert result.snapshot.watched[0].tmdb_id == 329865
    assert result.snapshot.watched[0].credits.filmmaker is not None
    assert result.snapshot.watched[0].credits.filmmaker.name == "Denis Villeneuve"
    assert any(diagnostic.code == "catalog-credits-failed" for diagnostic in result.diagnostics)


def test_successful_local_recommendation_run_records_generation_time(tmp_path: Path) -> None:
    reviews = tmp_path / "reviews"
    reviews.mkdir()
    watchlist = tmp_path / "Watchlist.md"
    watchlist.write_text("", encoding="utf-8")
    now = datetime(2026, 7, 20, 10, tzinfo=UTC)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/3/genre/movie/list":
            return httpx.Response(200, json={"genres": []})
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 1,
                        "title": "Discovery",
                        "release_date": "2020-01-01",
                        "vote_average": 8,
                    }
                ]
            },
        )

    http_client = httpx.Client(
        base_url="https://catalog.test/3/",
        transport=httpx.MockTransport(handler),
    )
    catalog = TMDBClient("token", tmp_path / "cache", http_client=http_client)
    try:
        snapshot = build_snapshot(
            reviews,
            watchlist,
            catalog=catalog,
            generated_at=now,
        ).snapshot
    finally:
        http_client.close()

    assert [item.title for item in snapshot.deterministic_discoveries] == ["Discovery"]
    assert snapshot.recommendations_generated_at == now


def test_watchlist_without_year_enriches_with_popular_catalog_match(tmp_path: Path) -> None:
    reviews = tmp_path / "reviews"
    reviews.mkdir()
    watchlist = tmp_path / "Watchlist.md"
    watchlist.write_text("Меню\n", encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/3/genre/movie/list":
            return httpx.Response(200, json={"genres": []})
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 1,
                        "title": "Menu",
                        "release_date": "2012-01-01",
                        "popularity": 10,
                    },
                    {
                        "id": 593643,
                        "title": "The Menu",
                        "release_date": "2022-11-17",
                        "popularity": 90,
                    },
                ]
            },
        )

    http_client = httpx.Client(
        base_url="https://catalog.test/3/",
        transport=httpx.MockTransport(handler),
    )
    catalog = TMDBClient("token", tmp_path / "cache", http_client=http_client)
    try:
        snapshot = build_snapshot(reviews, watchlist, catalog=catalog).snapshot
    finally:
        http_client.close()

    assert snapshot.watchlist[0].title == "The Menu"
    assert snapshot.watchlist[0].tmdb_id == 593643
    assert snapshot.watchlist[0].interest == 6.5
    assert snapshot.watchlist[0].interest_source == "local"


def test_watchlist_expected_rating_is_predicted_when_missing_and_preserves_manual(
    tmp_path: Path,
) -> None:
    reviews = tmp_path / "reviews"
    reviews.mkdir()
    (reviews / "Arrival (2016).md").write_text(
        "---\nrating: 9\n---\nThoughtful science fiction.",
        encoding="utf-8",
    )
    watchlist = tmp_path / "Watchlist.md"
    watchlist.write_text(
        "Moon (2009)\nManual Pick (2020) — interest: 4.5\n",
        encoding="utf-8",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/3/search/movie":
            query = request.url.params["query"]
            if query == "Arrival":
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {
                                "id": 1,
                                "title": "Arrival",
                                "release_date": "2016-01-01",
                                "genre_ids": [878],
                                "vote_average": 8,
                            }
                        ]
                    },
                )
            if query == "Moon":
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {
                                "id": 17431,
                                "title": "Moon",
                                "release_date": "2009-01-01",
                                "genre_ids": [878],
                                "overview": "A lunar worker nears the end of his contract.",
                                "vote_average": 7.6,
                            }
                        ]
                    },
                )
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 2,
                            "title": "Manual Pick",
                            "release_date": "2020-01-01",
                            "vote_average": 9,
                        }
                    ]
                },
            )
        if request.url.path in {"/3/search/tv", "/3/discover/movie"}:
            return httpx.Response(200, json={"results": []})
        if request.url.path == "/3/movie/1/credits":
            return httpx.Response(200, json={"cast": [], "crew": []})
        if request.url.path in {"/3/genre/movie/list", "/3/genre/tv/list"}:
            return httpx.Response(200, json={"genres": [{"id": 878, "name": "Science Fiction"}]})
        raise AssertionError(f"unexpected path: {request.url.path}")

    http_client = httpx.Client(
        base_url="https://catalog.test/3/",
        transport=httpx.MockTransport(handler),
    )
    catalog = TMDBClient("token", tmp_path / "cache", http_client=http_client)
    try:
        snapshot = build_snapshot(reviews, watchlist, catalog=catalog).snapshot
    finally:
        http_client.close()

    moon = next(item for item in snapshot.watchlist if item.title == "Moon")
    manual = next(item for item in snapshot.watchlist if item.title == "Manual Pick")
    assert moon.interest == 7.8
    assert moon.interest_source == "local"
    assert manual.interest == 4.5
    assert manual.interest_source == "manual"


def test_snapshot_write_is_atomic_round_trip_and_contains_no_credentials(tmp_path: Path) -> None:
    path = tmp_path / "public" / "data" / "filmography.json"
    snapshot = _previous_snapshot()

    write_snapshot(snapshot, path)

    assert load_snapshot(path) == snapshot
    content = path.read_text(encoding="utf-8")
    assert "API_KEY" not in content
    assert "/Users/" not in content
    assert not path.with_suffix(".json.tmp").exists()


def test_failed_ai_refresh_leaves_existing_snapshot_unchanged(tmp_path: Path) -> None:
    original = _previous_snapshot()
    provider_http = httpx.Client(
        base_url="https://provider.test/v1/",
        transport=httpx.MockTransport(lambda _request: httpx.Response(500)),
    )
    catalog_http = httpx.Client(
        base_url="https://catalog.test/3/",
        transport=httpx.MockTransport(lambda _request: httpx.Response(500)),
    )
    ai_client = OpenAICompatibleClient(
        "secret",
        "new-model",
        "https://provider.test/v1",
        http_client=provider_http,
    )
    catalog = TMDBClient("token", tmp_path / "cache", http_client=catalog_http)
    before = original.model_dump_json()
    try:
        with pytest.raises(AIError):
            refresh_ai_recommendations(original, ai_client, catalog)
    finally:
        provider_http.close()
        catalog_http.close()

    assert original.model_dump_json() == before
    assert original.ai_discoveries[0].model == "old-model"


def test_ai_refresh_requests_extra_candidates_and_reports_rejections(tmp_path: Path) -> None:
    captured_count: int | None = None
    snapshot = Snapshot(
        generated_at=datetime(2026, 7, 20, tzinfo=UTC),
        watchlist=[WatchlistFilm(title="Existing", year=2020)],
    )

    def provider_handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_count
        body: object = json.loads(request.content)
        assert isinstance(body, dict)
        typed_body = cast(dict[str, object], body)
        messages = typed_body["messages"]
        assert isinstance(messages, list)
        typed_messages = cast(list[object], messages)
        user_message = typed_messages[1]
        assert isinstance(user_message, dict)
        typed_user_message = cast(dict[str, object], user_message)
        profile: object = json.loads(str(typed_user_message["content"]))
        assert isinstance(profile, dict)
        typed_profile = cast(dict[str, object], profile)
        response_format = cast(dict[str, object], typed_body["response_format"])
        json_schema = cast(dict[str, object], response_format["json_schema"])
        if json_schema["name"] == "film_scores":
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {"watchlistScores": [], "discoveryScores": []}
                                )
                            }
                        }
                    ]
                },
            )
        raw_count = typed_profile["count"]
        assert isinstance(raw_count, int)
        captured_count = raw_count
        result = {
            "recommendations": [
                {
                    "title": "Existing",
                    "year": 2020,
                    "predictedRating": 8,
                    "rationale": "Already in the watchlist.",
                }
            ]
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(result)}}]},
        )

    provider_http = httpx.Client(
        base_url="https://provider.test/v1/",
        transport=httpx.MockTransport(provider_handler),
    )
    catalog_http = httpx.Client(
        base_url="https://catalog.test/3/",
        transport=httpx.MockTransport(lambda _request: httpx.Response(500)),
    )
    ai_client = OpenAICompatibleClient(
        "secret", "new-model", "https://provider.test/v1", http_client=provider_http
    )
    catalog = TMDBClient("token", tmp_path / "cache", http_client=catalog_http)
    try:
        with pytest.raises(AIError) as raised:
            refresh_ai_recommendations(snapshot, ai_client, catalog, limit=2)
    finally:
        provider_http.close()
        catalog_http.close()

    assert captured_count == 6
    assert "excluded existing film: Existing (2020)" in str(raised.value)


def test_recommend_cli_failure_preserves_previous_verified_ai_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reviews = tmp_path / "reviews"
    reviews.mkdir()
    watchlist = tmp_path / "Watchlist.md"
    watchlist.write_text("", encoding="utf-8")
    output = tmp_path / "filmography.json"
    write_snapshot(_previous_snapshot(), output)

    class EmptyCatalog:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> EmptyCatalog:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def discover_movies(self, _genres: list[str]) -> list[object]:
            return []

    class FailingAI:
        def suggest(self, *_args: object, **_kwargs: object) -> None:
            raise AIError("provider unavailable")

        def score_targets(self, *_args: object, **_kwargs: object) -> None:
            raise AIError("provider unavailable")

    def failing_ai_factory(_stack: ExitStack) -> FailingAI:
        return FailingAI()

    monkeypatch.setenv("TMDB_ACCESS_TOKEN", "catalog-token")
    monkeypatch.setattr("filmography.cli.TMDBClient", EmptyCatalog)
    monkeypatch.setattr("filmography.cli._create_ai_client", failing_ai_factory)

    result = main(
        [
            "recommend",
            "--reviews",
            str(reviews),
            "--watchlist",
            str(watchlist),
            "--output",
            str(output),
        ]
    )

    saved = load_snapshot(output)
    assert result == 1
    assert saved is not None
    assert [item.tmdb_id for item in saved.ai_discoveries] == [100]
    assert saved.ai_discoveries[0].generated_at == datetime(2026, 7, 19, tzinfo=UTC)
    assert saved.ai_discoveries[0].model == "old-model"


def test_successful_ai_refresh_replaces_previous_set_and_removes_local_duplicate(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 20, 12, tzinfo=UTC)
    original = _previous_snapshot()
    local_pick = Recommendation(
        tmdb_id=17431,
        title="Moon",
        year=2009,
        predicted_rating=8,
        rationale="Local match.",
        source="deterministic",
        generated_at=now,
    )
    original = original.model_copy(update={"deterministic_discoveries": [local_pick]})
    suggestion_result: dict[str, object] = {
        "recommendations": [
            {
                "title": "Moon",
                "year": 2009,
                "predictedRating": 8.5,
                "rationale": "Its isolation matches your science-fiction reviews.",
            }
        ]
    }

    def provider_handler(request: httpx.Request) -> httpx.Response:
        body: object = json.loads(request.content)
        assert isinstance(body, dict)
        response_format = cast(dict[str, object], body["response_format"])
        json_schema = cast(dict[str, object], response_format["json_schema"])
        result: dict[str, object] = (
            suggestion_result
            if json_schema["name"] == "film_recommendations"
            else {"watchlistScores": [], "discoveryScores": []}
        )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(result)}}]},
        )

    provider_http = httpx.Client(
        base_url="https://provider.test/v1/",
        transport=httpx.MockTransport(provider_handler),
    )
    catalog_http = httpx.Client(
        base_url="https://catalog.test/3/",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 17431,
                            "title": "Moon",
                            "release_date": "2009-06-12",
                            "overview": "A lunar worker nears the end of his contract.",
                        }
                    ]
                },
            )
        ),
    )
    ai_client = OpenAICompatibleClient(
        "secret", "new-model", "https://provider.test/v1", http_client=provider_http
    )
    catalog = TMDBClient("token", tmp_path / "cache", http_client=catalog_http)
    try:
        result = refresh_ai_recommendations(
            original,
            ai_client,
            catalog,
            generated_at=now,
            limit=1,
        ).snapshot
    finally:
        provider_http.close()
        catalog_http.close()

    assert [item.title for item in result.ai_discoveries] == ["Moon"]
    assert result.ai_discoveries[0].model == "new-model"
    assert result.deterministic_discoveries == []
    assert result.recommendations_generated_at == now


def test_ai_refresh_scores_watchlist_and_taste_matches_on_the_users_scale(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 20, 12, tzinfo=UTC)
    watched = [
        WatchedFilm(title="Eight", rating=8),
        WatchedFilm(title="Eight and a half", rating=8.5),
        WatchedFilm(title="Nine", rating=9),
    ]
    local_watchlist = WatchlistFilm(
        tmdb_id=20,
        title="Score Me",
        year=2020,
        interest=8,
        interest_source="local",
    )
    manual_watchlist = WatchlistFilm(
        tmdb_id=21,
        title="Manual",
        year=2021,
        interest=6,
        interest_source="manual",
    )
    taste_match = Recommendation(
        tmdb_id=22,
        title="Taste Match",
        year=2022,
        predicted_rating=8,
        rationale="Local rationale.",
        source="deterministic",
        generated_at=now,
    )
    snapshot = Snapshot(
        generated_at=now,
        watched=watched,
        watchlist=[local_watchlist, manual_watchlist],
        deterministic_discoveries=[taste_match],
    )
    suggestion_result = {
        "recommendations": [
            {
                "title": "Moon",
                "year": 2009,
                "predictedRating": 10,
                "rationale": "Its isolation suits the reflective reviews.",
            }
        ]
    }
    score_result = {
        "watchlistScores": [
            {
                "target": score_target_id("watchlist", local_watchlist),
                "predictedRating": 10,
            }
        ],
        "discoveryScores": [
            {
                "target": score_target_id("discovery", taste_match),
                "predictedRating": 9,
            }
        ],
    }

    def provider_handler(request: httpx.Request) -> httpx.Response:
        body: object = json.loads(request.content)
        assert isinstance(body, dict)
        response_format = cast(dict[str, object], body["response_format"])
        json_schema = cast(dict[str, object], response_format["json_schema"])
        result = (
            suggestion_result if json_schema["name"] == "film_recommendations" else score_result
        )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(result)}}]},
        )

    provider_http = httpx.Client(
        base_url="https://provider.test/v1/",
        transport=httpx.MockTransport(provider_handler),
    )
    catalog_http = httpx.Client(
        base_url="https://catalog.test/3/",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 17431,
                            "title": "Moon",
                            "release_date": "2009-06-12",
                        }
                    ]
                },
            )
        ),
    )
    ai_client = OpenAICompatibleClient(
        "secret", "new-model", "https://provider.test/v1", http_client=provider_http
    )
    catalog = TMDBClient("token", tmp_path / "cache", http_client=catalog_http)
    try:
        result = refresh_ai_recommendations(
            snapshot,
            ai_client,
            catalog,
            generated_at=now,
            limit=1,
        ).snapshot
    finally:
        provider_http.close()
        catalog_http.close()

    scored_watchlist = {film.title: film for film in result.watchlist}
    assert scored_watchlist["Score Me"].interest == 9.1
    assert scored_watchlist["Score Me"].interest_source == "ai"
    assert scored_watchlist["Manual"].interest == 6
    assert scored_watchlist["Manual"].interest_source == "manual"
    assert result.deterministic_discoveries[0].predicted_rating == 8.7
    assert result.deterministic_discoveries[0].score_source == "ai"
    assert result.ai_discoveries[0].predicted_rating == 9.1


def test_ai_refresh_rejects_fewer_than_five_verified_picks_for_standard_run(
    tmp_path: Path,
) -> None:
    provider_result = {
        "recommendations": [
            {
                "title": f"Film {index}",
                "year": 2020 + index,
                "predictedRating": 8,
                "rationale": f"Specific rationale {index}.",
            }
            for index in range(4)
        ]
    }
    provider_http = httpx.Client(
        base_url="https://provider.test/v1/",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps(provider_result)}}]},
            )
        ),
    )

    def catalog_handler(request: httpx.Request) -> httpx.Response:
        title = request.url.params["query"]
        index = int(title.removeprefix("Film "))
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 100 + index,
                        "title": title,
                        "release_date": f"{2020 + index}-01-01",
                    }
                ]
            },
        )

    catalog_http = httpx.Client(
        base_url="https://catalog.test/3/",
        transport=httpx.MockTransport(catalog_handler),
    )
    ai_client = OpenAICompatibleClient(
        "secret", "new-model", "https://provider.test/v1", http_client=provider_http
    )
    catalog = TMDBClient("token", tmp_path / "cache", http_client=catalog_http)
    try:
        with pytest.raises(AIError, match="at least 5 required"):
            refresh_ai_recommendations(
                Snapshot(generated_at=datetime(2026, 7, 20, tzinfo=UTC)),
                ai_client,
                catalog,
                limit=8,
            )
    finally:
        provider_http.close()
        catalog_http.close()


def test_check_and_build_cli_without_runtime_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reviews, watchlist = _sources(tmp_path)
    output = tmp_path / "filmography.json"
    monkeypatch.delenv("TMDB_ACCESS_TOKEN", raising=False)

    assert main(["check", "--reviews", str(reviews), "--watchlist", str(watchlist)]) == 0
    assert (
        main(
            [
                "build",
                "--reviews",
                str(reviews),
                "--watchlist",
                str(watchlist),
                "--output",
                str(output),
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert "valid: 1 reviews, 1 watchlist films" in captured.out
    assert "wrote" in captured.out
    snapshot = load_snapshot(output)
    assert snapshot is not None and snapshot.watched[0].title == "Arrival"


def test_recommend_cli_rejects_invalid_ai_max_tokens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reviews, watchlist = _sources(tmp_path)
    output = tmp_path / "filmography.json"

    class EmptyCatalog:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> EmptyCatalog:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def discover_movies(self, _genres: list[str]) -> list[object]:
            return []

    monkeypatch.setenv("TMDB_ACCESS_TOKEN", "catalog-token")
    monkeypatch.setenv("FILMOGRAPHY_AI_API_KEY", "ai-token")
    monkeypatch.setenv("FILMOGRAPHY_AI_MODEL", "test-model")
    monkeypatch.setenv("FILMOGRAPHY_AI_MAX_TOKENS", "too-many")
    monkeypatch.setattr("filmography.cli.TMDBClient", EmptyCatalog)

    result = main(
        [
            "recommend",
            "--reviews",
            str(reviews),
            "--watchlist",
            str(watchlist),
            "--output",
            str(output),
        ]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert "FILMOGRAPHY_AI_MAX_TOKENS must be an integer" in captured.err
    assert not output.exists()


def test_cli_defaults_match_static_frontend_and_ignored_cache_paths() -> None:
    args = build_parser().parse_args(
        ["build", "--reviews", "reviews", "--watchlist", "Watchlist.md"]
    )

    assert args.output == Path("public/data/filmography.json")
    assert args.cache_dir == Path(".filmography-cache/tmdb")

    recommend_args = build_parser().parse_args(
        ["recommend", "--reviews", "reviews", "--watchlist", "Watchlist.md"]
    )
    assert recommend_args.count == 10

    with pytest.raises(SystemExit):
        build_parser().parse_args(
            [
                "recommend",
                "--reviews",
                "reviews",
                "--watchlist",
                "Watchlist.md",
                "--count",
                "4",
            ]
        )
