from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import httpx
import pytest
from filmography.ai import (
    AIError,
    AISuggestionBatch,
    OpenAICompatibleClient,
    resolve_ai_suggestions,
)
from filmography.models import WatchedFilm
from filmography.tmdb import TMDBClient


def _provider_client(
    handler: httpx.MockTransport,
) -> tuple[OpenAICompatibleClient, httpx.Client]:
    http_client = httpx.Client(base_url="https://provider.test/v1/", transport=handler)
    return (
        OpenAICompatibleClient(
            "super-secret",
            "test-model",
            "https://provider.test/v1",
            http_client=http_client,
        ),
        http_client,
    )


def test_ai_client_sends_complete_profile_and_parses_structured_output() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        body_value: object = json.loads(request.content)
        assert isinstance(body_value, dict)
        captured["body"] = body_value
        result = {
            "recommendations": [
                {
                    "title": "Moon",
                    "year": 2009,
                    "predictedRating": 8.5,
                    "rationale": "Its isolation matches themes in your reviews.",
                }
            ]
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(result)}}]},
        )

    ai_client, http_client = _provider_client(httpx.MockTransport(handler))
    watched = [WatchedFilm(title="Arrival", year=2016, rating=9, review="A complete review.")]
    try:
        batch = ai_client.suggest(watched, [], prompt="quiet science fiction", count=1)
    finally:
        http_client.close()

    assert batch.recommendations[0].title == "Moon"
    assert captured["path"] == "/v1/chat/completions"
    request_body = cast(dict[str, object], captured["body"])
    assert request_body["model"] == "test-model"
    serialized_body = json.dumps(request_body)
    assert "A complete review." in serialized_body
    assert "super-secret" not in serialized_body
    assert "exclusions" in serialized_body
    assert cast(dict[str, object], request_body["response_format"])["type"] == "json_schema"
    messages = cast(list[dict[str, str]], request_body["messages"])
    assert "Do not use Markdown" in messages[0]["content"]
    assert "Never recommend any title" in messages[0]["content"]


def test_ai_client_extracts_fenced_json_from_compat_provider() -> None:
    result = {
        "recommendations": [
            {
                "title": "Moneyball",
                "year": 2011,
                "predictedRating": 8,
                "rationale": "Data-driven sports drama fits the profile.",
            }
        ]
    }
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={"choices": [{"message": {"content": f"```json\n{json.dumps(result)}\n```"}}]},
        )
    )
    ai_client, http_client = _provider_client(transport)
    try:
        batch = ai_client.suggest([], [], count=1)
    finally:
        http_client.close()

    assert batch.recommendations[0].title == "Moneyball"


def test_ai_client_normalizes_provider_score_aliases() -> None:
    result = {
        "recommendations": [
            {
                "title": "Dumb Money",
                "year": 2023,
                "score": 7.5,
                "rationale": "Crowd-driven finance story fits the profile.",
            }
        ]
    }
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(result)}}]},
        )
    )
    ai_client, http_client = _provider_client(transport)
    try:
        batch = ai_client.suggest([], [], count=1)
    finally:
        http_client.close()

    assert batch.recommendations[0].title == "Dumb Money"
    assert batch.recommendations[0].predicted_rating == 7.5


def test_ai_client_drops_provider_suggestions_without_year() -> None:
    result = {
        "recommendations": [
            {
                "title": "Ted lesso",
                "year": None,
                "rating": 6.5,
                "rationale": "Not a verifiable film recommendation.",
            },
            {
                "title": "The Menu",
                "year": 2022,
                "rating": 7.7,
                "rationale": "Satirical pressure fits the profile.",
            },
        ]
    }
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(result)}}]},
        )
    )
    ai_client, http_client = _provider_client(transport)
    try:
        batch = ai_client.suggest([], [], count=2)
    finally:
        http_client.close()

    assert [item.title for item in batch.recommendations] == ["The Menu"]
    assert batch.recommendations[0].predicted_rating == 7.7


def test_ai_client_accepts_top_level_recommendation_array() -> None:
    result = [
        {
            "title": "The Menu",
            "year": 2022,
            "rating": 8,
            "rationale": "Satirical tension matches the profile.",
        }
    ]
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(result)}}]},
        )
    )
    ai_client, http_client = _provider_client(transport)
    try:
        batch = ai_client.suggest([], [], count=1)
    finally:
        http_client.close()

    assert batch.recommendations[0].title == "The Menu"
    assert batch.recommendations[0].predicted_rating == 8


def test_ai_client_drops_unrecoverable_items_from_provider_json() -> None:
    result = {
        "recommendations": [
            {
                "title": "Dumb Money",
                "year": 2023,
                "rating": 8.0,
                "rationale": "Echoes entrepreneurial optimism.",
            },
            {
                "title": "Ted lesso",
                "year": None,
                "rating": 6.5,
                "rationale": "This is a series and has no film year.",
            },
            {
                "title": "The Menu",
                "year": 2022,
                "rating": 7.5,
                "extraProviderField": "ignored",
                "rationale": "A sharp satirical take.",
            },
        ]
    }
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(result)}}]},
        )
    )
    ai_client, http_client = _provider_client(transport)
    try:
        batch = ai_client.suggest([], [], count=3)
    finally:
        http_client.close()

    assert [item.title for item in batch.recommendations] == ["Dumb Money", "The Menu"]
    assert [item.predicted_rating for item in batch.recommendations] == [8, 7.5]


def test_ai_client_parses_openrouter_markdown_recommendations() -> None:
    markdown = """**Dumb Money (2023)** - predicted rating: 8/10.
Matches your interest in finance, systems, and recent crowd-driven stories.

**The Social Network (2010)** - Strong fit for your business and tech preferences.
"""
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={"choices": [{"message": {"content": markdown}}]},
        )
    )
    ai_client, http_client = _provider_client(transport)
    try:
        batch = ai_client.suggest([], [], count=2)
    finally:
        http_client.close()

    assert [item.title for item in batch.recommendations] == ["Dumb Money", "The Social Network"]
    assert batch.recommendations[0].predicted_rating == 8
    assert batch.recommendations[1].predicted_rating == 7.5
    assert "business and tech" in batch.recommendations[1].rationale


@pytest.mark.parametrize(
    "response",
    [
        {"not_choices": []},
        {"choices": [{"message": {"content": "not json"}}]},
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "recommendations": [
                                    {
                                        "title": "Film",
                                        "year": 2020,
                                        "predictedRating": 8.25,
                                        "rationale": "Invalid step",
                                    }
                                ]
                            }
                        )
                    }
                }
            ]
        },
    ],
)
def test_ai_client_rejects_malformed_provider_output(response: dict[str, object]) -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=response))
    ai_client, http_client = _provider_client(transport)
    try:
        with pytest.raises(AIError):
            ai_client.suggest([], [])
    finally:
        http_client.close()


def test_ai_client_wraps_http_failures_without_leaking_key() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(429, text="limited"))
    ai_client, http_client = _provider_client(transport)
    try:
        with pytest.raises(AIError) as raised:
            ai_client.suggest([], [])
    finally:
        http_client.close()

    assert "super-secret" not in str(raised.value)
    assert "429 Too Many Requests" in str(raised.value)
    assert "--count" in str(raised.value)


def test_resolver_verifies_tmdb_and_excludes_seen_ambiguous_and_duplicate_films(
    tmp_path: Path,
) -> None:
    batch = AISuggestionBatch.model_validate(
        {
            "recommendations": [
                {
                    "title": "Seen",
                    "year": 2020,
                    "predictedRating": 9,
                    "rationale": "Should be excluded",
                },
                {
                    "title": "Moon",
                    "year": 2009,
                    "predictedRating": 8.5,
                    "rationale": "Isolation and precise science fiction.",
                },
                {
                    "title": "Moon",
                    "year": 2009,
                    "predictedRating": 8,
                    "rationale": "Duplicate",
                },
                {
                    "title": "Crash",
                    "year": 1996,
                    "predictedRating": 7,
                    "rationale": "Ambiguous",
                },
            ]
        }
    )

    def catalog_handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["query"]
        if query == "Moon":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 17431,
                            "title": "Moon",
                            "original_title": "Moon",
                            "release_date": "2009-06-12",
                            "overview": "A lunar worker nears the end of his contract.",
                            "vote_average": 7.6,
                            "popularity": 20,
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 1,
                        "title": "Crash",
                        "release_date": "1996-01-01",
                    },
                    {
                        "id": 2,
                        "title": "Crash",
                        "release_date": "1996-02-02",
                    },
                ]
            },
        )

    http_client = httpx.Client(
        base_url="https://catalog.test/3/",
        transport=httpx.MockTransport(catalog_handler),
    )
    catalog = TMDBClient("token", tmp_path / "cache", http_client=http_client)
    try:
        result = resolve_ai_suggestions(
            batch,
            catalog,
            [WatchedFilm(tmdb_id=10, title="Seen", rating=8)],
            [],
            generated_at=datetime(2026, 7, 20, tzinfo=UTC),
            provider="openai-compatible",
            model="test-model",
        )
    finally:
        http_client.close()

    assert [item.tmdb_id for item in result.recommendations] == [17431]
    assert result.recommendations[0].source == "ai"
    assert len(result.warnings) == 3
