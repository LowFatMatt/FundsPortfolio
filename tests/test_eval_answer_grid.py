"""Unit tests for the answer-grid generator."""

from funds_portfolio.eval.answer_grid import (
    REGIONS,
    build_answer_grid,
    cap_grid,
    grid_summary,
)


def test_default_grid_count_matches_combinatorics():
    # Default max_regions=2 (UI cap), max_themes=2.
    grid = build_answer_grid()
    region_subsets = (
        1 + len(REGIONS) + len(REGIONS) * (len(REGIONS) - 1) // 2
    )  # C(5,0..2)=16
    theme_subsets = 1 + 11 + 55  # C(11,0..2)
    expected = 3 * 3 * 3 * region_subsets * theme_subsets
    assert len(grid) == expected == 28_944


def test_full_unconstrained_grid_count():
    # max_regions=None relaxes the UI cap -> all 2^5 region subsets.
    grid = build_answer_grid(max_regions=None)
    expected = 3 * 3 * 3 * (2 ** len(REGIONS)) * (1 + 11 + 55)
    assert len(grid) == expected == 57_888


def test_grid_is_deterministic_and_unique():
    a = build_answer_grid()
    b = build_answer_grid()
    assert a == b
    ids = [x["id"] for x in a]
    assert len(ids) == len(set(ids))  # no duplicate answer sets


def test_no_none_theme_and_sorted_selections():
    grid = build_answer_grid()
    assert grid, "grid must be non-empty"
    for answer in grid:
        assert "none" not in [t.lower() for t in answer["preferred_themes"]]
        assert answer["preferred_regions"] == sorted(answer["preferred_regions"])
        assert answer["preferred_themes"] == sorted(answer["preferred_themes"])
        assert len(answer["preferred_themes"]) <= 2


def test_all_region_and_theme_cardinalities_present():
    # Default grid is capped at 2 regions (UI); themes capped at 2 (schema).
    grid = build_answer_grid()
    region_sizes = {len(a["preferred_regions"]) for a in grid}
    theme_sizes = {len(a["preferred_themes"]) for a in grid}
    assert region_sizes == {0, 1, 2}
    assert theme_sizes == {0, 1, 2}

    # The unconstrained grid (max_regions=None) reaches all 0..5 region cardinalities.
    full = build_answer_grid(max_regions=None)
    assert {len(a["preferred_regions"]) for a in full} == set(
        range(0, len(REGIONS) + 1)
    )


def test_max_regions_and_max_themes_shrink_grid():
    full = build_answer_grid()
    one_region = build_answer_grid(max_regions=1)
    one_theme = build_answer_grid(max_themes=1)
    assert len(one_region) < len(full)
    assert len(one_theme) < len(full)
    assert all(len(a["preferred_regions"]) <= 1 for a in one_region)
    assert all(len(a["preferred_themes"]) <= 1 for a in one_theme)


def test_cap_grid_is_deterministic_and_sized():
    grid = build_answer_grid()
    capped_a = cap_grid(grid, 1500)
    capped_b = cap_grid(grid, 1500)
    assert capped_a == capped_b
    assert len(capped_a) == 1500
    assert {a["id"] for a in capped_a} <= {a["id"] for a in grid}
    assert cap_grid(grid, 10**9) == grid  # cap above size is a no-op


def test_grid_summary_reports_counts():
    grid = build_answer_grid(max_regions=1, max_themes=1)
    summary = grid_summary(grid)
    assert summary["total"] == len(grid)
    assert summary["distinct_ids"] == len(grid)
    assert set(summary["by_region_count"].keys()) == {0, 1}
    assert set(summary["by_theme_count"].keys()) == {0, 1}
