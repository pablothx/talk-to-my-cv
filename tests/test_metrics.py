import pytest

from talk_to_my_cv.evaluation import Source, hit_at_k, mean, reciprocal_rank

LUMEN = Source("experience/northwind-payments.md", "Senior Backend Engineer > Project Lumen")
SKILLS = Source("skills.md", "Languages")
OTHER = Source("profile.md", "Contact")


def test_hit_at_k_is_one_when_any_expected_source_is_in_the_top_k():
    ranked = [OTHER, SKILLS, LUMEN]

    assert hit_at_k(ranked, expected=[LUMEN], k=3) == 1.0
    assert hit_at_k(ranked, expected=[LUMEN], k=2) == 0.0
    assert hit_at_k(ranked, expected=[LUMEN, SKILLS], k=2) == 1.0


def test_reciprocal_rank_uses_the_first_expected_source_found():
    assert reciprocal_rank([LUMEN, OTHER], expected=[LUMEN]) == 1.0
    assert reciprocal_rank([OTHER, OTHER, LUMEN], expected=[LUMEN]) == pytest.approx(1 / 3)
    assert reciprocal_rank([OTHER, SKILLS, LUMEN], expected=[LUMEN, SKILLS]) == 0.5
    assert reciprocal_rank([OTHER], expected=[LUMEN]) == 0.0


def test_mean_of_nothing_is_none_not_a_crash():
    assert mean([1.0, 0.0, 0.5]) == 0.5
    assert mean([]) is None
