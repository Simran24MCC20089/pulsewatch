FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PULSEWATCH_ENV=production \
    PORT=5000

WORKDIR /app

RUN useradd --create-home --shell /bin/bash pulsewatch

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py wsgi.py config.py extensions.py ./
COPY models ./models
COPY routes ./routes
COPY services ./services
COPY templates ./templates
COPY static ./static
COPY scripts ./scripts

RUN mkdir -p /app/instance && chown -R pulsewatch:pulsewatch /app

USER pulsewatch

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health')"

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "60", "wsgi:app"]
