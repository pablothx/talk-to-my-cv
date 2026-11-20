# Step 7: LangGraph and verification

🇪🇸 [Leer en español](README.es.md)

The chat still falls for the JavaScript trap: it answers "No" with citations, when the CV says nothing. In this step we add a **check** before answering, and rewrite the flow as a **graph**. Here, for the first time, a framework comes in: LangGraph.

## What you'll learn

- How to write a RAG's flow as a **graph**: nodes, state and conditional routing.
- Why a small model is a **bad judge**, measured.
- A pattern that works well with small models: **the LLM extracts, the code decides**.
- How to **rewrite** the question so keyword search understands Spanish.

---

## Piece 1 of 7: from a function to a graph

Until step 6, `answer()` was a top-to-bottom function: search, gate, ask the LLM. Every new step (rewrite, verify) would add an `if`, and the function would get hard to read and test.

LangGraph writes it as a **graph**:

- each **node** is a function that reads the **state** (a dictionary with the question, the chunks, etc.) and returns what changes;
- **conditional edges** decide which node comes next.

```
   [rewrite] → retrieve → gate ─┬─ nothing reaches the threshold ───────→ refuse
                                └─ verify ─┬─ a name is missing ────────→ refuse
                                           └─ otherwise → answer with citations
```

`rewrite` only runs in `keyword` and `hybrid` modes (piece 6).

Why LangGraph only now? Because until now the flow was a straight line and didn't need it ([ADR-0003](../../docs/adr/0003-own-seams-no-langchain-before-step-7.md)). Now it has branches.

## Piece 2 of 7: the check that didn't work

Step 5 called for a check after the search. The obvious idea is to ask the LLM: "does this CONTEXT answer the QUESTION? Reply YES or NO".

We tried it with `qwen2.5:3b` on 6 questions with known answers, with three different prompts:

| Question | Expected | Prompt A | Prompt B | Prompt C |
|---|:-:|:-:|:-:|:-:|
| How much did Project Lumen speed up reconciliation? | YES | ✓ | ✓ | ✗ |
| Has she used Kubernetes in production? | YES | ✗ | ✗ | ✗ |
| Has she worked with JavaScript? | NO | ✓ | ✓ | ✓ |
| ¿Trabajó con Azure? | NO | ✓ | ✓ | ✓ |
| ¿Dónde trabaja actualmente y qué rol tiene? | YES | ✗ | ✗ | ✗ |
| What is her tech stack? | YES | ✓ | ✓ | ✓ |

When in doubt, the model says NO. As a checker, it would refuse questions that have an answer. **A 3B model is a bad judge.**

## Piece 3 of 7: the LLM extracts

The same model is good at a smaller task: **extracting** the specific name the question asks about.

| Question | The LLM extracts |
|---|---|
| Has she worked with JavaScript? | `JavaScript` |
| ¿Trabajó con Azure? | `Azure` |
| ¿Usó Kubernetes? | `Kubernetes` |
| What is her tech stack? | `NONE` |
| ¿Dónde estudió? | `NONE` |

`NONE` means "this question doesn't name anything specific".

## Piece 4 of 7: the code decides

Then **the code** checks whether that name appears in the chunks that passed the gate:

- whole word: "Java" does **not** count as "JavaScript";
- ignoring case and accents.

| Result | What it does |
|---|---|
| The name is in the context | Goes on and answers. |
| The name is **not** there | Refuses, without writing an answer. |
| `NONE` (general question) | Goes on: step 4's prompt decides. |

If the question names several things ("Did she use Kafka and Flink?"), one being there is enough: the answer can be partial ("Kafka yes; nothing about Flink").

It's the signal we found in step 6 ("none of the question's words is in the CV"), but now it works in **any** store and mode, pgvector included, and with Spanish questions, because the extractor writes names in English ([ADR-0011](../../docs/adr/0011-verify-by-extracting-names-not-by-judging.md)).

> **The pattern:** don't ask a small model to judge. Ask it to extract something concrete, and do the comparison in code, which doesn't make mistakes or get talked into anything.

## Piece 5 of 7: when the extractor replies with anything

A small model sometimes doesn't reply as asked: it writes a sentence, explains, or lists categories ("technologies"). The code (`parse_terms()`) protects itself:

- if any "name" has more than 4 words, it's chatter, not a list: everything is dropped and treated as "no names";
- it strips the quotes, asterisks and periods the model adds.

When in doubt, it **doesn't refuse**: the normal flow goes on. Losing a check is better than refusing a good question.

## Piece 6 of 7: rewriting for keyword search

BM25 doesn't translate: "¿Qué idiomas habla?" shares no words with "Spanish, English, Esperanto". In `keyword` and `hybrid` modes, the graph first asks the LLM to rewrite the question as English keywords, and that's BM25's query.

The **vector** still comes from the original question. That way the threshold still holds, because it was calibrated with questions, not keywords. In `vector` mode there's nothing to rewrite and the node doesn't run.

## Piece 7 of 7: same contract, another engine

There are now two **engines**, two ways to turn a question into an answer:

- **pipeline**: the fixed chain from steps 3 to 6, `answer()` in `rag.py`. Always the same steps, in the same order.
- **graph**: this step's graph, `answer_with_graph()` in `graph.py`, with detours (rewrite, verify).

`answer_with_graph()` takes the same arguments and returns the same `Answer` as `answer()`. So the chat, the eval and the API don't know which one they're using:

```bash
ENGINE=graph            # in .env; pipeline is the default
```

The pipeline stays as lessons 3 to 6 wrote it.

| File | What it does |
|------|--------------|
| `src/talk_to_my_cv/graph.py` | The `reformulate`, `retrieve`, `verify`, `generate` and `refuse` nodes; `parse_terms()`, `mentions()` and `answer_with_graph()`. |
| `src/talk_to_my_cv/engines.py` | `ENGINES`: `pipeline` or `graph`. |
| `src/talk_to_my_cv/rag.py` | The pipeline, unchanged. `Answer` gains `verified` and `query`. |

The unit tests try every path of the graph with a `ScriptedChatModel`, a fake LLM that replies whatever you script, in order.

---

## Check that it works

```bash
make check-07
ENGINE=graph make ask DEBUG=1 Q="Has she worked with JavaScript?"
ENGINE=graph make ask DEBUG=1 Q="Has she used Kubernetes in production?"
make eval ENGINE=graph                                   # ~1.5 min on a CPU
make eval ENGINE=graph STORE=opensearch MODE=keyword     # ~2 min
```

With `DEBUG=1` you see the rewritten query (if any) and whether the question's names were in the context.

## The results

The same 20 questions, threshold 0.42:

| Store · mode | Engine | hit@5 | MRR | refusal acc. | answer acc. | Time |
|---|---|---:|---:|---:|---:|---:|
| pgvector · vector | pipeline | 1.00 | 0.82 | 0.88 | 0.82 | ~1:30 |
| pgvector · vector | **graph** | 1.00 | 0.82 | 0.88 | 0.82 | 1:35 |
| opensearch · hybrid | pipeline | 1.00 | 0.86 | 0.88 | 0.82 | — |
| opensearch · hybrid | **graph** | 1.00 | 0.86 | 0.88 | 0.82 | 2:02 |
| opensearch · keyword | pipeline | 0.64 | 0.52 | 0.71 | 0.71 | — |
| opensearch · keyword | **graph** | **0.82** | **0.77** | **0.82** | **0.76** | 1:55 |

The traps:

| Trap | pipeline | graph |
|---|:-:|:-:|
| JavaScript (must refuse) | ✗ says "No" | **✓ refuses** |
| CRM / HubSpot (must answer) | ✗ | ✗ |
| Kubernetes (must say "no") | ✓ | ✓ |

What to look at:

1. **JavaScript is fixed in every store and mode.** The extractor pulls `JavaScript`, the code doesn't find it and refuses.
2. **Azure is now refused by a rule, not by luck.** Before, the LLM refused it when it felt like it; now the code does, always the same way.
3. **The scored questions' metrics don't change.** The ones that fail, fail for other reasons: in `degree` the chunk with the answer doesn't pass the gate (0.41); in `team-size` the only chunk that passes is `Contact`; `talk` translates the talk's title (step 5). **Verifying can't add what search didn't bring.**
4. **Rewriting rescues keyword search:** hit@5 goes from 0.64 to 0.82, because Spanish questions reach BM25 in English.
5. **It's cheap.** Extracting a name produces very few words: the graph takes almost the same time as the pipeline.

**CRM is still unfixed,** and now it's refused on purpose: the extractor pulls `CRM` and the CV never names it. The fix is still "HubSpot (CRM)".

**The ≥ 0.9 target is still missed (0.88).** The two remaining errors are extra refusals, and in both the right chunk doesn't reach the threshold. Lowering the threshold now is tempting, but it would be calibrated on the same 20 questions.

## Play with it

1. **Try the judge.** In `graph.py`, change `verify` to ask "does the CONTEXT answer the QUESTION? YES or NO" and use the reply directly. Run `make eval ENGINE=graph`. How many good questions does it refuse?
2. **Lower the threshold.** Try `make eval ENGINE=graph THRESHOLD=0.40`. Are `team-size` and `degree` saved? Which unanswerable questions get through now? Remember overfitting.
3. **Fool the extractor.** "Did she use K8s?", "Did she code in JS?". What does it extract? Does it refuse even though the CV says "Kubernetes"?

## Known limitations

- **Synonyms and acronyms:** "K8s" doesn't find "Kubernetes", and "CRM" doesn't find "HubSpot". The check is as literal as the CV.
- **Questions without names:** "How much does she charge?" names nothing, so the check can't catch it. Those depend on the gate and the prompt.
- **One more LLM call** per question that passes the gate (two in `keyword` and `hybrid`).

---

## FAQ

<details>
<summary><b>If the CV mentions "Mark" in another context, does the check let it through?</b></summary>

Yes. The check only verifies that the name **appears** in the retrieved chunks, not that it refers to the same thing. If you ask about "the prophet Mark" and "John Mark" appears in a piece, it passes, and the answer will be about that Mark. It's a cheap, literal check, not understanding.
</details>

<details>
<summary><b>Would the YES/NO judge work with a big model?</b></summary>

Probably much better: big models judge fairly well. But you'd have to measure it with the eval, like we did here. And the "extract + compare in code" pattern is still cheaper and more repeatable.
</details>

---

## ✋ Review

**1. Why go from a function to a graph?**

<details><summary>Show answer</summary>

Because the flow now has branches (refuse at the gate, refuse at the check, answer). With a graph, each step is a node tested on its own, and the routing is explicit instead of buried in `if`s.
</details>

**2. What went wrong with the YES/NO judge?**

<details><summary>Show answer</summary>

When in doubt, `qwen2.5:3b` says NO: it refused answerable questions (Kubernetes, where she works). A small model is a bad judge.
</details>

**3. What does "the LLM extracts, the code decides" mean?**

<details><summary>Show answer</summary>

Give the model a small, concrete task (pull the name out of the question) and make the decision with deterministic code (is that name in the chunks?). Code doesn't make mistakes or get talked into anything.
</details>

**4. 🧪 Try it:** `ENGINE=graph make ask DEBUG=1 Q="Has she worked with JavaScript?"`. What do you expect in the debug output?

<details><summary>Show answer</summary>

`named terms in the context: NO → refuse` and the fixed refusal. The extractor pulls "JavaScript", and no chunk contains it as a whole word ("Java" doesn't count).
</details>

**5. Why does the vector come from the original question and not the rewritten one?**

<details><summary>Show answer</summary>

Because the threshold was calibrated with questions, not keyword lists. If the vector came from the rewrite, the scores would change and 0.42 would stop holding.
</details>

---

[← Step 6](../06-hybrid-search/README.md) · [Index](../../README.md) · [Next: Step 8, API and web →](../08-api-and-web/README.md)
