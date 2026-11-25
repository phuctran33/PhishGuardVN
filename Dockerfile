FROM debian:bookworm-slim AS web

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git unzip xz-utils \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch 3.47.9 --filter=blob:none \
      https://github.com/flutter/flutter.git /opt/flutter \
    && test "$(git -C /opt/flutter rev-parse HEAD)" = c197ca5199e9ee5661e865596c9c07294dfab51c

ENV PATH="/opt/flutter/bin:$PATH" CI=true
WORKDIR /web
COPY apps/web/pubspec.yaml apps/web/pubspec.lock ./
RUN flutter pub get --enforce-lockfile

COPY apps/web/lib ./lib
COPY apps/web/assets ./assets
COPY apps/web/web ./web
# An empty build-time base makes browser requests relative to the demo origin.
RUN flutter build web --release --no-pub --no-web-resources-cdn --dart-define=API_BASE_URL=

FROM python:3.11.17-slim-bookworm@sha256:f06d01d4ba3f8ad5af45a3ec87df19c1d317d8e8961edc0fabda61811af6f7cf

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PORT=10000
WORKDIR /app
COPY pyproject.toml requirements-teacher.txt ./
COPY src ./src
RUN python -m pip install --no-cache-dir -r requirements-teacher.txt '.[api]' \
    && python -m pip check

COPY configs/teacher_lock.json configs/teacher_v2_candidate_lock.json ./configs/
COPY models/teacher_v2_candidate.joblib ./models/
COPY deploy/demo.py ./deploy/
COPY --from=web /web/build/web ./apps/web/build/web
USER 65534:65534
EXPOSE 10000
CMD ["sh", "-c", "exec python -m uvicorn deploy.demo:app --host 0.0.0.0 --port \"$PORT\" --no-access-log"]
