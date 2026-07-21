"""Optional OpenAI-compatible recommendations with strict structured output."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from filmography.models import (
    Recommendation,
    WatchedFilm,
    WatchlistFilm,
    film_matches_any,
    film_titles_overlap,
)
from filmography.tmdb import CatalogError, TMDBClient


class AIError(RuntimeError):
    """Raised when an AI provider cannot return valid structured suggestions."""


class AISuggestion(BaseModel):
    """Unverified title proposed by the AI provider."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1)
    year: int = Field(ge=1878, le=2200)
    predicted_rating: float = Field(alias="predictedRating", ge=0, le=10, multiple_of=0.5)
    rationale: str = Field(min_length=1, max_length=500)


class AISuggestionBatch(BaseModel):
    """Top-level structured response expected from the AI provider."""

    model_config = ConfigDict(extra="forbid")

    recommendations: list[AISuggestion] = Field(min_length=1, max_length=20)


@dataclass(frozen=True, slots=True)
class AIResolution:
    """Verified AI recommendations and non-fatal rejection explanations."""

    recommendations: tuple[Recommendation, ...]
    warnings: tuple[str, ...]


class OpenAICompatibleClient:
    """Call a chat-completions-compatible endpoint using JSON Schema output."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("AI API key cannot be empty")
        if not model.strip():
            raise ValueError("AI model cannot be empty")
        parsed_url = urlparse(base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("AI base URL must be an absolute HTTP(S) URL")
        self.model = model.strip()
        self.provider = "openai-compatible"
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=60.0,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> OpenAICompatibleClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def suggest(
        self,
        watched: list[WatchedFilm],
        watchlist: list[WatchlistFilm],
        *,
        prompt: str | None = None,
        count: int = 8,
    ) -> AISuggestionBatch:
        """Send the complete taste profile and validate the provider response."""

        if count < 1 or count > 20:
            raise ValueError("AI recommendation count must be between 1 and 20")
        taste_profile = {
            "watched": [
                {
                    "title": film.title,
                    "year": film.year,
                    "rating": film.rating,
                    "genres": film.genres,
                    "tags": film.tags,
                    "review": film.review,
                }
                for film in watched
            ],
            "watchlist": [
                {
                    "title": film.title,
                    "year": film.year,
                    "interest": film.interest,
                    "tags": film.tags,
                    "notes": film.notes,
                    "dismissed": film.dismissed,
                }
                for film in watchlist
            ],
            "request": prompt.strip() if prompt and prompt.strip() else None,
            "count": count,
        }
        response_schema = AISuggestionBatch.model_json_schema(by_alias=True)
        request_body = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You recommend feature films for one person. Infer taste from their "
                        "ratings and review text. Return only unseen films and make each "
                        "rationale specific "
                        "to the supplied history. Scores must use 0.5 increments on a 0-10 scale."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(taste_profile, ensure_ascii=False, separators=(",", ":")),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "film_recommendations",
                    "strict": True,
                    "schema": response_schema,
                },
            },
            "temperature": 0.4,
        }
        try:
            response = self._client.post("chat/completions", json=request_body)
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise AIError(_http_error_message(error.response)) from error
        except httpx.HTTPError as error:
            raise AIError(f"AI recommendation request failed: {error}") from error
        payload = _json_object(response.text)
        content = _extract_message_content(payload)
        try:
            return AISuggestionBatch.model_validate_json(content)
        except ValidationError as error:
            raise AIError(
                f"AI response does not match the recommendation schema: {error}"
            ) from error


def resolve_ai_suggestions(
    batch: AISuggestionBatch,
    catalog: TMDBClient,
    watched: list[WatchedFilm],
    watchlist: list[WatchlistFilm],
    *,
    generated_at: datetime,
    provider: str,
    model: str,
    limit: int = 8,
) -> AIResolution:
    """Reconcile proposed titles with TMDB and exclude all existing state."""

    excluded = [*watched, *watchlist]
    seen_ids: set[int] = set()
    recommendations: list[Recommendation] = []
    warnings: list[str] = []
    for suggestion in batch.recommendations:
        if len(recommendations) >= limit:
            break
        if any(
            film_titles_overlap(suggestion.title, suggestion.year, film.title, film.year)
            for film in excluded
        ):
            warnings.append(f"excluded existing film: {suggestion.title} ({suggestion.year})")
            continue
        try:
            match = catalog.match_movie(suggestion.title, suggestion.year)
        except CatalogError as error:
            warnings.append(f"could not verify {suggestion.title}: {error}")
            continue
        if match.status != "matched" or match.film is None or match.film.tmdb_id is None:
            warnings.append(f"{match.status} TMDB title: {suggestion.title} ({suggestion.year})")
            continue
        if match.film.tmdb_id in seen_ids:
            warnings.append(f"excluded duplicate film: {suggestion.title} ({suggestion.year})")
            continue
        if film_matches_any(match.film, excluded):
            warnings.append(f"excluded existing film: {suggestion.title} ({suggestion.year})")
            continue
        seen_ids.add(match.film.tmdb_id)
        recommendations.append(
            Recommendation(
                **match.film.model_dump(),
                predicted_rating=suggestion.predicted_rating,
                rationale=suggestion.rationale,
                source="ai",
                generated_at=generated_at,
                provider=provider,
                model=model,
            )
        )
    return AIResolution(tuple(recommendations), tuple(warnings))


def _json_object(raw_json: str) -> dict[str, object]:
    try:
        value: object = json.loads(raw_json)
    except json.JSONDecodeError as error:
        raise AIError("AI provider response is not valid JSON") from error
    if not isinstance(value, dict):
        raise AIError("AI provider response must be a JSON object")
    return cast(dict[str, object], value)


def _extract_message_content(payload: dict[str, object]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise AIError("AI provider response has no choices")
    first = cast(dict[str, object], choices[0])
    message = first.get("message")
    if not isinstance(message, dict):
        raise AIError("AI provider response has no message")
    typed_message = cast(dict[str, object], message)
    parsed = typed_message.get("parsed")
    if isinstance(parsed, dict):
        return json.dumps(parsed, ensure_ascii=False)
    content = typed_message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise AIError("AI provider message has no textual content")
    return content


def _http_error_message(response: httpx.Response) -> str:
    status = response.status_code
    if status == 401:
        return "AI recommendation request failed: OpenAI rejected the API key (401 Unauthorized)"
    if status == 403:
        return (
            "AI recommendation request failed: OpenAI account or project lacks access "
            "(403 Forbidden)"
        )
    if status == 429:
        return (
            "AI recommendation request failed: OpenAI rate limit or quota exceeded "
            "(429 Too Many Requests). Try again later, lower --count, use a smaller model, "
            "or check project billing/usage limits."
        )
    if 500 <= status < 600:
        return f"AI recommendation request failed: provider server error ({status})"
    return f"AI recommendation request failed: provider returned HTTP {status}"
