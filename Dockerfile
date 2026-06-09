FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/data/ikt_portal.db

WORKDIR /app

RUN addgroup --system iktportal \
    && adduser --system --ingroup iktportal iktportal \
    && mkdir -p /data \
    && chown -R iktportal:iktportal /app /data

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt gunicorn

COPY --chown=iktportal:iktportal app.py ./
COPY --chown=iktportal:iktportal templates ./templates
COPY --chown=iktportal:iktportal static ./static

USER iktportal

EXPOSE 5000
VOLUME ["/data"]

CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:5000", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
