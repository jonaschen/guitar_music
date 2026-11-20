FROM python:3.12-slim-bookworm
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY gateway.py ./
USER 65532:65532
ENV PYTHONUNBUFFERED=1
# Hypercorn accepts cleartext HTTP/2 (h2c). Cloud Run must use --use-http2.
# One process is sufficient; ledger CAS also protects overlapping revisions.
CMD ["sh", "-c", "exec hypercorn 'gateway:create_app()' --bind 0.0.0.0:${PORT:-8080} --workers 1 --graceful-timeout 10 --keep-alive 5 --error-logfile -"]
