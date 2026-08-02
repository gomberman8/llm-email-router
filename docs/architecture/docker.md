# Docker: startup order, healthchecks, and GPU

## Startup order and gating

```
ollama (healthcheck: ollama list)
  └── ollama-init (service_completed_successfully)
        └── api (healthcheck: HTTP /health)
mailpit (healthcheck: /mailpit readyz)
  └── api
```

`api` starts only after `ollama-init` completes successfully and `mailpit` is
healthy. `ollama-init` issues a model pull over HTTP and exits when it finishes,
so the weights are guaranteed to be present before the API accepts traffic.

Gating alone is not enough, which is why every command in this repository uses
`docker compose up -d --wait`. Plain `up -d` returns once the containers have
*started*, not once they are *healthy*, and the API still needs a few seconds to
warm the model, so a request sent in that window is refused. `--wait` blocks on the
healthchecks, so the command returns when the stack can actually serve.

The Ollama healthcheck uses `ollama list` instead of HTTP because the image does
not include curl. The Mailpit healthcheck uses the built-in `/mailpit readyz`
command.

## Model weight volume

`qwen3:4b-instruct` weights (~2.5 GB) are stored in the named volume
`ollama-models`. The first start downloads the model; afterwards a warm restart
takes ~7 s. Measured cold start on Fedora 43 x86_64, from a clean clone with the
images removed and no `.env` file: **57.7 s**.

## SELinux labels on bind mounts

Bind mounts carry the `:z` suffix. Without it, on Fedora, RHEL and CentOS with
SELinux in enforcing mode the container is denied access to the mounted file:
`ollama-init` exits with code 2 and `api` never starts. The whole stack fails on
an entire family of distributions while looking fine on macOS.

`:z` is safe everywhere: Docker ignores SELinux labels on systems where SELinux is
not active. `:Z` (uppercase) is deliberately avoided, since it applies a private
label and the `tests` service mounts the whole repository.

## Verified platforms

| Platform | Inference | Time per request |
|---|---|---|
| macOS arm64 (Apple Silicon) | CPU | 4.5-5.6 s |
| Fedora 43 x86_64 | CPU | 3.74-3.98 s |
| Fedora 43 x86_64 + AMD RX 9070 XT | ROCm | 0.73-0.77 s |

## Ollama port not exposed on the host

Port 11434 is not mapped in `docker-compose.yml`. Ollama is reachable only
inside the Docker network (by the service name `ollama`). This is an intentional
decision: exposing the port would open the model API without any authentication.

As a result, `eval/` is run via:

```bash
docker compose cp eval api:/app/
docker compose exec -T api python -m eval.run_eval
```

## Dev stage and the tests service

The `Dockerfile` contains a `dev` stage (built on top of `build`) that adds
`requirements-dev.txt` (pytest, pytest-asyncio, ruff) to the venv without
touching the production image.

`docker-compose.yml` defines a `tests` service with `profiles: [test]` so it
does not start on `docker compose up -d`. The service bind-mounts the repository
into the container, making `tests/` and `eval/` available despite `.dockerignore`.

```bash
docker compose run --rm tests                   # unit tests
docker compose run --rm tests pytest -m llm -q  # e2e
```

## GPU overrides

### AMD ROCm (verified on hardware)

```bash
docker compose -f docker-compose.yml -f docker-compose.rocm.yml up -d --wait
```

`docker-compose.rocm.yml` replaces the Ollama image with `ollama/ollama:0.32.5-rocm`
(same pinned version) and passes devices `/dev/kfd` and `/dev/dri` with
`security_opt: seccomp:unconfined`.

`ollama-init` stays on the CPU image, since it only issues a pull over HTTP and
needs no GPU.

Verified on an AMD Radeon RX 9070 XT (RDNA4, `gfx1201`) under Fedora 43: Ollama
detected the GPU natively, offloaded 37/37 layers, and `ollama ps` reported 100%
GPU against 15.9 GiB of VRAM. Request latency dropped from 3.74-3.98 s on CPU to
0.73-0.77 s on the same machine.

`HSA_OVERRIDE_GFX_VERSION` was **not** required, because this Ollama build
recognises `gfx1201` on its own. It remains an escape hatch if detection ever fails on a
different card; setting it unnecessarily can break a working configuration.

No `group_add` is present, and that is deliberate. An earlier revision listed the
`video` and `render` groups, which broke twice: Docker resolves group names inside
the container, and the Ollama image has no `render` group, while hardcoding numeric
GIDs would pin the file to one distribution. Testing with and without the section
on real hardware produced identical results: `/dev/kfd` and `/dev/dri/renderD*`
are mode `crw-rw-rw-` and the container runs as root, so group membership never
mattered.

### NVIDIA CUDA (compose syntax validated, never run on GPU hardware)

```bash
docker compose -f docker-compose.yml -f docker-compose.cuda.yml up -d --wait
```

`docker-compose.cuda.yml` adds `deploy.resources.reservations.devices` with
`driver: nvidia`. Requires `nvidia-container-toolkit` installed on the host.
The Ollama image is unchanged (`ollama/ollama:0.32.5`); it handles NVIDIA
without a separate image variant.

**The CUDA variant was not run on physical GPU hardware and is not guaranteed
to work.**
