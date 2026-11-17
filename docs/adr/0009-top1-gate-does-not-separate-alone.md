# The top-1 gate does not separate answerable from unanswerable on its own

Step 5 measured ADR-0006 on 20 questions about `kb.example/` with `bge-m3`. Answerable questions scored below unanswerable ones: `degree` scored 0.41 and `team-size` 0.43, while `azure` scored 0.48 and `salary` 0.44. Among the traps, Kubernetes (0.51, has an answer) sits next to JavaScript (0.50, has none). No threshold reaches the target of refusal accuracy ≥ 0.9.

We keep the gate, because it is deterministic, free and impossible to talk around, but we change how its threshold is chosen. The gate-only sweep only proposes candidates (its best was 0.49). The full eval with the LLM decides between them: 0.42 won (refusal accuracy 0.88 vs 0.82), because the LLM refuses well what a lower gate lets through, while a higher gate refuses answerable questions the LLM never sees.

## Consequences

- The threshold is calibrated on the same 20 questions the eval reports: the numbers are optimistic (overfitting). New questions are needed to trust them.
- Step 7 adds an LLM verification step after retrieval: it decides whether the retrieved chunks actually answer the question, instead of relying on the score alone.
