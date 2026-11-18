# Bonus: llevarlo a producción en AWS

🇬🇧 [Read in English](production-on-aws.md)

El tutorial corre 100% local y gratis. Este documento muestra qué cambia si querés publicar tu chat en AWS. No es un paso con `make check`: es un mapa para decidir, con las piezas que ya tenés.

> **La idea central:** gracias a las interfaces de los pasos 0 a 2 (`Embedder`, `ChatModel`, `VectorStore`), pasar a AWS es escribir **adaptadores**, no reescribir el RAG. El corte, la verificación, las citas, la eval y la API no cambian.

## El mapa

| Local (este repo) | En AWS | Qué cambia en el código |
|---|---|---|
| Ollama + `qwen2.5:3b` (`ChatModel`) | **Amazon Bedrock**, con la API Converse (por ejemplo, un modelo chico como Claude Haiku o Amazon Nova) | Un `BedrockChatModel` nuevo, y `LLM_PROVIDER=bedrock` en `build_chat_model()`. |
| Ollama + `bge-m3` (`Embedder`) | **Bedrock**: Amazon Titan Text Embeddings V2 o Cohere Embed Multilingual | Un `BedrockEmbedder` nuevo. Otro modelo = **re-ingestar y recalibrar el umbral** (ver abajo). |
| pgvector en Docker | **Amazon Aurora PostgreSQL** o **RDS for PostgreSQL**, con la extensión `pgvector` | Nada: cambia `DATABASE_URL`. |
| OpenSearch en Docker | **Amazon OpenSearch Service** (dominio administrado) u **OpenSearch Serverless** | La autenticación: firmar los pedidos con SigV4 (`AWSV4SignerAuth` de `opensearch-py`). |
| Contenedor de la API (paso 8) | **AWS Lambda** (imagen de contenedor + Lambda Web Adapter) o **ECS Fargate** detrás de un ALB | Nada en `api.py`. |
| `.env` | Variables de entorno de Lambda/ECS; la contraseña de la base en **Secrets Manager**. Bedrock no usa keys: usa el **rol IAM**. | `load_settings()` ya lee el entorno. |
| `kb/` en tu disco | Un bucket **S3** privado y cifrado | Un `make ingest` que lea de S3, o una Lambda que ingeste cuando subís un archivo. |
| `docker compose` | **AWS CDK** (en Python, como el resto del repo) | Infraestructura nueva; el código de la app no se entera. |
| `make eval` a mano | La eval en **CI** (GitHub Actions con OIDC, sin keys) contra un ambiente de staging, antes de cada deploy | Ninguno: es el mismo comando. |

## Lo que no podés saltearte: el umbral

El umbral de relevancia (0.42) se calibró **para `bge-m3`** en el paso 5. Otro modelo de embeddings da otros scores, y el mismo umbral puede rechazar todo o dejar pasar todo.

El repo ya te cuida de dos formas:

1. **El candado del modelo** ([ADR-0005](adr/0005-chunk-identity-and-embedding-model-lock.md)): si cambiás `EMBED_MODEL` sin `make ingest REBUILD=1`, la ingesta falla en vez de mezclar vectores de dos modelos.
2. **El umbral es por modelo**: `config/models.yaml` necesita una entrada para el modelo nuevo, con su dimensión y su umbral. Sin umbral, el chat no arranca.

El orden, entonces: agregar el modelo a `config/models.yaml`, `make ingest REBUILD=1`, `make eval-sweep` para proponer candidatos, `make eval THRESHOLD=...` para elegir ([ADR-0009](adr/0009-top1-gate-does-not-separate-alone.md)). Con las mismas advertencias de sobreajuste.

## La migración, de a un paso

Cada paso se puede verificar con `make eval` antes de dar el siguiente:

1. **Bedrock desde tu máquina.** Escribí `BedrockChatModel` y `BedrockEmbedder` con TDD (los fakes y los tests de contrato ya existen). Dejá pgvector local. Recalibrá el umbral y compará la eval con la de Ollama: con un modelo más grande, ¿se arreglan `talk` (el título traducido) y el juez del paso 7?
2. **Los stores.** Aurora/RDS o OpenSearch Service, en subredes privadas. Los tests de contrato del paso 2 corren igual contra ellos.
3. **La API.** La misma imagen del paso 8, en Lambda o Fargate.
4. **CDK.** Todo lo anterior como código.
5. **La eval en CI.** Un deploy que baja `refusal_accuracy` no pasa.

## ¿Lambda o Fargate?

| | Lambda | ECS Fargate |
|---|---|---|
| Costo sin tráfico | Cero | La tarea corre siempre |
| Arranque | Arranque en frío de segundos (la imagen trae numpy, psycopg...) | Siempre caliente |
| Encaja con | Un chat personal con poco tráfico | Tráfico constante o respuestas en streaming |

Para un CV, **Lambda**. Ojo con el timeout si la ponés detrás de API Gateway: tiene un límite de integración más corto que el de Lambda. Con Bedrock las respuestas tardan segundos, no los 10 a 30 de una CPU, así que no debería ser un problema, pero medilo. Una alternativa es una Lambda Function URL detrás de CloudFront.

## Costos: qué los mueve

No ponemos precios porque cambian y dependen de la región; consultá las páginas de precios de cada servicio. Lo que importa es **qué cobra aunque nadie pregunte**:

| Pieza | Se cobra por | ¿Cobra sin tráfico? |
|---|---|---|
| Bedrock | Tokens de entrada y salida, y tokens embebidos | No |
| Lambda | Pedidos y tiempo de ejecución | No |
| Aurora Serverless v2 | Capacidad (ACU) por hora + almacenamiento | Puede pausarse a 0 ACU si lo configurás; el almacenamiento sí |
| RDS | La instancia por hora | **Sí** |
| OpenSearch Service | Las instancias del dominio por hora | **Sí** |
| OpenSearch Serverless | Capacidad (OCU) por hora | **Sí**, tiene un mínimo |
| S3, Secrets Manager | Almacenamiento y pedidos | Centavos |

**El piso del costo es el store.** Para un CV de 30 chunks, una opción que no figura en ningún diagrama de arquitectura: guardar los vectores en un JSON en S3 y cargarlos en el `InMemoryStore` del paso 2 cuando arranca la Lambda. Treinta vectores de 1024 números entran sobrados en memoria, y el costo sin tráfico es cero. Perdés la búsqueda híbrida, pero el grafo del paso 7 verifica igual en modo vector. OpenSearch tiene sentido cuando hay miles de documentos, o para aprender la arquitectura que usarías en una empresa.

**El LLM se calcula así:** cada pregunta que pasa el corte manda el contexto (5 chunks, unos pocos miles de caracteres) más el prompt. El grafo agrega una llamada corta para extraer nombres. Multiplicá por las preguntas por mes y por el precio por token del modelo que elijas. Las preguntas que el corte rechaza no llaman al LLM: el corte también ahorra plata.

## Seguridad

- **La KB son datos personales.** S3 privado con cifrado (KMS), la base cifrada, y nada de `kb/` en la imagen (el `.dockerignore` del paso 8 ya lo garantiza).
- **Sin keys.** La Lambda tiene un rol IAM con `bedrock:InvokeModel` sobre los ARN de los modelos que usa, y nada más. CI se autentica con OIDC.
- **Nada público salvo la API.** Stores en subredes privadas; OpenSearch nunca con acceso abierto (el `DISABLE_SECURITY_PLUGIN` del paso 6 es solo para tu máquina).
- **La API pública necesita freno.** Sin autenticación, cualquiera gasta tus tokens. Como mínimo, un límite de pedidos (AWS WAF con una regla por IP delante de CloudFront o API Gateway), y una alarma de presupuesto (AWS Budgets).
- **Los logs.** No guardes las preguntas completas si pueden traer datos personales de quien pregunta.
- **Las defensas del tutorial siguen.** El prompt injection no desaparece en la nube: el corte, la verificación, el rechazo fijo y el escape del HTML siguen siendo tu código. Bedrock Guardrails puede agregar un control de *contextual grounding*, que mide si la respuesta se apoya en el contexto: es el "una cita no es una garantía" del paso 4, como servicio. Si lo agregás, medilo con la eval como cualquier otro cambio.

## ¿Y Bedrock Knowledge Bases?

Bedrock Knowledge Bases hace el RAG por vos: chunking, embeddings, store y recuperación, administrados. Es una opción válida para producción. La diferencia es el control: elegir cómo cortar (por secciones, con la ruta de títulos), el corte por umbral antes del LLM, la verificación del paso 7 y los rechazos fijos son decisiones que este tutorial tomó midiendo. Con la eval del paso 5 podés comparar las dos opciones con números, que es exactamente para lo que la construiste.

## Un esqueleto de CDK

Un punto de partida, **no probado**: la API del paso 8 como Lambda, con acceso solo a Bedrock y la KB en memoria (la opción más barata de arriba).

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

`LLM_PROVIDER=bedrock` y `VECTOR_STORE=memory` todavía no existen: son los adaptadores del paso 1 de la migración. Ese es el punto: lo que falta es poco, y está detrás de interfaces que ya tienen tests.
