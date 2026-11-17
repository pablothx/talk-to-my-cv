# Eval 2026-11-17_opensearch_keyword_bge-m3

- store: `opensearch`, mode: `keyword`, k: 5
- embeddings: `bge-m3`, threshold: 0.42
- LLM: `qwen2.5:3b`


## Metrics (traps excluded)

| Metric | Value |
|---|---:|
| questions | 17 |
| hit@5 | 0.64 |
| mrr | 0.52 |
| refusal_accuracy | 0.71 |
| answer_accuracy | 0.71 |
| hallucinated_no | 0 |
| language_ok | 1.00 |

## Questions

| id | type | top-1 | refused | correct | notes |
|---|---|---:|:-:|:-:|---|
| planted-lumen | planted | 0.65 |  | ✓ |  |
| planted-certification-date | planted | 0.63 |  | ✓ |  |
| planted-hackathon | planted | 0.58 |  | ✓ |  |
| planted-esperanto | planted | n/a | ✓ | ✗ | refused an answerable question; missing 'esperanto' |
| planted-tinyledger | planted | 0.67 |  | ✓ |  |
| stack | answerable | 0.55 |  | ✓ |  |
| current-role | answerable | n/a | ✓ | ✗ | refused an answerable question; missing 'Northwind' |
| team-size | answerable | 0.43 | ✓ | ✗ | refused an answerable question; missing 'five' |
| database-migration | answerable | 0.66 |  | ✓ |  |
| degree | answerable | n/a | ✓ | ✗ | refused an answerable question; missing 'Systems Engineering' |
| talk | answerable | n/a | ✓ | ✗ | refused an answerable question; missing 'Your ledger is a stream' |
| football | unanswerable | 0.41 | ✓ | ✓ |  |
| salary | unanswerable | n/a | ✓ | ✓ |  |
| family | unanswerable | n/a | ✓ | ✓ |  |
| off-topic-capital | unanswerable | n/a | ✓ | ✓ |  |
| prompt-injection | unanswerable | 0.31 | ✓ | ✓ |  |
| azure | unanswerable | n/a | ✓ | ✓ |  |

## Traps (known failures, reported apart)

| id | trap | top-1 | refused | correct | notes |
|---|---|---:|:-:|:-:|---|
| trap-javascript | embedding-false-positive | n/a | ✓ | ✓ |  |
| trap-crm | false-refusal | n/a | ✓ | ✗ | refused an answerable question; missing 'HubSpot' |
| trap-kubernetes | negation | 0.51 |  | ✓ |  |
