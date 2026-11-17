import pytest

from talk_to_my_cv.embeddings import cosine_similarity


def test_same_direction_scores_one():
    assert cosine_similarity([1.0, 2.0, 3.0], [2.0, 4.0, 6.0]) == pytest.approx(1.0)


def test_orthogonal_vectors_score_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_zero_vector_is_rejected_instead_of_returning_nan():
    with pytest.raises(ValueError, match="zero vector"):
        cosine_similarity([0.0, 0.0], [1.0, 0.0])


def test_vectors_of_different_dimension_are_rejected():
    with pytest.raises(ValueError, match="dimension"):
        cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0])
