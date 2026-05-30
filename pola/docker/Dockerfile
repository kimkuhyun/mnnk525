# POLARIS 앱 컨테이너 — CLI 실행용 (3DB 는 별도 docker-compose)
#
# 빌드: docker build -t polaris:latest -f docker/Dockerfile .
# 실행: docker run --rm --env-file .env --network host polaris:latest verify
#
# GPU 백엔드는 빌드 인자로 선택:
#   --build-arg GPU=cpu       # 기본 (CPU only)
#   --build-arg GPU=cuda      # NVIDIA (CUDA torch)
#   --build-arg GPU=directml  # Windows AMD (Linux 컨테이너엔 비추, 호스트에서 직접)
FROM python:3.11-slim

ARG GPU=cpu

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONIOENCODING=utf-8

WORKDIR /app

# 시스템 의존성 (최소)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# uv 설치 (rust 기반 빠른 패키지 매니저)
RUN pip install --no-cache-dir uv

# 의존성만 먼저 (캐시 적중률 ↑)
COPY pyproject.toml ./
COPY README.md ./
COPY LICENSE ./

# 소스
COPY src/ ./src/
COPY tests/ ./tests/

# 설치 (GPU extras 분기)
RUN uv pip install --system -e ".[${GPU}]"

ENTRYPOINT ["polaris"]
CMD ["--help"]
