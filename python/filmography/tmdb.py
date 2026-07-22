"""Small cached TMDB catalog adapter with conservative title matching."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal, cast

import httpx
from pydantic import ValidationError

from filmography.models import FilmMetadata, MediaType, film_identity

_DEFAULT_BASE_URL = "https://api.themoviedb.org/3"
_POSTER_BASE_URL = "https://image.tmdb.org/t/p/w780"


class CatalogError(RuntimeError):
    """Raised when TMDB cannot provide a valid response."""


@dataclass(frozen=True, slots=True)
class CatalogMatch:
    """A title lookup that requires an unambiguous exact title/year match."""

    status: Literal["matched", "unresolved", "ambiguous"]
    film: FilmMetadata | None
    candidates: tuple[FilmMetadata, ...] = ()


class TMDBClient:
    """Synchronous TMDB client whose successful GET responses are cached on disk."""

    def __init__(
        self,
        access_token: str,
        cache_dir: Path,
        *,
        http_client: httpx.Client | None = None,
        base_url: str = _DEFAULT_BASE_URL,
        language: str = "en-US",
    ) -> None:
        if not access_token.strip():
            raise ValueError("TMDB access token cannot be empty")
        self._cache_dir = cache_dir
        self._language = language
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            timeout=20.0,
        )
        self._genres_by_media: dict[MediaType, dict[int, str]] = {}

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> TMDBClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def get_movie(self, tmdb_id: int) -> FilmMetadata:
        """Fetch a film by canonical ID."""
        return self._get_media(tmdb_id, "movie")

    def get_tv(self, tmdb_id: int) -> FilmMetadata:
        """Fetch a TV series by canonical ID."""
        return self._get_media(tmdb_id, "tv")

    def match_movie(
        self,
        title: str,
        year: int | None = None,
        *,
        allow_popular_without_year: bool = False,
    ) -> CatalogMatch:
        """Match a title conservatively, with explicit fallbacks for localized catalog results."""
        return self._match(title, year, "movie", allow_popular_without_year)

    def match_tv(
        self,
        title: str,
        year: int | None = None,
        *,
        allow_popular_without_year: bool = False,
    ) -> CatalogMatch:
        """Match a TV series conservatively, using the same rules as movie matching."""
        return self._match(title, year, "tv", allow_popular_without_year)

    def _match(
        self,
        title: str,
        year: int | None,
        media_type: MediaType,
        allow_popular_without_year: bool,
    ) -> CatalogMatch:
        params: dict[str, str | int] = {"query": title, "include_adult": "false", "page": 1}
        if year is not None:
            params["year" if media_type == "movie" else "first_air_date_year"] = year
        payload = self._get_json(
            f"/search/{media_type}",
            params,
            validator=lambda value: self._validate_search_payload(value, media_type),
        )
        raw_results = _list_of_mappings(payload.get("results"), "TMDB search results")
        candidates = tuple(self._media_from_payload(item, media_type) for item in raw_results[:20])
        return self._select_match(title, year, candidates, allow_popular_without_year)

    def _get_media(self, tmdb_id: int, media_type: MediaType) -> FilmMetadata:
        if tmdb_id < 1:
            raise ValueError("TMDB ID must be positive")
        payload = self._get_json(
            f"/{media_type}/{tmdb_id}",
            {},
            validator=lambda value: self._media_from_payload(value, media_type),
        )
        return self._media_from_payload(payload, media_type)

    @staticmethod
    def _select_match(
        title: str,
        year: int | None,
        candidates: tuple[FilmMetadata, ...],
        allow_popular_without_year: bool,
    ) -> CatalogMatch:
        requested_title = film_identity(title, None)[0]
        exact_title = tuple(
            film
            for film in candidates
            if requested_title
            in {
                film_identity(film.title, None)[0],
                film_identity(film.original_title or "", None)[0],
            }
        )
        exact = (
            tuple(film for film in exact_title if film.year == year)
            if year is not None
            else exact_title
        )
        if len(exact) == 1:
            return CatalogMatch("matched", exact[0], exact)
        if len(exact) > 1:
            popular = _unique_popularity_winner(exact)
            if popular is not None:
                return CatalogMatch("matched", popular, exact)
            return CatalogMatch("ambiguous", None, exact)
        if year is not None and _contains_non_ascii(title):
            same_year = tuple(film for film in candidates if film.year == year)
            if len(same_year) == 1:
                return CatalogMatch("matched", same_year[0], same_year)
            if len(same_year) > 1:
                popular = _unique_popularity_winner(same_year)
                if popular is not None:
                    return CatalogMatch("matched", popular, same_year)
                return CatalogMatch("ambiguous", None, same_year)
        if year is None and allow_popular_without_year and candidates:
            popular = _unique_popularity_winner(candidates)
            if popular is not None:
                return CatalogMatch("matched", popular, candidates)
        return CatalogMatch("unresolved", None, candidates[:5])

    def find_tv_titles(self, title: str, *, limit: int = 3) -> tuple[str, ...]:
        """Return likely TMDB TV matches for diagnostics; does not enrich film records."""

        if limit < 1:
            return ()
        match = self.match_tv(title, allow_popular_without_year=True)
        return tuple(
            f"{series.title} ({series.year or 'unknown'})" for series in match.candidates[:limit]
        )

    def discover_movies(
        self,
        preferred_genres: list[str],
        *,
        pages: int = 2,
    ) -> list[FilmMetadata]:
        """Fetch a stable candidate pool, optionally narrowed to preferred genres."""

        if pages < 1 or pages > 5:
            raise ValueError("pages must be between 1 and 5")
        genres_by_id = self._genre_names("movie")
        ids_by_name = {name.casefold(): genre_id for genre_id, name in genres_by_id.items()}
        genre_ids = sorted(
            {
                ids_by_name[name.casefold()]
                for name in preferred_genres
                if name.casefold() in ids_by_name
            }
        )
        films: list[FilmMetadata] = []
        seen: set[int] = set()
        for page in range(1, pages + 1):
            params: dict[str, str | int] = {
                "include_adult": "false",
                "include_video": "false",
                "language": self._language,
                "page": page,
                "sort_by": "vote_average.desc",
                "vote_count.gte": 250,
            }
            if genre_ids:
                params["with_genres"] = "|".join(str(item) for item in genre_ids[:4])
            payload = self._get_json(
                "/discover/movie",
                params,
                validator=lambda value: self._validate_discovery_payload(value, genres_by_id),
            )
            for item in _list_of_mappings(payload.get("results"), "TMDB discovery results"):
                film = self._media_from_payload(item, "movie", genres_by_id=genres_by_id)
                if film.tmdb_id is not None and film.tmdb_id not in seen:
                    seen.add(film.tmdb_id)
                    films.append(film)
        return films

    def _genre_names(self, media_type: MediaType) -> dict[int, str]:
        cached = self._genres_by_media.get(media_type)
        if cached is not None:
            return cached
        payload = self._get_json(
            f"/genre/{media_type}/list",
            {},
            validator=self._validate_genre_payload,
        )
        genres: dict[int, str] = {}
        for item in _list_of_mappings(payload.get("genres"), "TMDB genres"):
            genre_id = _required_int(item, "id")
            name = _required_string(item, "name")
            genres[genre_id] = name
        self._genres_by_media[media_type] = genres
        return genres

    def _media_from_payload(
        self,
        payload: Mapping[str, object],
        media_type: MediaType,
        *,
        genres_by_id: dict[int, str] | None = None,
    ) -> FilmMetadata:
        is_movie = media_type == "movie"
        title_key = "title" if is_movie else "name"
        original_title_key = "original_title" if is_movie else "original_name"
        release_date_key = "release_date" if is_movie else "first_air_date"
        release_date = _parse_release_date(payload.get(release_date_key))
        genre_names: list[str] = []
        raw_genres = payload.get("genres")
        if isinstance(raw_genres, list):
            for raw_genre in cast(list[object], raw_genres):
                if isinstance(raw_genre, Mapping):
                    genre = cast(Mapping[object, object], raw_genre)
                    name = genre.get("name")
                    if isinstance(name, str):
                        genre_names.append(name)
        raw_genre_ids = payload.get("genre_ids")
        if isinstance(raw_genre_ids, list):
            names = genres_by_id if genres_by_id is not None else self._genre_names(media_type)
            for raw_id in cast(list[object], raw_genre_ids):
                if isinstance(raw_id, int) and raw_id in names:
                    genre_names.append(names[raw_id])
        poster_path = payload.get("poster_path")
        poster_url = (
            f"{_POSTER_BASE_URL}{poster_path}"
            if isinstance(poster_path, str) and poster_path.startswith("/")
            else None
        )
        try:
            return FilmMetadata(
                tmdb_id=_required_int(payload, "id"),
                media_type=media_type,
                title=_required_string(payload, title_key),
                original_title=_optional_string(payload.get(original_title_key)),
                year=release_date.year if release_date is not None else None,
                release_date=release_date,
                poster_url=poster_url,
                overview=_optional_string(payload.get("overview")) or "",
                genres=genre_names,
                vote_average=_optional_float(payload.get("vote_average")),
                popularity=_optional_float(payload.get("popularity")),
            )
        except ValidationError as error:
            message = error.errors()[0]["msg"]
            label = "movie" if is_movie else "TV"
            raise CatalogError(f"TMDB {label} metadata is invalid: {message}") from error

    def _validate_search_payload(
        self, payload: Mapping[str, object], media_type: MediaType
    ) -> None:
        for item in _list_of_mappings(payload.get("results"), "TMDB search results"):
            self._media_from_payload(item, media_type)

    def _validate_discovery_payload(
        self,
        payload: Mapping[str, object],
        genres_by_id: dict[int, str],
    ) -> None:
        for item in _list_of_mappings(payload.get("results"), "TMDB discovery results"):
            self._media_from_payload(item, "movie", genres_by_id=genres_by_id)

    @staticmethod
    def _validate_genre_payload(payload: Mapping[str, object]) -> None:
        for item in _list_of_mappings(payload.get("genres"), "TMDB genres"):
            _required_int(item, "id")
            _required_string(item, "name")

    def _get_json(
        self,
        path: str,
        params: Mapping[str, str | int],
        *,
        validator: Callable[[Mapping[str, object]], object] | None = None,
    ) -> Mapping[str, object]:
        request_params: dict[str, str | int] = {"language": self._language, **params}
        cache_key = hashlib.sha256(
            json.dumps(
                [path, sorted(request_params.items())],
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        cache_path = self._cache_dir / f"{cache_key}.json"
        if cache_path.is_file():
            try:
                cached = _load_mapping(
                    cache_path.read_text(encoding="utf-8"), "cached TMDB response"
                )
                if validator is not None:
                    validator(cached)
                return cached
            except (CatalogError, OSError):
                cache_path.unlink(missing_ok=True)

        try:
            response = self._client.get(path.lstrip("/"), params=request_params)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise CatalogError(f"TMDB request failed for {path}: {error}") from error
        payload = _load_mapping(response.text, "TMDB response")
        if validator is not None:
            validator(payload)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = cache_path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary_path.replace(cache_path)
        return payload


def _load_mapping(raw_json: str, label: str) -> Mapping[str, object]:
    try:
        value: object = json.loads(raw_json)
    except json.JSONDecodeError as error:
        raise CatalogError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise CatalogError(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def _list_of_mappings(value: object, label: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        raise CatalogError(f"{label} must be an array")
    result: list[Mapping[str, object]] = []
    for item in cast(list[object], value):
        if not isinstance(item, dict):
            raise CatalogError(f"{label} contains a non-object value")
        result.append(cast(dict[str, object], item))
    return result


def _required_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise CatalogError(f"TMDB field {key!r} must be an integer")
    return value


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CatalogError(f"TMDB field {key!r} must be a non-empty string")
    return value.strip()


def _optional_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _unique_popularity_winner(candidates: tuple[FilmMetadata, ...]) -> FilmMetadata | None:
    scored = [
        (candidate.popularity if candidate.popularity is not None else 0.0, candidate)
        for candidate in candidates
    ]
    if not scored:
        return None
    ranked = sorted(scored, key=lambda item: item[0], reverse=True)
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return None
    return ranked[0][1]


def _contains_non_ascii(value: str) -> bool:
    return any(ord(character) > 127 for character in value)


def _parse_release_date(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
