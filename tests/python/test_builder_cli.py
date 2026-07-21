from __future__ import annotations

import json
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import httpx
import pytest
from filmography.ai import AIError, OpenAICompatibleClient
from filmography.builder import (
    build_snapshot,
    load_snapshot,
    refresh_ai_recommendations,
    write_snapshot,
)
from filmography.cli import build_parser, main
from filmography.models import Recommendation, Snapshot, WatchlistFilm
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


def test_builder_warns_when_unresolved_movie_title_is_a_series(tmp_path: Path) -> None:
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

        def find_tv_titles(self, title: str) -> tuple[str, ...]:
            assert title == "Ted Lasso"
            return ("Ted Lasso (2020)",)

        def discover_movies(self, _genres: list[str]) -> list[object]:
            return []

    result = build_snapshot(reviews, watchlist, catalog=cast(TMDBClient, SeriesAwareCatalog()))

    messages = [diagnostic.message for diagnostic in result.diagnostics]
    assert any("unresolved TMDB movie match for Ted Lasso" in message for message in messages)
    assert any("TMDB TV match: Ted Lasso (2020)" in message for message in messages)
    assert any("film-only snapshot" in message for message in messages)


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
    provider_result = {
        "recommendations": [
            {
                "title": "Moon",
                "year": 2009,
                "predictedRating": 8.5,
                "rationale": "Its isolation matches your science-fiction reviews.",
            }
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


def test_cli_defaults_match_static_frontend_and_ignored_cache_paths() -> None:
    args = build_parser().parse_args(
        ["build", "--reviews", "reviews", "--watchlist", "Watchlist.md"]
    )

    assert args.output == Path("public/data/filmography.json")
    assert args.cache_dir == Path(".filmography-cache/tmdb")
