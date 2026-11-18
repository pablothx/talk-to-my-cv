import pytest

from talk_to_my_cv.graph import mentions, parse_terms


@pytest.mark.parametrize(
    ("reply", "terms"),
    [
        ("JavaScript", ["JavaScript"]),
        ("Acme Corp, Terraform", ["Acme Corp", "Terraform"]),
        ("**Azure**.", ["Azure"]),
        (" 'Kafka' ", ["Kafka"]),
        ("NONE", []),
        ("None.", []),
        ("", []),
    ],
)
def test_the_extractor_reply_becomes_a_list_of_names(reply, terms):
    assert parse_terms(reply) == terms


def test_a_reply_that_is_not_a_list_of_names_extracts_nothing():
    # A chatty reply would make every term "missing" and refuse: fail open instead.
    assert parse_terms("The question asks about her experience with cloud providers.") == []


@pytest.mark.parametrize(
    ("term", "text", "found"),
    [
        ("Kubernetes", "Kubernetes in production: the team chose ECS.", True),
        ("kubernetes", "KUBERNETES", True),
        ("JavaScript", "Java (expert), Kotlin, Python.", False),
        ("Java", "JavaScript only.", False),
        ("Acme Corp", "Worked at Acme  Corp.", True),
        ("Ríos", "Valentina Rios", True),
        ("C++", "C++ and Go.", True),
    ],
)
def test_a_term_is_mentioned_only_as_a_whole_word(term, text, found):
    assert mentions(term, text) is found
