FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HARBORMASTER_ENV=prod \
    PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.txt README.md ./
COPY src ./src
COPY web ./web
COPY config ./config
COPY scripts ./scripts
COPY data/inbox ./data/inbox

RUN pip install --no-cache-dir -e .

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "harbormaster.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
