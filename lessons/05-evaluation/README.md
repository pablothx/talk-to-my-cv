# Step 5: Evaluation

🇪🇸 [Leer en español](README.es.md)

Until now we tested "by hand": three questions, looks like it works. In this step we measure the chat with **numbers**, over 20 questions, and use those numbers to choose the threshold. That's what separates an experiment from a system you can trust.

## What you'll learn

- How to measure a RAG with numbers instead of "I tried three questions and it worked".
- What **hit@k**, **MRR**, **refusal accuracy** and **answer accuracy** measure.
- How to calibrate the threshold with data, and why the best threshold "on paper" isn't the best in practice.
- What **overfitting** is and why our numbers are optimistic.

---

## Piece 1: why measure

An LLM isn't deterministic, and every change (the prompt, the threshold, the model, how the CV is cut) can fix one question and break another. Without a measurement:

- you don't know whether a change helped or hurt;
- you're left with the last impression ("it worked yesterday");
- you can't compare two options with arguments.

An **eval** is a fixed exam: always the same questions, with what's expected from each one.

## Piece 2: the questions

`eval/questions.yaml` has 20 questions about Valentina, 10 in English and 10 in Spanish. There are four types:

| Type | How many | What's expected |
|------|---------:|-----------------|
| `answerable` | 7 | That it answers, cites the right section and includes the key facts. |
| `planted` | 5 | The same, with facts impossible to guess ("14 minutes", "Golden Pigeon"). Proves the answer comes from the document and not from the model's memory. |
| `negation` | 1 | That it answers "no", citing the source. Neither refuse nor affirm. |
| `unanswerable` | 7 | That it refuses. Includes off-topic, private data and prompt injection. |

A question looks like this:

```yaml
- id: planted-lumen
  type: planted
  lang: en
  question: How much did Project Lumen speed up reconciliation?
  expected_sources:
    - file: experience/northwind-payments.md
      section: Senior Backend Engineer > Project Lumen
  expected_answer: From 9 hours to 14 minutes.
  must_contain: ["14 minutes"]
```

What each field is:

| Field | What it is | Does the code use it? |
|---|---|---|
| `id` | A short name to find it in the results. | Only for display. |
| `type` | One of the four types above. Decides whether it must answer or refuse. | Yes |
| `lang` | The question's language: `es` or `en`. | Yes, with `check_language`. |
| `question` | The question, exactly as the chat gets it. | Yes |
| `expected_sources` | The file and section holding the answer, exactly as the chunker builds them. | Yes: for hit@5 and MRR. |
| `expected_answer` | The right answer, in words. | **No.** It's for a person to read. |
| `must_contain` | The key facts that must appear in the answer. All of them, case-insensitive. | Yes: for answer accuracy. |
| `check_language` | If `true`, the answer must be in the `lang` language. 3 questions have it. | Yes |
| `forbid_unsupported_no` | If `true`, a "no" is a hallucination: the CV says nothing, so only a refusal is right. Azure and JavaScript have it. | Yes |
| `trap` | Marks a deliberate trap (piece 3). | Yes: reported apart. |

Why `must_contain` and not compare against `expected_answer`? Because the LLM words it differently every time: "from 9 hours to 14 minutes" and "cut it to 14 minutes" are both right. Comparing the whole text would always fail. We only require the facts that can't be guessed.

## Piece 3: the traps

Three questions are marked as **traps**, the ones we've been chasing:

- **JavaScript:** the CV doesn't mention it. The right reply is the refusal; a "No" is a hallucination.
- **CRM:** the CV says "HubSpot", never "CRM". Search doesn't find it.
- **Kubernetes:** the CV says she did *not* use it in production. The right reply is "no", with a citation.

They fail on purpose with vector search, so they're reported apart and don't count toward the targets. Steps 6 and 7 show whether they get fixed.

A test validates the YAML on every push: minimums per type, both languages, and that every expected source really exists in the chunks. If someone changes a CV heading and breaks a question, they find out.

## Piece 4: the search metrics

Two metrics measure **only the search**, without the LLM, over the answerable questions:

**hit@5** (read "hit at five"): a *hit* is a success, and *@5* means "looking at the first 5". It asks: is the right section among the 5 retrieved chunks? It's yes or no per question, averaged. 1.00 = it was always there. With hit@1 the question would be "did it come first?".

**MRR** (*Mean Reciprocal Rank*): the *rank* is the **position** where the right chunk came, *reciprocal* is its inverse (1 divided by the position) and *mean* is the average over all questions. It asks: how high did it come?

| Position of the right chunk | Worth |
|---|---:|
| 1st | 1 |
| 2nd | 0.5 |
| 3rd | 0.33 |
| missing | 0 |

It's averaged. An MRR of 0.82 means the right one is usually first, sometimes second.

An example with three questions:

| Question | Position of the right one | hit@5 | 1 / position |
|---|---:|:-:|---:|
| Lumen | 1st | ✅ | 1.00 |
| Stack | 2nd | ✅ | 0.50 |
| Talk | 4th | ✅ | 0.25 |
| **Result** | | **3/3 = 1.00** | **(1 + 0.5 + 0.25) / 3 = 0.58** |

hit@5 says "it always found it"; MRR adds "but not always at the top".

We didn't invent them: they're classic *information retrieval* metrics (the field behind search engines). MRR comes from the TREC question-answering competitions of the late '90s; hit@k is also called *hit rate*, *recall@k* or *top-k accuracy*. RAG frameworks like LlamaIndex ship them out of the box. Only the implementation is ours.

## Piece 5: the whole-system metrics

Two metrics measure **everything**, with the LLM, over the 17 questions that aren't traps (the 3 traps are reported apart):

**refusal accuracy:** did it refuse when it should, and answer when it should? An extra refusal and an extra answer both count as errors.

**answer accuracy:** is the answer fully right? It doesn't refuse if there was an answer, says "no" for the negation, includes the key facts (`must_contain`) and respects the language.

The pair matters: if search works (hit@5 = 1.00) but the system fails, the problem is after the search.

## Piece 6: calibrating the threshold, first without the LLM

`make eval-sweep` does **one search per question, without the LLM**, and tries every threshold between 0.35 and 0.65. For each one it computes how many unanswerable questions it would refuse and how many answerable ones it would let through. It takes 9 seconds.

![Threshold sweep](../../eval/results/threshold-sweep_bge-m3.png)

If the two curves separated cleanly, there would be a perfect threshold. They don't: some answerable questions score **below** unanswerable ones.

| Question | Top-1 | Has an answer? |
|----------|------:|:--------------:|
| ¿Trabajó con Azure? | 0.483 | no |
| ¿Dónde trabaja actualmente y qué rol tiene? | 0.466 | yes |
| ¿Cuánto cobra por mes? | 0.444 | no |
| How big is the team she leads? | 0.431 | yes |
| What did she study? | 0.414 | yes |

No number separates the "yes" from the "no".

## Piece 7: the best on paper isn't the best

Looking only at the gate, the best threshold is **0.49**: it refuses every unanswerable question, but also 3 that had an answer. We ran the full eval, with the LLM, on both candidates:

| Threshold | refusal accuracy | answer accuracy | hit@5 | MRR |
|---|---:|---:|---:|---:|
| 0.49 (best "gate only") | 0.82 | 0.76 | 1.00 | 0.82 |
| **0.42** | **0.88** | **0.82** | 1.00 | 0.82 |

**0.42 is better,** because the gate isn't the only thing that refuses: at 0.42, "¿Cuánto cobra?" and "¿Trabajó con Azure?" pass the gate, and **the LLM refuses them correctly**. At 0.49, the gate refuses good questions the LLM never gets to see.

> **An extra refusal can't be undone; an extra answer can still be refused by the LLM.**

That's why the sweep only **proposes** candidates and the full eval **decides** ([ADR-0009](../../docs/adr/0009-top1-gate-does-not-separate-alone.md)). We kept `relevance_threshold: 0.42`.

## Piece 8: we missed the target, and it's fine to say so

The target was refusal accuracy ≥ 0.9. We got **0.88**.

We won't "fix" it by tweaking the CV or the prompt until it passes, because that would be cheating on the exam (piece 9). Step 7 adds a check after the search.

## Piece 9: overfitting

We calibrated the threshold **with the same 20 questions** we then report results on. That's called **overfitting**: we chose what works best on *these* questions, and nothing guarantees it works the same on new ones.

It's like studying with the solved exam in hand: you do well on that exam, not necessarily on another.

With 20 questions, moving a single one shifts the metrics by 5%. That's why 0.88 is an **optimistic** number. The right practice is to split the questions into two groups: one to calibrate and one, never looked at, to report. 20 isn't enough to split; 100 is.

## Piece 10: where results go

Every run writes two files to `eval/results/`, and **they're committed**:

```
eval/results/2026-11-17_pgvector_vector_bge-m3.md     ← to read
eval/results/2026-11-17_pgvector_vector_bge-m3.json   ← to compare with code
```

The name gives the date, store, mode and model. That keeps the history: what changed and how much it moved the numbers. The raw output (every full answer) goes to `raw/`, which isn't committed.

The eval always runs against the example CV, in its own Postgres schema (`eval`), whatever your `KB_DIR`: the questions are about Valentina, not about you.

| File | What it does |
|------|--------------|
| `src/talk_to_my_cv/evaluation.py` | Metrics, `grade()` (each question's mark), `run_eval()`, reports and `sweep()`. |
| `src/talk_to_my_cv/sweep_plot.py` | The sweep chart. |
| `eval/questions.yaml` | The 20 questions, each trap explained in a comment. |

---

## Check that it works

```bash
make check-05
make eval-sweep                      # 9 s, no LLM
make eval                            # ~1.5 min with qwen2.5:3b on a CPU
make eval THRESHOLD=0.49             # another candidate
make eval MODE=hybrid                # pgvector doesn't support it: "skipped"
```

### What was hard

**1. A bug only the eval could find.** "¿Dónde trabaja actualmente?" ("Where does she work now?") failed with "her workplace isn't specified". The chunk doesn't contain the word "Northwind": the company is only in the document's title, which went into the **embedded** text but not into the text the **LLM** got. Search found it and the LLM couldn't read it. Now the LLM gets the same as the embedding saw. No earlier test would have caught it.

**2. The language instruction translates proper names.** "¿Dio alguna charla?" ("Has she given a talk?") answered with the talk "Tu libro de transacciones es un flujo". The real title is "Your ledger is a stream". It's a side effect of step 4's language instruction. **We don't fix it on purpose**: tuning the prompt while looking at this question would be overfitting.

**3. The grader makes mistakes too.** For JavaScript, the model answered "No, the CONTEXT does not mention any experience with JavaScript.". It's wrong (it isn't the fixed refusal), but our rule classifies it as a hallucination, and it isn't: it admits it doesn't know. A rule-based grader has limits.

**4. One run isn't enough.** Ollama on a CPU isn't deterministic (step 4). Before trusting a small difference between two runs, repeat it.

## Play with it

1. **Try overfitting yourself.** Write 5 new questions about Valentina in `eval/questions.yaml` (3 answerable and 2 not), without looking at the scores first. Run `make eval-sweep` and `make eval`. Do the threshold and the metrics hold?
2. **Fix the CRM trap.** Change "HubSpot" to "HubSpot (CRM)" in `kb.example/experience/northwind-payments.md`, re-ingest and run the eval. Is it cheating? Yes, if you do it looking at the question; no, if it's a general rule for writing CVs ("Tool (category)").
3. **Try another model.** Change `LLM_MODEL` (for example `qwen2.5:7b`, if your RAM allows) and compare the summaries in `eval/results/`.

---

## FAQ

<details>
<summary><b>Can I evaluate with my own CV?</b></summary>

Today the eval always runs on the example CV, because the questions are about Valentina. For yours, you'd write your own questions file (with sections that exist in your chunks) and point the eval at your `kb/`. It's the best way to calibrate the threshold for your CV.
</details>

<details>
<summary><b>Why not use another LLM as a judge of the answers?</b></summary>

You can, and it's common in the industry ("LLM-as-judge"). But with a 3B model, the judge makes many mistakes (we measured it in step 7). Fixed rules (`must_contain`, the exact refusal, the language) are more limited but repeatable. With a big cloud model, a judge would be worth it.
</details>

---

## ✋ Review

**1. hit@5 = 1.00 and answer accuracy = 0.82. Where are the errors?**

<details><summary>Show answer</summary>

After the search: the right chunk was always among the 5, so either the gate (refusing too much) or the LLM (answering wrong with good context) fails.
</details>

**2. The right chunk is second for one question and first for another. What's the MRR of those two?**

<details><summary>Show answer</summary>

(0.5 + 1) / 2 = 0.75.
</details>

**3. Why did 0.42 win if the sweep said 0.49 was best?**

<details><summary>Show answer</summary>

Because the sweep only looks at the gate, and the LLM also refuses. At 0.42 some unanswerable questions get through, but the LLM refuses them correctly; at 0.49 you lose good questions nobody can recover.
</details>

**4. What's overfitting, in one sentence?**

<details><summary>Show answer</summary>

Choosing what works best on the same questions you then measure with: the numbers come out optimistic and nothing guarantees they hold for new questions.
</details>

**5. 🧪 Try it:** run `make eval-sweep` and open `eval/results/threshold-sweep_bge-m3.png`. Do you see a threshold that separates perfectly?

<details><summary>Show answer</summary>

No: the curves overlap. Some answerable questions score lower than unanswerable ones. No threshold alone separates them.
</details>

---

[← Step 4](../04-citations-threshold/README.md) · [Index](../../README.md) · [Next: Step 6, hybrid search →](../06-hybrid-search/README.md)
