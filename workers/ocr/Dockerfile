FROM python:3.11-slim AS base

WORKDIR /app

# Зависимости для PyMuPDF и обработки изображений
RUN apt-get update && \
    apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .

CMD ["celery", "-A", "app.celery_app", "worker", "--loglevel=info"]
