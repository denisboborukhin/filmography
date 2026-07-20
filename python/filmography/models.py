"""Strict public data models shared by the updater and static application."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

Score = Annotated[float, Field(ge=0, le=10, multiple_of=0.5)]


class PublicModel(BaseModel):
    """Base model with a stable camelCase, no-extra-fields JSON contract."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
    )


class FilmMetadata(PublicModel):
    """Catalog metadata embedded into all public film records."""

    tmdb_id: int | None = Field(default=None, ge=1)
    title: str = Field(min_length=1)
    original_title: str | None = None
    year: int | None = Field(default=None, ge=1878, le=2200)
    release_date: date | None = None
    poster_url: str | None = None
    overview: str = ""
    genres: list[str] = Field(default_factory=list)
    vote_average: float | None = Field(default=None, ge=0, le=10)
    popularity: float | None = Field(default=None, ge=0)

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
    """A watched film imported from one Obsidian review note."""

    rating: Score
    watched_at: date | None = None
    tags: list[str] = Field(default_factory=list)
    review: str = ""
    source_url: str | None = None

    @field_validator("tags", mode="after")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        return _unique_nonempty(values)

    @field_validator("source_url", mode="after")
    @classmethod
    def empty_source_is_none(cls, value: str | None) -> str | None:
        return value or None


class WatchlistFilm(FilmMetadata):
    """A future film imported from the single watchlist note."""

    interest: Score | None = None
    notes: str = ""
    tags: list[str] = Field(default_factory=list)
    dismissed: bool = False

    @field_validator("tags", mode="after")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        return _unique_nonempty(values)


class Recommendation(FilmMetadata):
    """A TMDB-verified deterministic or AI recommendation."""

    tmdb_id: int = Field(ge=1)  # pyright: ignore[reportIncompatibleVariableOverride, reportGeneralTypeIssues]
    predicted_rating: Score
    rationale: str = Field(min_length=1)
    source: Literal["deterministic", "ai"]
    generated_at: datetime
    provider: str | None = None
    model: str | None = None

    @model_validator(mode="after")
    def provider_is_consistent_with_source(self) -> Self:
        if self.source == "deterministic":
            object.__setattr__(self, "provider", None)
            object.__setattr__(self, "model", None)
        elif not self.provider or not self.model:
            raise ValueError("AI recommendations require provider and model")
        return self


class Snapshot(PublicModel):
    """Versioned, entirely public state consumed by the static frontend."""

    schema_version: Literal[1] = 1
    generated_at: datetime
    recommendations_generated_at: datetime | None = None
    watched: list[WatchedFilm] = []
    watchlist: list[WatchlistFilm] = []
    deterministic_discoveries: list[Recommendation] = []
    ai_discoveries: list[Recommendation] = []

    @model_validator(mode="after")
    def validate_collections(self) -> Self:
        _ensure_unique_films(self.watched, "watched")
        _ensure_unique_films(self.watchlist, "watchlist")
        _ensure_unique_recommendations(
            [*self.deterministic_discoveries, *self.ai_discoveries]
        )
        excluded_ids = {
            film.tmdb_id
            for film in [*self.watched, *self.watchlist]
            if film.tmdb_id is not None
        }
        excluded_titles = {
            film_identity(film.title, film.year)
            for film in [*self.watched, *self.watchlist]
        }
        for recommendation in [*self.deterministic_discoveries, *self.ai_discoveries]:
            if recommendation.tmdb_id in excluded_ids or film_identity(
                recommendation.title, recommendation.year
            ) in excluded_titles:
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
    seen: set[tuple[str, int | None] | tuple[str, int]] = set()
    for film in films:
        key: tuple[str, int | None] | tuple[str, int]
        key = ("tmdb", film.tmdb_id) if film.tmdb_id is not None else film_identity(
            film.title, film.year
        )
        if key in seen:
            raise ValueError(f"duplicate film in {collection}: {film.title}")
        seen.add(key)


def _ensure_unique_recommendations(recommendations: list[Recommendation]) -> None:
    seen: set[int] = set()
    for recommendation in recommendations:
        if recommendation.tmdb_id in seen:
            raise ValueError(f"duplicate recommendation: {recommendation.title}")
        seen.add(recommendation.tmdb_id)
