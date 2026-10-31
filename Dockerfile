FROM python:3.14-slim@sha256:cd89c30eda26ee911a4611b18680086e0ea42e6f5f8cbe653d07fa7958c9cec8
WORKDIR /app
COPY fireplanner /app/fireplanner
COPY web /app/web
RUN useradd --uid 10001 --create-home planner && mkdir /data && chown planner:planner /data
USER planner
ENV FIRE_HOST=0.0.0.0 FIRE_PORT=8080 FIRE_DB=/data/planner.sqlite3
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health',timeout=2)"
CMD ["python", "-m", "fireplanner.server"]
