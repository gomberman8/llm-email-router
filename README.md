# LLM Email Router

Routes internal company messages to the right department via an LLM agent.
An HTTP endpoint accepts `{email, message}` in Polish; pydantic-ai + Ollama
calls a tool that sends an email to the correct address. Reply-To is set from
the HTTP request; the model cannot override it. Five target departments:
`kadry` (payroll/HR admin), `human-resources`, `help-desk`, `it`, `other`.

## Quick Start

```bash
docker compose up -d --wait
```

That is the whole setup. No `.env` file is required: every setting has a default
in both `docker-compose.yml` and `app/config.py`. Copy `.env.example` only if you
want to change something; it documents the available knobs.

`--wait` matters: without it `up -d` returns as soon as the containers start, while
the API still needs a few seconds to warm the model, and the first request would be
refused. With `--wait` the command returns when the stack is genuinely ready.

First run downloads ~2.5 GB of model weights. Measured cold start on Fedora 43
x86_64 from a clean clone with no cached images: **57.7 s**.

## Example

```bash
curl -s -X POST http://localhost:8000/api/v1/route \
  -H "Content-Type: application/json" \
  -d '{"email": "pracownik@firma.pl", "message": "Nie działa mi drukarka od rana."}'
```

Sample response:

```json
{
  "department": "help-desk@example.com",
  "reasoning": "Wiadomość została pomyślnie przekazana do działu help-desk.",
  "message_id": "<...@...>",
  "routed_by": "agent",
  "processing_time_ms": 5240
}
```

Swagger UI: http://localhost:8000/api/v1/docs  
`/health` reports whether the process is alive (no dependency checks).
`/ready` reports whether Ollama, the model and SMTP are reachable.

## Architecture

<!-- diagram placeholder -->

### Module Map


```
app/
├── main.py              FastAPI, endpoints, lifespan, exception handlers, structured logging
├── config.py            All config via pydantic-settings / env vars
├── models.py            Request / response models
├── dependencies.py      Dependency injection wiring
├── guards.py            Concurrency semaphore (MAX_CONCURRENT_RUNS)
├── ports.py             EmailSender Protocol, the architectural boundary
├── services.py          RoutingService, the use case
├── exceptions.py        EmailDeliveryError
├── agent/
│   ├── agent.py         pydantic-ai Agent, tool registration, retry and fallback
│   ├── departments.py   Department enum + scope descriptions
│   └── prompt.py        System prompt (Polish)
└── adapters/
    ├── smtp_sender.py   SmtpEmailSender (production / Mailpit)
    └── memory_sender.py InMemoryEmailSender (tests and eval)
eval/                    Evaluation harness, 35 labelled Polish messages
tests/                   19 unit tests + 1 e2e behind the llm marker
docker/                  One-shot model pull script
```

## Running Tests

No local Python required; Docker is sufficient:

```bash
docker compose run --rm tests                   # unit tests (19, ~0.6 s)
docker compose run --rm tests pytest -m llm -q  # e2e, requires running stack
```

Local (venv needed only for tests and eval):

```bash
python3.13 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q && .venv/bin/pytest -m llm -q
```

## Evaluation

```bash
docker compose cp eval api:/app/
docker compose exec -T api python -m eval.run_eval            # default model
docker compose exec -T api python -m eval.run_eval --model llama3.2:3b
docker compose exec -T api python -m eval.run_eval --limit 8  # first 8 cases
```

## GPU

```bash
# AMD ROCm, verified on an RX 9070 XT
docker compose -f docker-compose.yml -f docker-compose.rocm.yml up -d --wait
# NVIDIA CUDA, compose syntax validated, never run on GPU hardware
docker compose -f docker-compose.yml -f docker-compose.cuda.yml up -d --wait
```

Details: [docs/architecture/docker.md](docs/architecture/docker.md)

## Verified Platforms

| Platform | Inference | Time per request |
|---|---|---|
| macOS arm64 (Apple Silicon) | CPU | 4.5-5.6 s |
| Fedora 43 x86_64 | CPU | 3.74-3.98 s |
| Fedora 43 x86_64 + AMD RX 9070 XT | ROCm | **0.73-0.77 s** |

On the RX 9070 XT Ollama detected `gfx1201` natively and offloaded all 37 layers,
roughly a 5x speed-up over CPU on the same machine. The NVIDIA override has never
been run on real hardware; only its compose syntax is validated.

## Design Decisions

**Ports and adapters.** `EmailSender` is a Protocol (`app/ports.py`). Production uses
`SmtpEmailSender`; tests use `InMemoryEmailSender`. Agent only calls a tool and has
no knowledge of transport.

**Mailpit over MailHog.** Actively maintained, ships `/mailpit readyz`, no curl needed.

**No task queue.** Two concurrent requests take roughly twice as long as one (see latency
table). With `OLLAMA_NUM_PARALLEL=1` concurrency spreads the same throughput; the
bottleneck is CPU/GPU, not HTTP.

### Latency (qwen3:4b-instruct, warmed model, CPU)

| Concurrent | Wall clock | Throughput |
|---|---|---|
| 1 | 4.5 s / 5.6 s | 0.22 / 0.18 req/s |
| 2 | 9.4 s / 13.2 s | 0.21 / 0.15 req/s |

### Model Selection (35 messages: 29 tuned + 6 held-out, CPU)

| Model | Tuned | Held-out | s/msg | Fallbacks | Verdict |
|---|---|---|---|---|---|
| `qwen3:4b-instruct` | 29/29 (100%) | 6/6 (100%) | 9.2 | 0 | **selected** |
| `llama3.2:3b` | 18/29 (62%) | 3/6 (50%) | 22.8 | 4 | rejected |
| `qwen3:4b` | did not finish | n/a | >120 s (timeout) | n/a | rejected |

Caveats on these numbers: [docs/architecture/routing.md](docs/architecture/routing.md)

## Documentation

- [agent.md](docs/architecture/agent.md): tool calling, Reply-To protection, enum constraint, retry, fallback
- [routing.md](docs/architecture/routing.md): department scopes, routing rules, evaluation caveats
- [docker.md](docs/architecture/docker.md): startup order, healthchecks, GPU overrides, dev stage
- [testing.md](docs/architecture/testing.md): test layers, Docker vs local, llm marker
