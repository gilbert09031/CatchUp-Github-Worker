# Python 3.12 slim 이미지 사용
FROM python:3.12-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 업데이트 및 필수 도구 설치
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# requirements.txt 먼저 복사 (Docker 캐싱 최적화)
COPY requirements.txt .

# Python 패키지 설치
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY . .

# 환경 변수 기본값 설정 (실제 값은 docker-compose에서 주입)
ENV PYTHONUNBUFFERED=1

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# FastStream Worker 실행
CMD ["python", "-m", "src.main"]
