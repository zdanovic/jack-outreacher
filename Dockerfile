FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default log level for the orchestrator; can be overridden.
ENV ORCHESTRATOR_LOG_LEVEL=INFO

CMD ["python", "-m", "src.app.runner"]

