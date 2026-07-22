from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from filmography.models import Recommendation, Snapshot, WatchedFilm, WatchlistFilm
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError


def test_public_models_reject_unknown_fields_and_invalid_score_steps() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        WatchedFilm.model_validate({"title": "Arrival", "rating": 9, "localNotesPath": "/secret"})
    with pytest.raises(ValidationError, match="multiple_of"):
        WatchedFilm(title="Arrival", rating=9.25)
    assert WatchedFilm(title="Arrival", rating=9.2).rating == 9.2


def test_release_date_supplies_year_without_assignment_recursion() -> None:
    film = WatchedFilm(title="Arrival", rating=9, release_date=date(2016, 11, 11))

    assert film.year == 2016


def test_media_type_defaults_to_movie_and_separates_catalog_namespaces() -> None:
    movie = WatchedFilm(tmdb_id=1, title="Shared ID", rating=8)
    series = WatchlistFilm(tmdb_id=1, media_type="tv", title="Shared ID")

    assert movie.media_type == "movie"
    Snapshot(generated_at=datetime(2026, 7, 20, tzinfo=UTC), watched=[movie], watchlist=[series])


@pytest.mark.parametrize(
    "source_url",
    ["/Users/person/private-review.md", "file:///private/review.md", "https://token@example.test"],
)
def test_review_source_rejects_local_paths_and_embedded_credentials(source_url: str) -> None:
    with pytest.raises(ValidationError, match="public HTTP\\(S\\) URL"):
        WatchedFilm(title="Arrival", rating=9, source_url=source_url)


def test_recommendation_source_metadata_is_consistent() -> None:
    generated_at = datetime(2026, 7, 20, tzinfo=UTC)
    with pytest.raises(ValidationError, match="cannot include provider or model"):
        Recommendation(
            tmdb_id=1,
            title="Film",
            predicted_rating=8,
            rationale="Because",
            source="deterministic",
            generated_at=generated_at,
            provider="must not be published",
            model="must not be published",
        )
    with pytest.raises(ValidationError, match="require provider and model"):
        Recommendation(
            tmdb_id=2,
            title="AI Film",
            predicted_rating=8,
            rationale="Because",
            source="ai",
            generated_at=generated_at,
        )
    with pytest.raises(ValidationError, match="recommendations must be movies"):
        Recommendation(
            tmdb_id=3,
            media_type="tv",
            title="Series",
            predicted_rating=8,
            rationale="Because",
            source="deterministic",
            generated_at=generated_at,
        )


def test_public_numeric_fields_do_not_coerce_strings() -> None:
    with pytest.raises(ValidationError, match="valid integer"):
        WatchedFilm.model_validate({"title": "Arrival", "year": "2016", "rating": 9})
    with pytest.raises(ValidationError, match="valid number"):
        WatchedFilm.model_validate({"title": "Arrival", "year": 2016, "rating": "9"})


def test_public_timestamps_require_timezone_offsets() -> None:
    naive = datetime(2026, 7, 20, 12, 0)
    with pytest.raises(ValidationError, match="timezone offset"):
        Snapshot(generated_at=naive)
    with pytest.raises(ValidationError, match="timezone offset"):
        Recommendation(
            tmdb_id=1,
            title="Film",
            predicted_rating=8,
            rationale="Because",
            source="deterministic",
            generated_at=naive,
        )


def test_snapshot_rejects_duplicates_and_existing_recommendations() -> None:
    generated_at = datetime(2026, 7, 20, tzinfo=UTC)
    watched = WatchedFilm(tmdb_id=1, title="Seen", year=2020, rating=8)
    with pytest.raises(ValidationError, match="duplicate film"):
        Snapshot(generated_at=generated_at, watched=[watched, watched.model_copy()])
    with pytest.raises(ValidationError, match="already watched"):
        Snapshot(
            generated_at=generated_at,
            watched=[watched],
            ai_discoveries=[
                Recommendation(
                    tmdb_id=1,
                    title="Seen",
                    year=2020,
                    predicted_rating=8,
                    rationale="Duplicate",
                    source="ai",
                    generated_at=generated_at,
                    provider="openai-compatible",
                    model="test",
                )
            ],
        )


def test_snapshot_uses_title_identity_when_year_or_catalog_id_is_missing() -> None:
    generated_at = datetime(2026, 7, 20, tzinfo=UTC)
    recommendation = Recommendation(
        tmdb_id=884,
        title="Crash",
        year=1996,
        predicted_rating=8,
        rationale="Duplicate with a catalog year",
        source="deterministic",
        generated_at=generated_at,
    )

    with pytest.raises(ValidationError, match="already watched"):
        Snapshot(
            generated_at=generated_at,
            watched=[WatchedFilm(title="Crash", rating=8)],
            deterministic_discoveries=[recommendation],
        )

    with pytest.raises(ValidationError, match="duplicate film"):
        Snapshot(
            generated_at=generated_at,
            watched=[
                WatchedFilm(tmdb_id=884, title="Crash", year=1996, rating=8),
                WatchedFilm(title="Crash", year=1996, rating=7),
            ],
        )

    with pytest.raises(ValidationError, match="watched and watchlist"):
        Snapshot(
            generated_at=generated_at,
            watched=[WatchedFilm(title="Crash", year=1996, rating=8)],
            watchlist=[WatchlistFilm(tmdb_id=884, title="Crash")],
        )


def test_snapshot_rejects_recommendation_in_the_wrong_collection() -> None:
    generated_at = datetime(2026, 7, 20, tzinfo=UTC)
    ai_recommendation = Recommendation(
        tmdb_id=1,
        title="Film",
        predicted_rating=8,
        rationale="Because",
        source="ai",
        generated_at=generated_at,
        provider="openai-compatible",
        model="test",
    )

    with pytest.raises(ValidationError, match="deterministic discoveries"):
        Snapshot(
            generated_at=generated_at,
            deterministic_discoveries=[ai_recommendation],
        )


def test_snapshot_serializes_stable_camel_case_contract() -> None:
    snapshot = Snapshot(
        generated_at=datetime(2026, 7, 20, tzinfo=UTC),
        watched=[WatchedFilm(title="Film", rating=7.5)],
        watchlist=[WatchlistFilm(title="Later")],
    )

    payload = snapshot.model_dump(mode="json", by_alias=True)

    assert set(payload) == {
        "schemaVersion",
        "generatedAt",
        "recommendationsGeneratedAt",
        "watched",
        "watchlist",
        "deterministicDiscoveries",
        "aiDiscoveries",
    }
    assert payload["watched"][0]["tmdbId"] is None  # type: ignore[index]


def test_static_schema_describes_the_runtime_contract() -> None:
    schema_path = Path(__file__).parents[2] / "schemas" / "snapshot.schema.json"
    schema_value: object = json.loads(schema_path.read_text(encoding="utf-8"))
    assert isinstance(schema_value, dict)
    schema = cast(dict[str, object], schema_value)

    assert schema["additionalProperties"] is False
    required = schema["required"]
    assert isinstance(required, list)
    assert set(cast(list[str], required)) == {
        "schemaVersion",
        "generatedAt",
        "recommendationsGeneratedAt",
        "watched",
        "watchlist",
        "deterministicDiscoveries",
        "aiDiscoveries",
    }

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    invalid = Snapshot(
        generated_at=datetime(2026, 7, 20, tzinfo=UTC),
        watched=[WatchedFilm(title="Film", rating=9.2)],
    ).model_dump(mode="json", by_alias=True)
    invalid["watched"][0]["rating"] = 9.25  # type: ignore[index]
    assert any(validator.iter_errors(invalid))  # pyright: ignore[reportUnknownMemberType]


def test_demo_snapshot_satisfies_python_and_static_json_schemas() -> None:
    root = Path(__file__).parents[2]
    snapshot_value: object = json.loads(
        (root / "public" / "data" / "filmography.json").read_text(encoding="utf-8")
    )
    schema_value: object = json.loads(
        (root / "schemas" / "snapshot.schema.json").read_text(encoding="utf-8"),
        parse_float=Decimal,
    )
    assert isinstance(schema_value, dict)

    Snapshot.model_validate(snapshot_value)
    validator = Draft202012Validator(
        cast(dict[str, object], schema_value),
        format_checker=FormatChecker(),
    )
    decimal_snapshot = json.loads(json.dumps(snapshot_value), parse_float=Decimal)
    validator.validate(decimal_snapshot)  # pyright: ignore[reportUnknownMemberType]
