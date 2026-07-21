from __future__ import annotations

from pathlib import Path

import pytest
from filmography.markdown_notes import (
    import_markdown_notes,
    normalize_score,
    parse_review_note,
    parse_watchlist_note,
)


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_review_uses_filename_and_keeps_numeric_rating_on_ten_point_scale(
    tmp_path: Path,
) -> None:
    note = _write(
        tmp_path / "Arrival (2016).md",
        """---
rating: 4
watchedAt: 2026-07-12
tags: [thoughtful, science-fiction, thoughtful]
---
The final scene **changes** everything.
""",
    )

    film = parse_review_note(note)

    assert film.title == "Arrival"
    assert film.year == 2016
    assert film.rating == 4
    assert film.watched_at is not None and film.watched_at.isoformat() == "2026-07-12"
    assert film.tags == ["thoughtful", "science-fiction"]
    assert film.review == "The final scene **changes** everything."


@pytest.mark.parametrize(
    ("rating_field", "expected"),
    [
        ("rating: 4/5", 8),
        ("rating: 4\nratingScale: 5", 8),
        ("stars: 4", 8),
        ('rating: "★★★★☆"', 8),
        ("rating: 8/10", 8),
    ],
)
def test_review_normalizes_only_explicit_five_point_scores(
    tmp_path: Path, rating_field: str, expected: float
) -> None:
    note = _write(
        tmp_path / "Film.md",
        f"---\n{rating_field}\n---\nReview",
    )

    assert parse_review_note(note).rating == expected


@pytest.mark.parametrize("value", ["7.2", "11", "bad", True])
def test_score_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ValueError):
        normalize_score(value)


def test_review_reads_supported_frontmatter_aliases(tmp_path: Path) -> None:
    note = _write(
        tmp_path / "ignored.md",
        """---
movie: The Matrix (1999)
score: 9.5
watched: 2024-01-02
tmdb: 603
genres: cyberpunk action
source: https://example.test/review
---
Still precise.
""",
    )

    film = parse_review_note(note)

    assert film.title == "The Matrix"
    assert film.year == 1999
    assert film.tmdb_id == 603
    assert film.rating == 9.5
    assert film.tags == ["cyberpunk", "action"]
    assert film.source_url == "https://example.test/review"


def test_review_rejects_missing_rating_and_malformed_frontmatter(tmp_path: Path) -> None:
    missing = _write(tmp_path / "Missing.md", "A review without metadata")
    malformed = _write(tmp_path / "Malformed.md", "---\nrating: [\n---\nBody")

    with pytest.raises(ValueError, match="missing required rating"):
        parse_review_note(missing)
    with pytest.raises(ValueError, match="invalid YAML"):
        parse_review_note(malformed)


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("title: {nested: value}", "title must be text"),
        ("tags: {private: value}", "tags must be text"),
        ("sourceUrl: {private: value}", "source URL must be text"),
    ],
)
def test_review_rejects_structured_values_in_text_fields(
    tmp_path: Path,
    field: str,
    message: str,
) -> None:
    note = _write(tmp_path / "Film.md", f"---\nrating: 8\n{field}\n---\nReview")

    with pytest.raises(ValueError, match=message):
        parse_review_note(note)


def test_watchlist_parses_bullets_plain_lines_and_optional_fields(tmp_path: Path) -> None:
    note = _write(
        tmp_path / "Watchlist.md",
        """---
title: Future films
---
# Queue
- [ ] Dune (2021) — interest: 9.5 — note: See on a large screen — tags: epic, sci-fi
2. [[Persona (1966)]] | interest: 8 | quiet evening
Moonlight (2016)
Dismiss Me (2000) — dismissed: yes
""",
    )

    films, diagnostics = parse_watchlist_note(note)

    assert diagnostics == []
    assert [film.title for film in films] == ["Dune", "Persona", "Moonlight", "Dismiss Me"]
    assert films[0].year == 2021
    assert films[0].interest == 9.5
    assert films[0].notes == "See on a large screen"
    assert films[0].tags == ["epic", "sci-fi"]
    assert films[1].interest == 8
    assert films[1].notes == "quiet evening"
    assert films[2].interest is None
    assert films[3].dismissed is True


def test_watchlist_reports_bad_lines_and_duplicates_without_stopping(tmp_path: Path) -> None:
    note = _write(
        tmp_path / "Watchlist.md",
        """- Good Film (2020) — interest: 7
- Bad Score (2021) — interest: 7.2
- Good Film (2020)
- Another Film (2022) — dismissed: perhaps
""",
    )

    films, diagnostics = parse_watchlist_note(note)

    assert [film.title for film in films] == ["Good Film"]
    assert [item.code for item in diagnostics] == [
        "invalid-watchlist-line",
        "duplicate-watchlist-film",
        "invalid-watchlist-line",
    ]
    assert [item.line for item in diagnostics] == [2, 3, 4]


def test_import_collects_review_errors_and_cross_collection_duplicates(tmp_path: Path) -> None:
    reviews = tmp_path / "reviews"
    _write(reviews / "Good Film (2020).md", "---\nrating: 8\n---\nGood")
    _write(reviews / "Broken.md", "---\ntitle: Broken\n---\nNo score")
    watchlist = _write(tmp_path / "Watchlist.md", "- Good Film (2020)\n")

    result = import_markdown_notes(reviews, watchlist)

    assert result.has_errors
    assert len(result.watched) == 1
    assert {item.code for item in result.diagnostics} == {
        "invalid-review",
        "watched-on-watchlist",
    }


def test_import_reports_missing_inputs(tmp_path: Path) -> None:
    result = import_markdown_notes(tmp_path / "missing-reviews", tmp_path / "missing-list.md")

    assert result.has_errors
    assert [item.code for item in result.diagnostics] == [
        "reviews-not-found",
        "watchlist-not-found",
    ]


def test_import_excludes_watchlist_note_when_it_is_inside_reviews_folder(tmp_path: Path) -> None:
    reviews = tmp_path / "notes"
    _write(reviews / "Arrival (2016).md", "---\nrating: 9\n---\nReview")
    watchlist = _write(reviews / "Watchlist.md", "- Persona (1966)\n")

    result = import_markdown_notes(reviews, watchlist)

    assert not result.has_errors
    assert [film.title for film in result.watched] == ["Arrival"]
    assert [film.title for film in result.watchlist] == ["Persona"]


def test_import_detects_duplicate_reviews_with_mixed_catalog_identity(tmp_path: Path) -> None:
    reviews = tmp_path / "reviews"
    _write(
        reviews / "Crash catalogued.md",
        "---\ntitle: Crash\nyear: 1996\ntmdbId: 884\nrating: 8\n---\nFirst",
    )
    _write(
        reviews / "Crash plain.md",
        "---\ntitle: Crash\nyear: 1996\nrating: 7\n---\nSecond",
    )
    watchlist = _write(tmp_path / "Watchlist.md", "")

    result = import_markdown_notes(reviews, watchlist)

    assert result.has_errors
    assert any(item.code == "duplicate-review" for item in result.diagnostics)
