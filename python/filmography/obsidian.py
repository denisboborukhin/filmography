"""Import watched films and a watchlist from Obsidian Markdown notes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal, cast

import yaml
from pydantic import ValidationError

from filmography.models import WatchedFilm, WatchlistFilm, film_identity

_FRONTMATTER_DELIMITER = re.compile(r"^---\s*$")
_TITLE_YEAR = re.compile(r"^(?P<title>.+?)\s*\((?P<year>\d{4})\)\s*$")
_LIST_PREFIX = re.compile(r"^\s*(?:(?:[-*+]\s+)|(?:\d+[.)]\s+))")
_CHECKBOX = re.compile(r"^\[[ xX]\]\s+")
_SCORE = re.compile(r"^(?P<score>\d+(?:\.\d+)?)\s*(?:/\s*(?P<scale>5|10))?$")


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A human-readable problem tied to local source data."""

    severity: Literal["error", "warning"]
    code: str
    message: str
    path: Path | None = None
    line: int | None = None

    def __str__(self) -> str:
        location = str(self.path) if self.path is not None else "input"
        if self.line is not None:
            location = f"{location}:{self.line}"
        return f"{location}: {self.severity}: {self.message} [{self.code}]"


@dataclass(slots=True)
class ImportResult:
    """Imported records plus every diagnostic found in one validation pass."""

    watched: list[WatchedFilm] = field(default_factory=lambda: list[WatchedFilm]())
    watchlist: list[WatchlistFilm] = field(default_factory=lambda: list[WatchlistFilm]())
    diagnostics: list[Diagnostic] = field(default_factory=lambda: list[Diagnostic]())

    @property
    def has_errors(self) -> bool:
        return any(item.severity == "error" for item in self.diagnostics)


class ImportValidationError(ValueError):
    """Raised when a snapshot cannot be built from invalid source notes."""

    def __init__(self, diagnostics: list[Diagnostic]) -> None:
        self.diagnostics = diagnostics
        super().__init__("\n".join(str(item) for item in diagnostics))


def import_obsidian(reviews_dir: Path, watchlist_path: Path) -> ImportResult:
    """Parse all source notes and report errors without stopping at the first one."""

    result = ImportResult()
    if not reviews_dir.is_dir():
        result.diagnostics.append(
            Diagnostic("error", "reviews-not-found", "reviews folder does not exist", reviews_dir)
        )
    else:
        review_paths = sorted(
            (path for path in reviews_dir.rglob("*.md") if not path.name.startswith(".")),
            key=lambda path: path.as_posix().casefold(),
        )
        if not review_paths:
            result.diagnostics.append(
                Diagnostic(
                    "warning",
                    "reviews-empty",
                    "reviews folder contains no Markdown notes",
                    reviews_dir,
                )
            )
        for path in review_paths:
            try:
                result.watched.append(parse_review_note(path))
            except (ValueError, ValidationError) as error:
                result.diagnostics.append(
                    Diagnostic("error", "invalid-review", _error_message(error), path)
                )

    if not watchlist_path.is_file():
        result.diagnostics.append(
            Diagnostic(
                "error",
                "watchlist-not-found",
                "watchlist note does not exist",
                watchlist_path,
            )
        )
    else:
        watchlist, diagnostics = parse_watchlist_note(watchlist_path)
        result.watchlist.extend(watchlist)
        result.diagnostics.extend(diagnostics)

    result.diagnostics.extend(_duplicate_diagnostics(result.watched, result.watchlist))
    return result


def parse_review_note(path: Path) -> WatchedFilm:
    """Parse one review note, falling back to the filename for its title."""

    metadata, body, _ = _read_note(path)
    fallback_title, fallback_year = _split_title_year(path.stem)
    title_raw = _get(metadata, "title", "film", "movie")
    title, title_year = _split_title_year(str(title_raw)) if title_raw is not None else (
        fallback_title,
        fallback_year,
    )
    year = _optional_int(_get(metadata, "year"), "year")
    year = year if year is not None else title_year

    rating_raw = _get(metadata, "rating", "score")
    stars_field = False
    if rating_raw is None:
        rating_raw = _get(metadata, "stars")
        stars_field = rating_raw is not None
    if rating_raw is None:
        raise ValueError("missing required rating frontmatter field")
    explicit_scale = _optional_int(
        _get(metadata, "ratingScale", "rating_scale", "scale"), "rating scale"
    )
    rating = normalize_score(rating_raw, scale=5 if stars_field else explicit_scale)

    return WatchedFilm(
        tmdb_id=_optional_int(_get(metadata, "tmdbId", "tmdb_id", "tmdb"), "TMDB ID"),
        title=title,
        year=year,
        rating=rating,
        watched_at=_optional_date(
            _get(metadata, "watchedAt", "watched_at", "watched", "date"), "watched date"
        ),
        tags=_string_list(_get(metadata, "tags", "genres")),
        review=body.strip(),
        source_url=_optional_string(_get(metadata, "sourceUrl", "source_url", "source")),
    )


def parse_watchlist_note(path: Path) -> tuple[list[WatchlistFilm], list[Diagnostic]]:
    """Parse one-film-per-line watchlist content while collecting bad-line errors."""

    _, body, body_start_line = _read_note(path)
    records: list[WatchlistFilm] = []
    diagnostics: list[Diagnostic] = []
    seen: set[tuple[str, int | None]] = set()

    for offset, raw_line in enumerate(body.splitlines()):
        line_number = body_start_line + offset
        line = raw_line.strip()
        if not line or line.startswith(("#", "<!--")):
            continue
        line = _LIST_PREFIX.sub("", line)
        line = _CHECKBOX.sub("", line).strip()
        if not line:
            continue
        try:
            record = _parse_watchlist_line(line)
        except (ValueError, ValidationError) as error:
            diagnostics.append(
                Diagnostic(
                    "error",
                    "invalid-watchlist-line",
                    _error_message(error),
                    path,
                    line_number,
                )
            )
            continue
        key = film_identity(record.title, record.year)
        if key in seen:
            diagnostics.append(
                Diagnostic(
                    "error",
                    "duplicate-watchlist-film",
                    f"duplicate watchlist film: {record.title}",
                    path,
                    line_number,
                )
            )
            continue
        seen.add(key)
        records.append(record)
    return records, diagnostics


def normalize_score(
    raw_value: object,
    *,
    scale: int | None = None,
) -> float:
    """Normalize a 5- or 10-point score and enforce half-point output steps."""

    if isinstance(raw_value, bool):
        raise ValueError("score must be a number")
    parsed_scale = scale
    if isinstance(raw_value, (int, float)):
        score = float(raw_value)
    elif isinstance(raw_value, str):
        value = raw_value.strip()
        if value and set(value) <= {"★", "☆"}:
            score = float(value.count("★"))
            parsed_scale = 5
        else:
            match = _SCORE.fullmatch(value)
            if match is None:
                raise ValueError(f"invalid score: {raw_value!r}")
            score = float(match.group("score"))
            if match.group("scale") is not None:
                parsed_scale = int(match.group("scale"))
    else:
        raise ValueError("score must be a number or number/scale string")

    if parsed_scale not in (None, 5, 10):
        raise ValueError("rating scale must be 5 or 10")
    if parsed_scale == 5:
        if not 0 <= score <= 5:
            raise ValueError("5-point score must be between 0 and 5")
        score *= 2
    elif not 0 <= score <= 10:
        raise ValueError("score must be between 0 and 10")

    if abs(score * 2 - round(score * 2)) > 1e-9:
        raise ValueError("score must use 0.5 increments")
    return score


def _parse_watchlist_line(line: str) -> WatchlistFilm:
    segments = [
        segment.strip()
        for segment in re.split(r"\s+[\N{EM DASH}\N{EN DASH}]\s+|\s+\|\s+", line)
    ]
    if not segments or not segments[0]:
        raise ValueError("missing film title")
    raw_title = _strip_markdown_link(segments[0])
    title, year = _split_title_year(raw_title)
    interest: float | None = None
    notes: list[str] = []
    tags: list[str] = []
    dismissed = False

    for segment in segments[1:]:
        key, separator, raw_value = segment.partition(":")
        normalized_key = key.strip().casefold()
        value = raw_value.strip()
        if separator and normalized_key in {"interest", "score"}:
            interest = normalize_score(value, scale=10)
        elif separator and normalized_key == "year":
            year = _optional_int(value, "year")
        elif separator and normalized_key in {"note", "notes"}:
            if value:
                notes.append(value)
        elif separator and normalized_key in {"tag", "tags"}:
            tags.extend(_string_list(value))
        elif separator and normalized_key == "dismissed":
            dismissed = _parse_bool(value)
        elif segment:
            notes.append(segment)

    return WatchlistFilm(
        title=title,
        year=year,
        interest=interest,
        notes=" — ".join(notes),
        tags=tags,
        dismissed=dismissed,
    )


def _read_note(path: Path) -> tuple[dict[str, object], str, int]:
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    if not lines or _FRONTMATTER_DELIMITER.fullmatch(lines[0]) is None:
        return {}, text, 1

    closing_index: int | None = None
    for index in range(1, len(lines)):
        if _FRONTMATTER_DELIMITER.fullmatch(lines[index]) is not None:
            closing_index = index
            break
    if closing_index is None:
        raise ValueError("frontmatter starts with '---' but has no closing delimiter")

    yaml_text = "\n".join(lines[1:closing_index])
    try:
        loaded: object = yaml.safe_load(yaml_text)
    except yaml.YAMLError as error:
        raise ValueError(f"invalid YAML frontmatter: {error}") from error
    if loaded is None:
        metadata: dict[str, object] = {}
    elif isinstance(loaded, dict):
        loaded_mapping = cast(dict[object, object], loaded)
        metadata = {str(key): value for key, value in loaded_mapping.items()}
    else:
        raise ValueError("frontmatter must be a YAML mapping")
    body = "\n".join(lines[closing_index + 1 :])
    return metadata, body, closing_index + 2


def _get(metadata: dict[str, object], *keys: str) -> object | None:
    folded = {key.casefold(): value for key, value in metadata.items()}
    for key in keys:
        if key.casefold() in folded:
            return folded[key.casefold()]
    return None


def _split_title_year(raw_title: str) -> tuple[str, int | None]:
    title = raw_title.strip()
    match = _TITLE_YEAR.fullmatch(title)
    if match is None:
        if not title:
            raise ValueError("film title cannot be empty")
        return title, None
    parsed_title = match.group("title").strip()
    if not parsed_title:
        raise ValueError("film title cannot be empty")
    return parsed_title, int(match.group("year"))


def _optional_int(value: object | None, label: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    try:
        integer = int(str(value))
    except ValueError as error:
        raise ValueError(f"{label} must be an integer") from error
    if str(integer) != str(value).strip() and not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return integer


def _optional_date(value: object | None, label: str) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as error:
        raise ValueError(f"{label} must use YYYY-MM-DD") from error


def _string_list(value: object | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_values = re.split(r"\s*,\s*|\s+", value.strip())
    elif isinstance(value, list):
        raw_values = [str(item) for item in cast(list[object], value)]
    else:
        raw_values = [str(value)]
    return [item.removeprefix("#").strip() for item in raw_values if item.strip()]


def _optional_string(value: object | None) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _strip_markdown_link(value: str) -> str:
    wiki_match = re.fullmatch(r"\[\[([^]|]+)(?:\|[^]]+)?\]\]", value)
    if wiki_match is not None:
        return wiki_match.group(1).strip()
    markdown_match = re.fullmatch(r"\[([^]]+)]\([^)]+\)", value)
    if markdown_match is not None:
        return markdown_match.group(1).strip()
    return value


def _parse_bool(value: str) -> bool:
    normalized = value.casefold()
    if normalized in {"true", "yes", "1"}:
        return True
    if normalized in {"false", "no", "0"}:
        return False
    raise ValueError("dismissed must be true or false")


def _duplicate_diagnostics(
    watched: list[WatchedFilm], watchlist: list[WatchlistFilm]
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    seen_watched: set[tuple[str, int | None] | tuple[str, int]] = set()
    for film in watched:
        key: tuple[str, int | None] | tuple[str, int]
        key = ("tmdb", film.tmdb_id) if film.tmdb_id is not None else film_identity(
            film.title, film.year
        )
        if key in seen_watched:
            diagnostics.append(
                Diagnostic("error", "duplicate-review", f"duplicate review film: {film.title}")
            )
        seen_watched.add(key)

    watched_titles = {film_identity(film.title, film.year) for film in watched}
    watched_ids = {film.tmdb_id for film in watched if film.tmdb_id is not None}
    for film in watchlist:
        if film_identity(film.title, film.year) in watched_titles or (
            film.tmdb_id is not None and film.tmdb_id in watched_ids
        ):
            diagnostics.append(
                Diagnostic(
                    "error",
                    "watched-on-watchlist",
                    f"film appears in reviews and watchlist: {film.title}",
                )
            )
    return diagnostics


def _error_message(error: ValueError | ValidationError) -> str:
    if isinstance(error, ValidationError):
        first = error.errors(include_url=False)[0]
        location = ".".join(str(part) for part in first["loc"])
        return f"{location}: {first['msg']}" if location else str(first["msg"])
    return str(error)
