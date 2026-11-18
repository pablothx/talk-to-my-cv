# Bonus: taking it to production on AWS

🇪🇸 [Leer en español](produccion-en-aws.md)

The tutorial runs 100% locally and for free. This document shows what changes if you want to publish your chat on AWS. It isn't a step with a `make check`: it's a map to help you decide, using the pieces you already have.

> **The core idea:** thanks to the interfaces from steps 0 to 2 (`Embedder`, `ChatModel`, `VectorStore`), moving to AWS means writing **adapters**, not rewriting the RAG. The gate, the verification, the citations, the eval and the API don't change.

## The map

| Local (this repo) | On AWS | What changes in the code |
|---|---|---|
| Ollama + `qwen2.5:3b` (`ChatModel`) | **Amazon Bedrock**, with the Converse API (for example, a small model such as Claude Haiku or Amazon Nova) | A new `BedrockChatModel`, and `LLM_PROVIDER=bedrock` in `build_chat_model()`. |
| Ollama + `bge-m3` (`Embedder`) | **Bedrock**: Amazon Titan Text Embeddings V2 or Cohere Embed Multilingual | A new `BedrockEmbedder`. Another model = **re-ingest and recalibrate the threshold** (see below). |
| pgvector in Docker | **Amazon Aurora PostgreSQL** or **RDS for PostgreSQL**, with the `pgvector` extension | Nothing: `DATABASE_URL` changes. |
| OpenSearch in Docker | **Amazon OpenSearch Service** (managed domain) or **OpenSearch Serverless** | Authentication: sign requests with SigV4 (`AWSV4SignerAuth` from `opensearch-py`). |
| The API container (step 8) | **AWS Lambda** (container image + Lambda Web Adapter) or **ECS Fargate** behind an ALB | Nothing in `api.py`. |
| `.env` | Lambda/ECS environment variables; the database password in **Secrets Manager**. Bedrock uses no keys: it uses the **IAM role**. | `load_settings()` already reads the environment. |
| `kb/` on your disk | A private, encrypted **S3** bucket | A `make ingest` that reads from S3, or a Lambda that ingests when you upload a file. |
| `docker compose` | **AWS CDK** (in Python, like the rest of the repo) | New infrastructure; the app code doesn't notice. |
| `make eval` by hand | The eval in **CI** (GitHub Actions with OIDC, no keys) against a staging environment, before every deploy | None: it's the same command. |

## What you can't skip: the threshold

The relevance threshold (0.42) was calibrated **for `bge-m3`** in step 5. Another embedding model gives other scores, and the same threshold may refuse everything or let everything through.

The repo already protects you in two ways:

1. **The model lock** ([ADR-0005](adr/0005-chunk-identity-and-embedding-model-lock.md)): if you change `EMBED_MODEL` without `make ingest REBUILD=1`, ingestion fails instead of mixing vectors from two models.
2. **The threshold is per model**: `config/models.yaml` needs an entry for the new model, with its dimension and threshold. Without a threshold, the chat won't start.

So the order is: add the model to `config/models.yaml`, `make ingest REBUILD=1`, `make eval-sweep` to propose candidates, `make eval THRESHOLD=...` to choose ([ADR-0009](adr/0009-top1-gate-does-not-separate-alone.md)). With the same overfitting caveats.

## The migration, one step at a time

Each step can be checked with `make eval` before taking the next one:

1. **Bedrock from your machine.** Write `BedrockChatModel` and `BedrockEmbedder` test-first (the fakes and contract tests already exist). Keep pgvector local. Recalibrate the threshold and compare the eval with Ollama's: with a bigger model, do `talk` (the translated title) and step 7's judge get fixed?
2. **The stores.** Aurora/RDS or OpenSearch Service, in private subnets. Step 2's contract tests run against them unchanged.
3. **The API.** The same step 8 image, on Lambda or Fargate.
4. **CDK.** All of the above as code.
5. **The eval in CI.** A deploy that lowers `refusal_accuracy` doesn't go through.

## Lambda or Fargate?

| | Lambda | ECS Fargate |
|---|---|---|
| Cost with no traffic | Zero | The task always runs |
| Startup | A cold start of a few seconds (the image carries numpy, psycopg...) | Always warm |
| Fits | A personal chat with little traffic | Steady traffic or streaming answers |

For a CV, **Lambda**. Watch the timeout if you put it behind API Gateway: its integration limit is shorter than Lambda's. With Bedrock, answers take seconds, not the 10 to 30 of a CPU, so it shouldn't be a problem, but measure it. An alternative is a Lambda Function URL behind CloudFront.

## Costs: what drives them

We don't give prices because they change and depend on the region; check each service's pricing page. What matters is **what you pay for even when nobody asks anything**:

| Piece | Billed by | Billed with no traffic? |
|---|---|---|
| Bedrock | Input and output tokens, and embedded tokens | No |
| Lambda | Requests and execution time | No |
| Aurora Serverless v2 | Capacity (ACUs) per hour + storage | It can pause at 0 ACUs if you configure it; storage is still billed |
| RDS | The instance, per hour | **Yes** |
| OpenSearch Service | The domain's instances, per hour | **Yes** |
| OpenSearch Serverless | Capacity (OCUs) per hour | **Yes**, it has a minimum |
| S3, Secrets Manager | Storage and requests | Cents |

**The store sets the cost floor.** For a 30-chunk CV, an option you won't find in any architecture diagram: keep the vectors in a JSON file on S3 and load them into step 2's `InMemoryStore` when the Lambda starts. Thirty 1024-number vectors fit in memory with room to spare, and the cost with no traffic is zero. You lose hybrid search, but step 7's graph still verifies in vector mode. OpenSearch makes sense with thousands of documents, or to learn the architecture you'd use at a company.

**The LLM cost works like this:** every question that passes the gate sends the context (5 chunks, a few thousand characters) plus the prompt. The graph adds one short call to extract names. Multiply by the questions per month and by your model's price per token. Questions the gate refuses don't call the LLM: the gate saves money too.

## Security

- **The KB is personal data.** Private S3 with encryption (KMS), an encrypted database, and nothing from `kb/` in the image (step 8's `.dockerignore` already guarantees it).
- **No keys.** The Lambda has an IAM role with `bedrock:InvokeModel` on the ARNs of the models it uses, and nothing else. CI authenticates with OIDC.
- **Nothing public except the API.** Stores in private subnets; OpenSearch never with open access (step 6's `DISABLE_SECURITY_PLUGIN` is for your machine only).
- **A public API needs a brake.** Without authentication, anyone spends your tokens. At least, a rate limit (AWS WAF with a per-IP rule in front of CloudFront or API Gateway), and a budget alarm (AWS Budgets).
- **Logs.** Don't store full questions if they may carry the asker's personal data.
- **The tutorial's defenses still apply.** Prompt injection doesn't go away in the cloud: the gate, the verification, the fixed refusal and HTML escaping are still your code. Bedrock Guardrails can add a *contextual grounding* check, which measures whether the answer is supported by the context: it's step 4's "a citation is not a guarantee", as a service. If you add it, measure it with the eval like any other change.

## What about Bedrock Knowledge Bases?

Bedrock Knowledge Bases does the RAG for you: chunking, embeddings, store and retrieval, managed. It's a valid option for production. The difference is control: choosing how to chunk (by section, with the heading path), the threshold gate before the LLM, step 7's verification and fixed refusals are decisions this tutorial made by measuring. With step 5's eval you can compare both options with numbers, which is exactly what you built it for.

## A CDK skeleton

A starting point, **not tested**: step 8's API as a Lambda, with access to Bedrock only and the KB in memory (the cheapest option above).

```python
from aws_cdk import Duration, Stack, aws_iam as iam, aws_lambda as lambda_
from constructs import Construct


class CvChatStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        api = lambda_.DockerImageFunction(
            self,
            "Api",
            # The step 8 Dockerfile plus the Lambda Web Adapter extension:
            #   COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:<version> \
            #        /lambda-adapter /opt/extensions/lambda-adapter
            code=lambda_.DockerImageCode.from_image_asset("."),
            memory_size=1024,
            timeout=Duration.seconds(60),
            environment={"LLM_PROVIDER": "bedrock", "VECTOR_STORE": "memory"},
        )
        api.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=["arn:aws:bedrock:*::foundation-model/<your-model-ids>"],
            )
        )
        api.add_function_url(auth_type=lambda_.FunctionUrlAuthType.NONE)  # add WAF + CloudFront
```

`LLM_PROVIDER=bedrock` and `VECTOR_STORE=memory` don't exist yet: they're the adapters from step 1 of the migration. That's the point: what's missing is small, and it sits behind interfaces that already have tests.
