FROM python:3.13-slim AS build
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ARG SWAGGER_UI_VERSION=5.32.12
RUN mkdir -p /opt/swagger-ui \
    && python -c "import urllib.request as u; [u.urlretrieve('https://cdn.jsdelivr.net/npm/swagger-ui-dist@${SWAGGER_UI_VERSION}/' + f, '/opt/swagger-ui/' + f) for f in ('swagger-ui-bundle.js', 'swagger-ui.css', 'favicon-32x32.png')]"
ENV SWAGGER_UI_DIR=/opt/swagger-ui

FROM build AS dev
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt

FROM python:3.13-slim
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY --from=build /opt/swagger-ui /opt/swagger-ui
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SWAGGER_UI_DIR=/opt/swagger-ui
COPY app ./app
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
