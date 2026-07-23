"""Command-line interface for local Filmography snapshot generation."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from contextlib import ExitStack
from pathlib import Path

from filmography.ai import AIError, OpenAICompatibleClient
from filmography.builder import (
    BuildResult,
    build_snapshot,
    load_snapshot,
    refresh_ai_recommendations,
    write_snapshot,
)
from filmography.markdown_notes import ImportValidationError, import_markdown_notes
from filmography.tmdb import TMDBClient

_DEFAULT_OUTPUT = Path("public/data/filmography.json")
_DEFAULT_CACHE = Path(".filmography-cache/tmdb")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="filmography",
        description="Build a public film journal from local Markdown notes.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="validate source notes without writing")
    _add_sources(check_parser)

    build_command = subparsers.add_parser("build", help="generate the public snapshot")
    _add_sources(build_command)
    _add_build_options(build_command)

    recommend_command = subparsers.add_parser(
        "recommend", help="generate and verify a fresh AI recommendation set"
    )
    _add_sources(recommend_command)
    _add_build_options(recommend_command)
    recommend_command.add_argument("--prompt", help="optional mood or discovery request")
    recommend_command.add_argument(
        "--count",
        type=_recommendation_count,
        default=10,
        help="number of verified AI suggestions to publish, 5-20 (default: 10)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    reviews = Path(args.reviews)
    watchlist = Path(args.watchlist)
    if args.command == "check":
        result = import_markdown_notes(reviews, watchlist)
        _print_diagnostics(result.diagnostics)
        if result.has_errors:
            return 1
        print(f"valid: {len(result.watched)} reviews, {len(result.watchlist)} watchlist films")
        return 0

    output = Path(args.output)
    try:
        previous = load_snapshot(output)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    tmdb_token = os.environ.get("TMDB_ACCESS_TOKEN", "").strip()
    try:
        with ExitStack() as stack:
            ai_client: OpenAICompatibleClient | None = None
            if args.command == "recommend":
                ai_client = _create_ai_client(stack)
                if ai_client is None:
                    return 2
            catalog = (
                stack.enter_context(TMDBClient(tmdb_token, Path(args.cache_dir)))
                if tmdb_token
                else None
            )
            if catalog is None and args.command == "recommend":
                print(
                    "error: TMDB_ACCESS_TOKEN is required for AI recommendation verification",
                    file=sys.stderr,
                )
                return 2
            built = build_snapshot(
                reviews,
                watchlist,
                catalog=catalog,
                previous=previous,
                deterministic_limit=args.deterministic_limit,
            )
            result = built
            ai_failure: AIError | None = None
            if args.command == "recommend":
                assert catalog is not None
                assert ai_client is not None
                try:
                    result = _combine_results(
                        built,
                        refresh_ai_recommendations(
                            built.snapshot,
                            ai_client,
                            catalog,
                            prompt=args.prompt,
                            limit=args.count,
                        ),
                    )
                except AIError as error:
                    ai_failure = error
            write_snapshot(result.snapshot, output)
            _print_diagnostics(result.diagnostics)
            print(
                f"wrote {output}: {len(result.snapshot.watched)} reviews, "
                f"{len(result.snapshot.watchlist)} watchlist films, "
                f"{len(result.snapshot.deterministic_discoveries)} local suggestions, "
                f"{len(result.snapshot.ai_discoveries)} AI suggestions"
            )
            if ai_failure is not None:
                print(
                    f"error: {ai_failure}; preserved the previous AI recommendation set",
                    file=sys.stderr,
                )
                return 1
            return 0
    except ImportValidationError as error:
        _print_diagnostics(error.diagnostics)
        return 1
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _add_sources(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--reviews", type=Path, required=True, help="folder of review notes")
    parser.add_argument("--watchlist", type=Path, required=True, help="single watchlist note")


def _add_build_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help=f"snapshot path (default: {_DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=_DEFAULT_CACHE,
        help=f"TMDB cache (default: {_DEFAULT_CACHE})",
    )
    parser.add_argument(
        "--deterministic-limit",
        type=int,
        default=12,
        help="maximum token-free suggestions (default: 12)",
    )


def _recommendation_count(value: str) -> int:
    try:
        count = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("AI suggestion count must be an integer") from error
    if not 5 <= count <= 20:
        raise argparse.ArgumentTypeError("AI suggestion count must be between 5 and 20")
    return count


def _create_ai_client(stack: ExitStack) -> OpenAICompatibleClient | None:
    api_key = os.environ.get("FILMOGRAPHY_AI_API_KEY", "").strip()
    model = os.environ.get("FILMOGRAPHY_AI_MODEL", "").strip()
    base_url = os.environ.get("FILMOGRAPHY_AI_BASE_URL", "https://api.openai.com/v1").strip()
    raw_max_tokens = os.environ.get("FILMOGRAPHY_AI_MAX_TOKENS", "8000").strip()
    missing = [
        name
        for name, value in (
            ("FILMOGRAPHY_AI_API_KEY", api_key),
            ("FILMOGRAPHY_AI_MODEL", model),
            ("FILMOGRAPHY_AI_BASE_URL", base_url),
        )
        if not value
    ]
    if missing:
        print(f"error: missing AI configuration: {', '.join(missing)}", file=sys.stderr)
        return None
    try:
        max_tokens = int(raw_max_tokens)
    except ValueError:
        print("error: FILMOGRAPHY_AI_MAX_TOKENS must be an integer", file=sys.stderr)
        return None
    try:
        return stack.enter_context(
            OpenAICompatibleClient(api_key, model, base_url, max_tokens=max_tokens)
        )
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return None


def _combine_results(first: BuildResult, second: BuildResult) -> BuildResult:
    return BuildResult(second.snapshot, (*first.diagnostics, *second.diagnostics))


def _print_diagnostics(diagnostics: Sequence[object]) -> None:
    for diagnostic in diagnostics:
        print(str(diagnostic), file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
