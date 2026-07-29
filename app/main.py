from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(
    title="LLM Email Router",
    description="Routes free-form messages to the right department via an LLM agent.",
    version="1.0.0",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
    redoc_url=None,
)


@app.get("/health", tags=["ops"])
def health_check() -> JSONResponse:
    """Liveness. Says nothing about dependencies - see /ready for those."""
    return JSONResponse(status_code=200, content={"fastapi": True})
