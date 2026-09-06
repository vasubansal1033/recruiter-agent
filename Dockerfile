FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

COPY pyproject.toml README.md ./
COPY src ./src
COPY profile ./profile

# Do not copy .env — pass keys at runtime.
RUN pip install --no-cache-dir .

EXPOSE 7860

CMD ["sh", "-c", "uvicorn recruiter_agent.server:app --host 0.0.0.0 --port ${PORT:-7860}"]
