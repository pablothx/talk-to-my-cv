# Verify by extracting names, not by asking the LLM to judge

ADR-0009 asked for an LLM verification step after retrieval. The obvious design is to ask the model "does this CONTEXT answer the QUESTION? YES or NO". We measured it with `qwen2.5:3b`, the default local model, on 6 questions whose retrieved context holds a known verdict, using three different prompts (a plain YES/NO question, a "quote the sentence or reply NONE" variant, and a "look for the key term" variant). Every variant said NO to answerable questions: "Has she used Kubernetes in production?" (a negation) and "Where does she work now?". The best of them got 4 out of 6 right. A small model is a poor judge.

The same model is a decent extractor. So verification is split in two:

1. **The LLM extracts** the specific names the question asks about ("JavaScript", "Azure", "Acme Corp, Terraform"), or `NONE` for general questions ("What did she study?").
2. **Code checks** whether any of those names appears in the chunks that passed the relevance gate: whole word, ignoring case and accents. "Java" does not match "JavaScript".

If a name is missing, the graph refuses without writing an answer. If the question names nothing specific, or the extractor's reply doesn't look like a list of names, verification passes and the answer prompt decides, as in step 4 (fail open).

## Consequences

- It generalises step 6's "no lexical match" signal (ADR-0010) to every store and mode, and it works for Spanish questions because the extractor writes names in English.
- It can't catch an unanswerable question that names nothing ("How much does she earn?"). The relevance gate and the answer prompt still handle those.
- A name the KB writes differently ("K8s" for "Kubernetes", "CRM" for "HubSpot") is refused. The fix belongs in the KB: "Tool (category)".
- The extraction prompt has few-shot examples. None of them are eval questions, to avoid tuning on the questions we report.
- It costs one more LLM call per question that passes the gate, but the reply is a few tokens: the eval took 1:35 against ~1:30 for the pipeline on a CPU.
