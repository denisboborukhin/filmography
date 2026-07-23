"""Strict public data models shared by the updater and static application."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

Score = Annotated[float, Field(strict=True, ge=0, le=10, multiple_of=0.1)]
PositiveId = Annotated[int, Field(strict=True, ge=1)]
FilmYear = Annotated[int, Field(strict=True, ge=1878, le=2200)]
CatalogScore = Annotated[float, Field(strict=True, ge=0, le=10)]
Popularity = Annotated[float, Field(strict=True, ge=0)]
MediaType = Literal["movie", "tv"]
ScoreSource = Literal["manual", "local", "ai"]


class PublicModel(BaseModel):
    """Base model with a stable camelCase, no-extra-fields JSON contract."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
    )


class PersonCredit(PublicModel):
    """A public TMDB person reference attached to a watched title."""

    tmdb_id: PositiveId
    name: str = Field(min_length=1)
    profile_url: str | None = None
    role: str | None = None

    @field_validator("profile_url", "role", mode="after")
    @classmethod
    def empty_optional_string_is_none(cls, value: str | None) -> str | None:
        return value or None


class FilmCredits(PublicModel):
    """People used to derive the public personal taste profile."""

    cast: list[PersonCredit] = Field(default_factory=lambda: list[PersonCredit]())
    filmmaker: PersonCredit | None = None

    @field_validator("cast", mode="after")
    @classmethod
    def unique_cast(cls, values: list[PersonCredit]) -> list[PersonCredit]:
        result: list[PersonCredit] = []
        seen: set[int] = set()
        for person in values:
            if person.tmdb_id not in seen:
                seen.add(person.tmdb_id)
                result.append(person)
        return result


class FilmMetadata(PublicModel):
    """Catalog metadata embedded into all public film records."""

    tmdb_id: PositiveId | None = None
    media_type: MediaType = "movie"
    title: str = Field(min_length=1)
    original_title: str | None = None
    year: FilmYear | None = None
    release_date: date | None = None
    poster_url: str | None = None
    overview: str = ""
    genres: list[str] = Field(default_factory=list)
    vote_average: CatalogScore | None = None
    popularity: Popularity | None = None

    @field_validator("original_title", "poster_url", mode="after")
    @classmethod
    def empty_optional_string_is_none(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("genres", mode="after")
    @classmethod
    def normalize_genres(cls, values: list[str]) -> list[str]:
        return _unique_nonempty(values)

    @model_validator(mode="after")
    def year_matches_release_date(self) -> Self:
        if self.release_date is not None and self.year is None:
            object.__setattr__(self, "year", self.release_date.year)
        return self


class WatchedFilm(FilmMetadata):
    """A watched film imported from one Markdown review note."""

    rating: Score
    watched_at: date | None = None
    tags: list[str] = Field(default_factory=list)
    review: str = ""
    source_url: str | None = None
    credits: FilmCredits = Field(default_factory=FilmCredits)

    @field_validator("tags", mode="after")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        return _unique_nonempty(values)

    @field_validator("source_url", mode="after")
    @classmethod
    def validate_public_source_url(cls, value: str | None) -> str | None:
        if not value:
            return None
        try:
            parsed = urlsplit(value)
            hostname = parsed.hostname
        except ValueError as error:
            raise ValueError("source URL must be an absolute public HTTP(S) URL") from error
        if (
            parsed.scheme.casefold() not in {"http", "https"}
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError(
                "source URL must be an absolute public HTTP(S) URL without credentials"
            )
        return value


class WatchlistFilm(FilmMetadata):
    """A future film imported from the single watchlist note."""

    interest: Score | None = None
    interest_source: ScoreSource | None = None
    notes: str = ""
    tags: list[str] = Field(default_factory=list)
    dismissed: bool = False

    @field_validator("tags", mode="after")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        return _unique_nonempty(values)

    @model_validator(mode="after")
    def interest_source_requires_score(self) -> Self:
        if self.interest is None and self.interest_source is not None:
            raise ValueError("watchlist score source requires an expected score")
        return self


class Recommendation(FilmMetadata):
    """A TMDB-verified deterministic or AI recommendation."""

    tmdb_id: PositiveId  # pyright: ignore[reportIncompatibleVariableOverride, reportGeneralTypeIssues]
    predicted_rating: Score
    score_source: Literal["local", "ai"] | None = None
    rationale: str = Field(min_length=1)
    source: Literal["deterministic", "ai"]
    generated_at: datetime
    provider: str | None = None
    model: str | None = None

    @field_validator("generated_at", mode="after")
    @classmethod
    def generated_at_has_timezone(cls, value: datetime) -> datetime:
        return _timezone_aware(value)

    @model_validator(mode="after")
    def provider_is_consistent_with_source(self) -> Self:
        if self.media_type != "movie":
            raise ValueError("recommendations must be movies")
        if self.source == "deterministic":
            if self.provider is not None or self.model is not None:
                raise ValueError("deterministic recommendations cannot include provider or model")
        elif not self.provider or not self.model:
            raise ValueError("AI recommendations require provider and model")
        expected_score_source = "ai" if self.source == "ai" else "local"
        if self.score_source is None:
            object.__setattr__(self, "score_source", expected_score_source)
        elif self.source == "ai" and self.score_source != "ai":
            raise ValueError("AI recommendations require an AI expected score")
        return self


class Snapshot(PublicModel):
    """Versioned, entirely public state consumed by the static frontend."""

    schema_version: Literal[1] = 1
    generated_at: datetime
    recommendations_generated_at: datetime | None = None
    watched: list[WatchedFilm] = Field(default_factory=lambda: list[WatchedFilm]())
    watchlist: list[WatchlistFilm] = Field(default_factory=lambda: list[WatchlistFilm]())
    deterministic_discoveries: list[Recommendation] = Field(
        default_factory=lambda: list[Recommendation]()
    )
    ai_discoveries: list[Recommendation] = Field(default_factory=lambda: list[Recommendation]())

    @field_validator("generated_at", "recommendations_generated_at", mode="after")
    @classmethod
    def generated_dates_have_timezone(cls, value: datetime | None) -> datetime | None:
        return _timezone_aware(value) if value is not None else None

    @model_validator(mode="after")
    def validate_collections(self) -> Self:
        _ensure_unique_films(self.watched, "watched")
        _ensure_unique_films(self.watchlist, "watchlist")
        for film in self.watchlist:
            if film_matches_any(film, self.watched):
                raise ValueError(f"film appears in watched and watchlist: {film.title}")
        _ensure_unique_recommendations([*self.deterministic_discoveries, *self.ai_discoveries])
        for recommendation in self.deterministic_discoveries:
            if recommendation.source != "deterministic":
                raise ValueError("deterministic discoveries must use deterministic source")
        for recommendation in self.ai_discoveries:
            if recommendation.source != "ai":
                raise ValueError("AI discoveries must use AI source")
        excluded = [*self.watched, *self.watchlist]
        for recommendation in [*self.deterministic_discoveries, *self.ai_discoveries]:
            if film_matches_any(recommendation, excluded):
                raise ValueError(
                    f"recommendation is already watched or watchlisted: {recommendation.title}"
                )
        return self


def film_identity(title: str, year: int | None) -> tuple[str, int | None]:
    """Return a predictable identity key for records without a catalog ID."""

    normalized = " ".join(
        "".join(char.casefold() if char.isalnum() else " " for char in title).split()
    )
    return normalized, year


def film_titles_overlap(
    left_title: str,
    left_year: int | None,
    right_title: str,
    right_year: int | None,
) -> bool:
    """Match normalized titles, treating a missing year as an unknown wildcard."""

    left_key = film_identity(left_title, left_year)
    right_key = film_identity(right_title, right_year)
    return left_key[0] == right_key[0] and (
        left_year is None or right_year is None or left_year == right_year
    )


def films_match(left: FilmMetadata, right: FilmMetadata) -> bool:
    """Match catalog IDs when available and always check the human title identity."""

    if left.media_type != right.media_type:
        return False
    return (
        left.tmdb_id is not None and right.tmdb_id is not None and left.tmdb_id == right.tmdb_id
    ) or film_titles_overlap(left.title, left.year, right.title, right.year)


def film_matches_any(film: FilmMetadata, existing: Sequence[FilmMetadata]) -> bool:
    """Return whether a film overlaps any watched, watchlisted, or recommended record."""

    return any(films_match(film, item) for item in existing)


def unique_unmatched_films[FilmRecord: FilmMetadata](
    films: Sequence[FilmRecord], excluded: Sequence[FilmMetadata] = ()
) -> list[FilmRecord]:
    """Keep the first film for each canonical identity, excluding existing records."""

    accepted: list[FilmRecord] = []
    comparisons = list(excluded)
    for film in films:
        if film_matches_any(film, comparisons):
            continue
        accepted.append(film)
        comparisons.append(film)
    return accepted


def _unique_nonempty(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = raw_value.strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _ensure_unique_films(films: Sequence[FilmMetadata], collection: str) -> None:
    seen: list[FilmMetadata] = []
    for film in films:
        if film_matches_any(film, seen):
            raise ValueError(f"duplicate film in {collection}: {film.title}")
        seen.append(film)


def _ensure_unique_recommendations(recommendations: list[Recommendation]) -> None:
    seen: list[Recommendation] = []
    for recommendation in recommendations:
        if film_matches_any(recommendation, seen):
            raise ValueError(f"duplicate recommendation: {recommendation.title}")
        seen.append(recommendation)


def _timezone_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone offset")
    return value
