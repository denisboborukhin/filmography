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
    score_target_id,
)
from filmography.models import Recommendation, WatchedFilm, WatchlistFilm
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
    watchlist = [
        WatchlistFilm(
            title="The Menu",
            original_title="The Menu",
            year=2022,
            notes="Do not leak this into suggestion context.",
        )
    ]
    try:
        batch = ai_client.suggest(watched, watchlist, prompt="quiet science fiction", count=5)
    finally:
        http_client.close()

    assert batch.recommendations[0].title == "Moon"
    assert captured["path"] == "/v1/chat/completions"
    request_body = cast(dict[str, object], captured["body"])
    assert request_body["model"] == "test-model"
    assert request_body["max_tokens"] == 48000
    assert "reasoning" not in request_body
    serialized_body = json.dumps(request_body)
    assert "A complete review." in serialized_body
    assert "super-secret" not in serialized_body
    assert "exclusions" in serialized_body
    messages = cast(list[dict[str, str]], request_body["messages"])
    profile = cast(dict[str, object], json.loads(messages[1]["content"]))
    assert "watchlist" not in profile
    forbidden_titles = cast(list[object], profile["forbiddenTitles"])
    assert "The Menu (2022)" in forbidden_titles
    assert "Do not leak this into suggestion context." not in messages[1]["content"]
    response_format = cast(dict[str, object], request_body["response_format"])
    assert response_format["type"] == "json_schema"
    json_schema = cast(dict[str, object], response_format["json_schema"])
    schema = cast(dict[str, object], json_schema["schema"])
    assert set(cast(list[str], schema["required"])) >= {
        "recommendations",
    }
    properties = cast(dict[str, object], schema["properties"])
    recommendations_schema = cast(dict[str, object], properties["recommendations"])
    assert recommendations_schema["minItems"] == 5
    assert "Do not use Markdown" in messages[0]["content"]
    assert "forbiddenTitles array is a hard blocklist" in messages[0]["content"]
    assert "Do not say it was suggested by the model" in messages[0]["content"]


def test_ai_client_validates_max_tokens_range() -> None:
    with pytest.raises(ValueError, match="between 128 and 128000"):
        OpenAICompatibleClient(
            "super-secret",
            "test-model",
            "https://provider.test/v1",
            max_tokens=256000,
        )


def test_ai_client_disables_openrouter_reasoning_for_json_requests() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
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

    http_client = httpx.Client(
        base_url="https://provider.test/v1/",
        transport=httpx.MockTransport(handler),
    )
    ai_client = OpenAICompatibleClient(
        "super-secret",
        "test-model",
        "https://openrouter.ai/api/v1",
        http_client=http_client,
    )
    try:
        ai_client.suggest([], [], count=1)
    finally:
        http_client.close()

    request_body = cast(dict[str, object], captured["body"])
    assert request_body["reasoning"] == {"effort": "none", "exclude": True}


def test_ai_client_requests_scores_for_non_manual_watchlist_and_taste_matches() -> None:
    captured_profile: dict[str, object] = {}
    generated_at = datetime(2026, 7, 20, tzinfo=UTC)
    watchlist = [
        WatchlistFilm(
            tmdb_id=10,
            title="Score Me",
            year=2020,
            interest=8,
            interest_source="local",
        ),
        WatchlistFilm(
            tmdb_id=11,
            title="Manual",
            year=2021,
            interest=6,
            interest_source="manual",
        ),
    ]
    discovery = Recommendation(
        tmdb_id=12,
        title="Taste Match",
        year=2022,
        predicted_rating=8,
        rationale="Local rationale.",
        source="deterministic",
        generated_at=generated_at,
    )
    watchlist_target = score_target_id("watchlist", watchlist[0])
    discovery_target = score_target_id("discovery", discovery)

    def handler(request: httpx.Request) -> httpx.Response:
        body: object = json.loads(request.content)
        assert isinstance(body, dict)
        messages = cast(list[dict[str, str]], body["messages"])
        profile: object = json.loads(messages[1]["content"])
        assert isinstance(profile, dict)
        captured_profile.update(cast(dict[str, object], profile))
        result = {
            "watchlistScores": [{"target": watchlist_target, "predictedRating": 8.4}],
            "discoveryScores": [{"target": discovery_target, "predictedRating": 8.7}],
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(result)}}]},
        )

    ai_client, http_client = _provider_client(httpx.MockTransport(handler))
    try:
        batch = ai_client.score_targets(
            [WatchedFilm(title="Arrival", rating=9)],
            watchlist,
            deterministic_discoveries=[discovery],
        )
    finally:
        http_client.close()

    assert [
        cast(dict[str, object], target)["target"]
        for target in cast(list[object], captured_profile["watchlistScoreTargets"])
    ] == [watchlist_target]
    assert "watchlist" in captured_profile
    assert batch.watchlist_scores[0].predicted_rating == 8.4
    assert batch.discovery_scores[0].predicted_rating == 8.7


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


def test_ai_client_extracts_text_from_message_content_parts() -> None:
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
            json={
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"type": "text", "text": json.dumps(result)},
                            ]
                        }
                    }
                ]
            },
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


def test_ai_client_normalizes_extra_fields_and_long_rationales() -> None:
    long_rationale = "Hidden Figures explores resilience and institutional barriers. " * 20
    result = {
        "providerNote": "ignored",
        "recommendations": [
            {
                "title": "Hidden Figures",
                "year": 2016,
                "rating": 8.0,
                "genres": ["Drama", "Biography"],
                "tags": ["films resumes", "lifestyle"],
                "review": "The true story of three mathematicians and their success.",
                "rationale": long_rationale,
            }
        ],
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

    suggestion = batch.recommendations[0]
    assert suggestion.title == "Hidden Figures"
    assert suggestion.predicted_rating == 8
    assert len(suggestion.rationale) == 500


def test_ai_client_normalizes_score_response_aliases() -> None:
    result = {
        "providerNote": "ignored",
        "watchlist_scores": [
            {
                "id": "watchlist:10",
                "rating": 8.2,
                "title": "Provider echo ignored",
            }
        ],
        "discovery_scores": [{"target": "discovery:20", "score": 7.9}],
    }
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(result)}}]},
        )
    )
    ai_client, http_client = _provider_client(transport)
    try:
        batch = ai_client.score_targets([], [])
    finally:
        http_client.close()

    assert batch.watchlist_scores[0].target == "watchlist:10"
    assert batch.watchlist_scores[0].predicted_rating == 8.2
    assert batch.discovery_scores[0].target == "discovery:20"
    assert batch.discovery_scores[0].predicted_rating == 7.9


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


def test_ai_client_reports_provider_shape_when_message_has_no_text() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "refusal": "The model refused to answer.",
                            "tool_calls": [],
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 0,
                    "total_tokens": 20,
                },
            },
        )
    )
    ai_client, http_client = _provider_client(transport)
    try:
        with pytest.raises(AIError) as raised:
            ai_client.suggest([], [], count=1)
    finally:
        http_client.close()

    message = str(raised.value)
    assert "AI provider message has no textual content" in message
    assert "finish_reason='stop'" in message
    assert "content_type=NoneType" in message
    assert "refusal='The model refused to answer.'" in message
    assert "usage[prompt_tokens=20, completion_tokens=0, total_tokens=20]" in message
    assert "super-secret" not in message


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


def test_resolver_replaces_generic_ai_rationale_with_catalog_description(tmp_path: Path) -> None:
    batch = AISuggestionBatch.model_validate(
        {
            "recommendations": [
                {
                    "title": "Moon",
                    "year": 2009,
                    "predictedRating": 8.5,
                    "rationale": "Suggested by the configured AI model.",
                }
            ]
        }
    )

    http_client = httpx.Client(
        base_url="https://catalog.test/3/",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
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
        ),
    )
    catalog = TMDBClient("token", tmp_path / "cache", http_client=http_client)
    try:
        result = resolve_ai_suggestions(
            batch,
            catalog,
            [],
            [],
            generated_at=datetime(2026, 7, 20, tzinfo=UTC),
            provider="openai-compatible",
            model="test-model",
        )
    finally:
        http_client.close()

    assert result.recommendations[0].rationale == ("A lunar worker nears the end of his contract.")
