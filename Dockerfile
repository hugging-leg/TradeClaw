# ============================================================
# Stage 1: Build frontend
# ============================================================
FROM node:22-slim AS frontend-builder

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# ============================================================
# Stage 2: Python runtime
# ============================================================
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 系统依赖（cvxpy/ecos 编译 + PostgreSQL 客户端）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ cmake libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖（利用 Docker 层缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY src/ src/
COPY main.py config.py ./

# 前端静态文件（从 Stage 1 拷贝）
COPY --from=frontend-builder /build/dist /app/frontend/dist

# 数据目录 & 非 root 用户
RUN mkdir -p /app/user_data/logs && \
    useradd -m -u 1000 trader && \
    chown -R trader:trader /app
USER trader

# 健康检查 — 使用 API 端点
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -sf http://localhost:8000/api/settings > /dev/null || exit 1

EXPOSE 8000

CMD ["python", "main.py"]
