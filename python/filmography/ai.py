"""Optional OpenAI-compatible recommendations with strict structured output."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from filmography.models import (
    FilmMetadata,
    Recommendation,
    WatchedFilm,
    WatchlistFilm,
    film_matches_any,
    film_titles_overlap,
)
from filmography.recommendations import calibrate_personal_score
from filmography.tmdb import CatalogError, TMDBClient


class AIError(RuntimeError):
    """Raised when an AI provider cannot return valid structured suggestions."""


class AISuggestion(BaseModel):
    """Unverified title proposed by the AI provider."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1)
    year: int = Field(ge=1878, le=2200)
    predicted_rating: float = Field(alias="predictedRating", ge=0, le=10, multiple_of=0.1)
    rationale: str = Field(min_length=1, max_length=500)


class AITargetScore(BaseModel):
    """Expected personal score for an existing public snapshot record."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    target: str = Field(min_length=1)
    predicted_rating: float = Field(alias="predictedRating", ge=0, le=10, multiple_of=0.1)


class AISuggestionBatch(BaseModel):
    """Structured recommendation response expected from the AI provider."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    recommendations: list[AISuggestion] = Field(min_length=1, max_length=20)


class AITargetScoreBatch(BaseModel):
    """Structured scoring response expected from the AI provider."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    watchlist_scores: list[AITargetScore] = Field(
        default_factory=lambda: list[AITargetScore](),
        alias="watchlistScores",
        max_length=200,
    )
    discovery_scores: list[AITargetScore] = Field(
        default_factory=lambda: list[AITargetScore](),
        alias="discoveryScores",
        max_length=200,
    )


@dataclass(frozen=True, slots=True)
class AIResolution:
    """Verified AI recommendations and non-fatal rejection explanations."""

    recommendations: tuple[Recommendation, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AIScoreResolution:
    """Verified AI scores and non-fatal rejection explanations."""

    watchlist_scores: tuple[tuple[str, float], ...]
    discovery_scores: tuple[tuple[str, float], ...]
    warnings: tuple[str, ...]


class OpenAICompatibleClient:
    """Call a chat-completions-compatible endpoint using JSON Schema output."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        *,
        max_tokens: int = 48000,
        http_client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("AI API key cannot be empty")
        if not model.strip():
            raise ValueError("AI model cannot be empty")
        parsed_url = urlparse(base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("AI base URL must be an absolute HTTP(S) URL")
        if not 128 <= max_tokens <= 128000:
            raise ValueError("AI max tokens must be between 128 and 128000")
        self.model = model.strip()
        self.provider = "openai-compatible"
        self.max_tokens = max_tokens
        self._disable_openrouter_reasoning = parsed_url.hostname == "openrouter.ai"
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
        count: int = 10,
    ) -> AISuggestionBatch:
        """Request unseen film suggestions and validate the provider response."""

        if count < 1 or count > 20:
            raise ValueError("AI recommendation count must be between 1 and 20")
        taste_profile = _taste_profile(
            watched,
            watchlist,
            prompt=prompt,
            count=count,
            include_watchlist_details=False,
        )
        response_schema = _suggestion_response_schema(minimum_recommendations=min(5, count))
        return _parse_suggestion_content(
            self._post_structured_chat(
                system_prompt=_suggestion_system_prompt(),
                payload=taste_profile,
                schema_name="film_recommendations",
                response_schema=response_schema,
                error_context="AI recommendation request failed",
            ),
        )

    def score_targets(
        self,
        watched: list[WatchedFilm],
        watchlist: list[WatchlistFilm],
        *,
        deterministic_discoveries: list[Recommendation] | None = None,
        prompt: str | None = None,
    ) -> AITargetScoreBatch:
        """Request expected scores for known films and validate the provider response."""

        deterministic_discoveries = deterministic_discoveries or []
        watchlist_score_targets = [
            _score_target_payload("watchlist", film)
            for film in watchlist
            if not film.dismissed and film.interest_source != "manual"
        ]
        discovery_score_targets = [
            _score_target_payload("discovery", film) for film in deterministic_discoveries
        ]
        taste_profile = _taste_profile(
            watched,
            watchlist,
            prompt=prompt,
            watchlist_score_targets=watchlist_score_targets,
            discovery_score_targets=discovery_score_targets,
        )
        return _parse_score_content(
            self._post_structured_chat(
                system_prompt=_scoring_system_prompt(),
                payload=taste_profile,
                schema_name="film_scores",
                response_schema=_score_response_schema(),
                error_context="AI scoring request failed",
            ),
        )

    def _post_structured_chat(
        self,
        *,
        system_prompt: str,
        payload: dict[str, object],
        schema_name: str,
        response_schema: dict[str, object],
        error_context: str,
    ) -> str:
        request_body: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": response_schema,
                },
            },
            "temperature": 0.4,
            "max_tokens": self.max_tokens,
        }
        if self._disable_openrouter_reasoning:
            request_body["reasoning"] = {"effort": "none", "exclude": True}
        try:
            response = self._client.post("chat/completions", json=request_body)
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise AIError(_http_error_message(error.response)) from error
        except httpx.HTTPError as error:
            raise AIError(f"{error_context}: {error}") from error
        payload = _json_object(response.text)
        return _extract_message_content(payload)


def score_target_id(collection: Literal["watchlist", "discovery"], film: FilmMetadata) -> str:
    """Return a stable, public identifier that an AI provider can echo safely."""

    identity = (
        str(film.tmdb_id)
        if film.tmdb_id is not None
        else f"{film.media_type}:{film.title.casefold()}:{film.year or 'unknown'}"
    )
    return f"{collection}:{identity}"


def _score_target_payload(
    collection: Literal["watchlist", "discovery"], film: FilmMetadata
) -> dict[str, object]:
    return {
        "target": score_target_id(collection, film),
        "title": film.title,
        "year": film.year,
        "mediaType": film.media_type,
        "genres": film.genres,
        "overview": film.overview,
        "tmdbAudienceScore": film.vote_average,
    }


def _taste_profile(
    watched: list[WatchedFilm],
    watchlist: list[WatchlistFilm],
    *,
    prompt: str | None = None,
    count: int | None = None,
    include_watchlist_details: bool = True,
    watchlist_score_targets: list[dict[str, object]] | None = None,
    discovery_score_targets: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    profile: dict[str, object] = {
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
        "request": prompt.strip() if prompt and prompt.strip() else None,
        "exclusions": [{"title": film.title, "year": film.year} for film in [*watched, *watchlist]],
        "forbiddenTitles": _forbidden_titles([*watched, *watchlist]),
    }
    if include_watchlist_details:
        profile["watchlist"] = [
            {
                "title": film.title,
                "year": film.year,
                "interest": film.interest,
                "interestSource": film.interest_source,
                "genres": film.genres,
                "overview": film.overview,
                "tmdbAudienceScore": film.vote_average,
                "tags": film.tags,
                "notes": film.notes,
                "dismissed": film.dismissed,
            }
            for film in watchlist
        ]
    if count is not None:
        profile["count"] = count
    if watchlist_score_targets is not None:
        profile["watchlistScoreTargets"] = watchlist_score_targets
    if discovery_score_targets is not None:
        profile["discoveryScoreTargets"] = discovery_score_targets
    return profile


def _forbidden_titles(films: list[FilmMetadata]) -> list[str]:
    titles: set[str] = set()
    for film in films:
        if film.year is None:
            titles.add(film.title)
            if film.original_title and film.original_title != film.title:
                titles.add(film.original_title)
            continue
        titles.add(f"{film.title} ({film.year})")
        if film.original_title and film.original_title != film.title:
            titles.add(f"{film.original_title} ({film.year})")
    return sorted(titles, key=str.casefold)


def _suggestion_system_prompt() -> str:
    return (
        "You recommend feature films for one person. Infer taste from their ratings and "
        "review text. Calibrate every predicted score to the person's actual scoring "
        "habits: preserve their observed range and treat 10.0 as exceptional rather than "
        "a default for a strong match. Return the requested number of unseen films and "
        "make each rationale specific to the film and the supplied history. Each "
        "rationale must name a concrete theme, premise, mood, craft element, or "
        "comparison. Do not say it was suggested by the model, fits the profile, matches "
        "preferences, or is recommended without explaining why. Scores must use 0.1 "
        "increments on a 0-10 scale. Never recommend any title from watched, "
        "exclusions, or forbiddenTitles, including translated versions of the same "
        "film. The forbiddenTitles array is a hard blocklist, not a source of ideas. "
        "Prefer films, not TV series. If your provider does not support "
        "response_format, return one valid JSON object with a recommendations array. "
        "Do not use Markdown."
    )


def _scoring_system_prompt() -> str:
    return (
        "You estimate how one person would score known films. Infer taste from their "
        "ratings and review text, then return one predicted score for every "
        "watchlistScoreTargets and discoveryScoreTargets item. Copy each target value "
        "exactly. Calibrate every predicted score to the person's actual scoring habits: "
        "preserve their observed range and treat 10.0 as exceptional rather than a "
        "default for a strong match. Scores must use 0.1 increments on a 0-10 scale. "
        "Explicit manual watchlist scores are intentionally absent and must not be "
        "replaced. Do not recommend new films in this request. If your provider does "
        "not support response_format, return one valid JSON object with watchlistScores "
        "and discoveryScores arrays. Do not use Markdown."
    )


def resolve_ai_suggestions(
    batch: AISuggestionBatch,
    catalog: TMDBClient,
    watched: list[WatchedFilm],
    watchlist: list[WatchlistFilm],
    *,
    deterministic_discoveries: list[Recommendation] | None = None,
    generated_at: datetime,
    provider: str,
    model: str,
    limit: int = 10,
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
                predicted_rating=calibrate_personal_score(watched, suggestion.predicted_rating),
                score_source="ai",
                rationale=_publication_rationale(suggestion.rationale, match.film.overview),
                source="ai",
                generated_at=generated_at,
                provider=provider,
                model=model,
            )
        )
    return AIResolution(
        recommendations=tuple(recommendations),
        warnings=tuple(warnings),
    )


def resolve_ai_scores(
    batch: AITargetScoreBatch,
    watched: list[WatchedFilm],
    watchlist: list[WatchlistFilm],
    deterministic_discoveries: list[Recommendation],
) -> AIScoreResolution:
    """Reconcile target scores with the current snapshot state."""

    warnings: list[str] = []
    watchlist_targets = {
        score_target_id("watchlist", film): film
        for film in watchlist
        if not film.dismissed and film.interest_source != "manual"
    }
    discovery_targets = {
        score_target_id("discovery", film): film for film in deterministic_discoveries
    }
    watchlist_scores = _resolve_target_scores(
        batch.watchlist_scores,
        watchlist_targets,
        watched,
        "watchlist",
        warnings,
    )
    discovery_scores = _resolve_target_scores(
        batch.discovery_scores,
        discovery_targets,
        watched,
        "discovery",
        warnings,
    )
    return AIScoreResolution(
        watchlist_scores=watchlist_scores,
        discovery_scores=discovery_scores,
        warnings=tuple(warnings),
    )


def _resolve_target_scores(
    scores: list[AITargetScore],
    targets: Mapping[str, FilmMetadata],
    watched: list[WatchedFilm],
    collection: str,
    warnings: list[str],
) -> tuple[tuple[str, float], ...]:
    resolved: dict[str, float] = {}
    for score in scores:
        if score.target not in targets:
            warnings.append(f"ignored unknown AI {collection} score target: {score.target}")
            continue
        if score.target in resolved:
            warnings.append(f"ignored duplicate AI {collection} score target: {score.target}")
            continue
        resolved[score.target] = calibrate_personal_score(watched, score.predicted_rating)
    for target, film in targets.items():
        if target not in resolved:
            warnings.append(f"AI did not score {collection} title: {film.title}")
    return tuple((target, resolved[target]) for target in targets if target in resolved)


def _suggestion_response_schema(minimum_recommendations: int) -> dict[str, object]:
    schema = cast(dict[str, object], AISuggestionBatch.model_json_schema(by_alias=True))
    properties_value = schema.get("properties")
    if isinstance(properties_value, dict):
        properties = cast(dict[str, object], properties_value)
        recommendations_value = properties.get("recommendations")
        if isinstance(recommendations_value, dict):
            recommendations = cast(dict[str, object], recommendations_value)
            recommendations["minItems"] = minimum_recommendations
    return schema


def _score_response_schema() -> dict[str, object]:
    schema = cast(dict[str, object], AITargetScoreBatch.model_json_schema(by_alias=True))
    schema["required"] = ["watchlistScores", "discoveryScores"]
    return schema


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
        raise AIError(f"AI provider response has no choices ({_response_summary(payload)})")
    first = cast(dict[str, object], choices[0])
    message = first.get("message")
    if not isinstance(message, dict):
        raise AIError(f"AI provider response has no message ({_choice_summary(first, payload)})")
    typed_message = cast(dict[str, object], message)
    parsed = typed_message.get("parsed")
    if isinstance(parsed, dict):
        return json.dumps(parsed, ensure_ascii=False)
    content = typed_message.get("content")
    if isinstance(content, list):
        content = _text_from_content_parts(cast(list[object], content))
    if not isinstance(content, str) or not content.strip():
        raise AIError(
            "AI provider message has no textual content "
            f"({_message_summary(first, typed_message, payload)})"
        )
    return content


def _text_from_content_parts(content: list[object]) -> str:
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        typed_item = cast(dict[str, object], item)
        text = typed_item.get("text")
        if isinstance(text, str):
            parts.append(text)
            continue
        nested_text = typed_item.get("content")
        if isinstance(nested_text, str):
            parts.append(nested_text)
    return "\n".join(part for part in parts if part.strip())


def _response_summary(payload: dict[str, object]) -> str:
    keys = ", ".join(sorted(payload))
    usage = _usage_summary(payload.get("usage"))
    return _join_summary_parts(f"top-level keys=[{keys or 'none'}]", usage)


def _choice_summary(choice: dict[str, object], payload: dict[str, object]) -> str:
    return _join_summary_parts(
        f"choice keys=[{', '.join(sorted(choice)) or 'none'}]",
        _finish_reason_summary(choice),
        _usage_summary(payload.get("usage")),
    )


def _message_summary(
    choice: dict[str, object], message: dict[str, object], payload: dict[str, object]
) -> str:
    content = message.get("content")
    parsed = message.get("parsed")
    tool_calls = message.get("tool_calls")
    return _join_summary_parts(
        f"finish_reason={_safe_scalar(choice.get('finish_reason'))}",
        f"message keys=[{', '.join(sorted(message)) or 'none'}]",
        f"content_type={type(content).__name__}",
        f"parsed_type={type(parsed).__name__}",
        _tool_calls_summary(tool_calls),
        _refusal_summary(message.get("refusal")),
        _usage_summary(payload.get("usage")),
    )


def _finish_reason_summary(choice: dict[str, object]) -> str:
    return f"finish_reason={_safe_scalar(choice.get('finish_reason'))}"


def _tool_calls_summary(value: object) -> str:
    if isinstance(value, list):
        return f"tool_calls={len(cast(list[object], value))}"
    return f"tool_calls_type={type(value).__name__}"


def _refusal_summary(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    return f"refusal={_preview(value)}"


def _usage_summary(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    usage = cast(dict[str, object], value)
    interesting = (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "input_tokens",
        "output_tokens",
    )
    parts = [f"{key}={usage[key]}" for key in interesting if isinstance(usage.get(key), int)]
    return f"usage[{', '.join(parts)}]" if parts else ""


def _safe_scalar(value: object) -> str:
    if isinstance(value, str):
        return _preview(value)
    if value is None or isinstance(value, (int, float, bool)):
        return repr(value)
    return type(value).__name__


def _preview(value: str, *, limit: int = 160) -> str:
    collapsed = " ".join(value.split())
    if len(collapsed) > limit:
        collapsed = f"{collapsed[: limit - 1]}..."
    return repr(collapsed)


def _join_summary_parts(*parts: str) -> str:
    return "; ".join(part for part in parts if part)


def _parse_suggestion_content(content: str) -> AISuggestionBatch:
    try:
        return AISuggestionBatch.model_validate_json(content)
    except ValidationError as original_error:
        extracted_json = _extract_json_object(content)
        for candidate in (content, extracted_json):
            batch = _validated_provider_json(candidate)
            if batch is not None:
                return batch
        markdown_batch = _parse_markdown_suggestions(content)
        if markdown_batch is not None:
            return markdown_batch
        raise AIError(
            f"AI response does not match the recommendation schema: {original_error}"
        ) from original_error


def _parse_score_content(content: str) -> AITargetScoreBatch:
    try:
        return AITargetScoreBatch.model_validate_json(content)
    except ValidationError as original_error:
        extracted_json = _extract_json_object(content)
        for candidate in (content, extracted_json):
            batch = _validated_provider_scores_json(candidate)
            if batch is not None:
                return batch
        raise AIError(
            f"AI response does not match the scoring schema: {original_error}"
        ) from original_error


def _validated_provider_json(content: str | None) -> AISuggestionBatch | None:
    if content is None:
        return None
    normalized = _normalize_provider_json(content)
    if normalized is None:
        return None
    try:
        return AISuggestionBatch.model_validate(normalized)
    except ValidationError:
        return None


def _validated_provider_scores_json(content: str | None) -> AITargetScoreBatch | None:
    if content is None:
        return None
    normalized = _normalize_provider_scores_json(content)
    if normalized is None:
        return None
    try:
        return AITargetScoreBatch.model_validate(normalized)
    except ValidationError:
        return None


def _extract_json_object(content: str) -> str | None:
    stripped = content.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    if fenced is not None:
        return fenced.group(1)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end <= start:
        return None
    return stripped[start : end + 1]


def _normalize_provider_json(content: str) -> dict[str, object] | None:
    try:
        raw: object = json.loads(content)
    except json.JSONDecodeError:
        return None
    if isinstance(raw, list):
        raw = {"recommendations": cast(list[object], raw)}
    if not isinstance(raw, dict):
        return None
    payload = cast(dict[str, object], raw)
    recommendations = payload.get("recommendations")
    if not isinstance(recommendations, list):
        return payload
    recommendation_items = cast(list[object], recommendations)
    normalized: list[object] = []
    for item in recommendation_items:
        if not isinstance(item, dict):
            continue
        suggestion = dict(cast(dict[str, object], item))
        normalized_suggestion = _normalize_provider_suggestion(suggestion)
        if normalized_suggestion is not None:
            normalized.append(normalized_suggestion)
    if not normalized:
        return None
    return {
        "recommendations": normalized,
    }


def _normalize_provider_scores_json(content: str) -> dict[str, object] | None:
    try:
        raw: object = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    payload = cast(dict[str, object], raw)
    return {
        "watchlistScores": _normalize_target_score_list(
            payload.get("watchlistScores", payload.get("watchlist_scores"))
        ),
        "discoveryScores": _normalize_target_score_list(
            payload.get("discoveryScores", payload.get("discovery_scores"))
        ),
    }


def _normalize_provider_suggestion(suggestion: dict[str, object]) -> dict[str, object] | None:
    title = suggestion.get("title")
    year = suggestion.get("year")
    rationale = suggestion.get("rationale")
    predicted_rating = suggestion.get("predictedRating")
    if predicted_rating is None:
        for alias in ("predicted_rating", "score", "rating"):
            if alias in suggestion:
                predicted_rating = suggestion[alias]
                break
    if not isinstance(title, str) or not title.strip():
        return None
    if isinstance(year, bool) or not isinstance(year, int):
        return None
    if isinstance(predicted_rating, bool) or not isinstance(predicted_rating, (int, float)):
        return None
    rating = float(predicted_rating)
    if not 0 <= rating <= 10 or abs(rating * 10 - round(rating * 10)) > 1e-9:
        return None
    if not isinstance(rationale, str) or not rationale.strip():
        rationale = "No specific rationale supplied."
    rationale = " ".join(rationale.split())[:500]
    return {
        "title": title,
        "year": year,
        "predictedRating": rating,
        "rationale": rationale,
    }


def _normalize_target_score_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, object]] = []
    for raw_item in cast(list[object], value):
        if not isinstance(raw_item, dict):
            continue
        item = cast(dict[str, object], raw_item)
        target = item.get("target", item.get("id"))
        predicted_rating = item.get("predictedRating")
        if predicted_rating is None:
            for alias in ("predicted_rating", "score", "rating"):
                if alias in item:
                    predicted_rating = item[alias]
                    break
        if not isinstance(target, str) or not target.strip():
            continue
        if isinstance(predicted_rating, bool) or not isinstance(predicted_rating, (int, float)):
            continue
        rating = float(predicted_rating)
        if not 0 <= rating <= 10 or abs(rating * 10 - round(rating * 10)) > 1e-9:
            continue
        normalized.append({"target": target, "predictedRating": rating})
    return normalized


def _parse_markdown_suggestions(content: str) -> AISuggestionBatch | None:
    matches = list(
        re.finditer(
            r"(?m)^\s*(?:[-*]|\d+[.)])?\s*\*\*(?P<title>[^*\n]+?)\s*\((?P<year>\d{4})\)\*\*",
            content,
        )
    )
    if not matches:
        return None
    recommendations: list[dict[str, object]] = []
    for index, match in enumerate(matches[:20]):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        body = content[start:end].strip(" \n:-")
        rating = _extract_markdown_rating(body)
        rationale = _clean_markdown_rationale(body)
        recommendations.append(
            {
                "title": match.group("title").strip(),
                "year": int(match.group("year")),
                "predictedRating": rating,
                "rationale": rationale or "No specific rationale supplied.",
            }
        )
    try:
        return AISuggestionBatch.model_validate({"recommendations": recommendations})
    except ValidationError:
        return None


def _extract_markdown_rating(value: str) -> float:
    match = re.search(
        r"(?i)(?:predicted\s+)?(?:rating|score)\s*[:=-]\s*(?P<score>\d+(?:\.\d+)?)",
        value,
    )
    if match is None:
        return 7.5
    score = float(match.group("score"))
    return round(max(0.0, min(10.0, score)) * 10) / 10


def _clean_markdown_rationale(value: str) -> str:
    text = re.sub(
        r"(?i)(?:predicted\s+)?(?:rating|score)\s*[:=-]\s*\d+(?:\.\d+)?(?:/10)?",
        "",
        value,
    )
    text = re.sub(r"[*_`#>-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .:-")
    return text[:500]


def _publication_rationale(raw_rationale: str, film_overview: str) -> str:
    rationale = " ".join(raw_rationale.split())
    if _is_generic_rationale(rationale):
        description = _short_description(film_overview)
        return description or "Review the premise before adding it to the watchlist."
    return rationale


def _is_generic_rationale(value: str) -> bool:
    normalized = value.casefold()
    generic_phrases = (
        "suggested by",
        "configured ai model",
        "fits the profile",
        "matches your profile",
        "matches your preferences",
        "recommended because",
        "worth watching because",
        "no specific rationale supplied",
    )
    return not value.strip() or any(phrase in normalized for phrase in generic_phrases)


def _short_description(value: str) -> str:
    text = " ".join(value.split())
    if not text:
        return ""
    first_sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0].strip()
    if len(first_sentence) <= 220:
        return first_sentence
    return f"{first_sentence[:217].rstrip()}..."


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
