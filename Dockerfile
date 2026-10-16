FROM python:3.12-slim

# stamped by CI so the page footer shows which build is running
ARG GIT_SHA=dev
ARG BUILD_TIME=
ENV APP_VERSION=$GIT_SHA \
    APP_BUILT=$BUILD_TIME \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLANTCAL_DB=/data/plantcal.db

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

RUN useradd --system --uid 1000 garden && mkdir -p /data && chown garden /data
USER garden
VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/settings', timeout=4)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
