# Testing: layers, Docker, llm marker

## Test layers

```
tests/
├── conftest.py        ALLOW_MODEL_REQUESTS=False, saturated_semaphore fixture
├── helpers.py         has_tool_return(), make_tool_caller()
├── test_agent.py      5 tests: tool calling, Reply-To, enum schema, fallback, retry
├── test_http.py      13 tests: validation, semaphore, error mapping, Swagger, /ready
├── test_smtp.py       1 test: OSError wrapped as EmailDeliveryError
└── test_e2e.py        1 test behind the llm marker: full path via HTTP + Mailpit
```

Plain `pytest` runs 19 unit tests in ~0.6 s with no external dependencies
(no Ollama, no Mailpit). This is verified by running with containers stopped.

Three properties get an explicit assertion rather than being inferred from a mail
arriving, because each of them can pass for the wrong reason:

- a `ToolCallPart` for `send_to_department` really appears in the exchange
  (`capture_run_messages`), so the agent sends the mail, not the application;
- the tool's JSON schema restricts `department` to exactly the five enum values,
  so the model cannot invent a destination;
- the e2e test reads Mailpit's **raw** RFC 2822 source, so `To` and `Reply-To` are
  checked on the wire rather than in a convenience JSON field.

## Running tests

### In Docker (no local Python required)

```bash
docker compose run --rm tests                   # unit tests
docker compose run --rm tests pytest -m llm -q  # e2e, requires running stack
```

The `tests` service is in `profiles: [test]` and does not start on
`docker compose up -d`. `docker compose run` ignores profiles and always runs
the specified service.

### Locally (for development)

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q          # unit tests
.venv/bin/pytest -m llm -q  # e2e
```

## The llm marker

Tests marked `@pytest.mark.llm` are deselected by the default
`addopts = "-m 'not llm'"` in `pyproject.toml`.

The e2e test fetches the raw email source from the Mailpit API
(`/api/v1/message/{ID}/raw`) and asserts the `To` and `Reply-To` headers
directly from the RFC 2822 message, not from the JSON field.

The test reads endpoint URLs from environment variables with localhost defaults,
so local and Docker runs both work without code changes:

```
ROUTER_URL    default: http://localhost:8000/api/v1/route  -> http://api:8000/...  in Docker
MAILPIT_BASE  default: http://localhost:8025               -> http://mailpit:8025  in Docker
```

## Mutation testing

Mutation testing means deliberately breaking the code and checking whether the
tests catch it, since line coverage alone doesn't prove a test asserts anything.
Applied to a handful of critical paths, not the whole codebase.

Most useful result: the `/ready` check for whether the configured model is
present in Ollama was replaced with `if False:`, and no test caught it. That
revealed an untested branch, closed by
`test_ready_returns_503_when_configured_model_not_in_ollama`.

Two mutations that were caught as expected: `reply_to` taken from `subject`
instead of `ctx.deps.sender_email` (`test_reply_to_is_sender_email_regardless_of_model_output`),
and `docs_url` changed to `/docs` (two Swagger location tests).
