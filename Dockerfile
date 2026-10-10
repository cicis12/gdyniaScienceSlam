FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code explicitly. Credentials, tests, and uploads stay outside the image.
COPY *.py ./
COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY routers/ ./routers/
COPY templates/ ./templates/
COPY static/ ./static/
COPY scripts/deploy_support.py ./scripts/deploy_support.py

RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir -p static/uploads/team static/uploads/gallery static/uploads/about \
       static/uploads/partners static/uploads/home static/uploads/imports \
       uploads/documents uploads/config-previews uploads/filmikuczestnik \
       uploads/zgodauczestnik uploads/zgodawidz uploads/zgodawolontariusz \
    && chown -R app:app static/uploads uploads

USER app
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
