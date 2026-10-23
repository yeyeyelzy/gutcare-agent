ARG PYTHON_BASE_IMAGE=python:3.13-slim-bookworm
FROM ${PYTHON_BASE_IMAGE}

# PDF 文本提取使用 pypdf；扫描页渲染使用 Poppler。
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GCA_HOST=0.0.0.0 \
    GCA_PORT=8100 \
    GCA_MODE=mock

WORKDIR /app

COPY requirements.txt ./
# Docker Desktop 偶发的 DNS/软件源抖动不应让演示镜像在第一次请求时就失败。
# Acquire::Retries 会同时覆盖索引与 deb 下载；先清掉可能不完整的索引再重试。
RUN rm -rf /var/lib/apt/lists/* \
    && apt-get -o Acquire::Retries=5 \
        -o Acquire::ForceIPv4=true \
        -o Acquire::http::Timeout=30 \
        -o Acquire::https::Timeout=30 update \
    && apt-get -o Acquire::Retries=5 \
        -o Acquire::ForceIPv4=true \
        -o Acquire::http::Timeout=30 \
        -o Acquire::https::Timeout=30 install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt

COPY gutcare_agents ./gutcare_agents
COPY knowledge ./knowledge
COPY prompts ./prompts
COPY console ./console
COPY tools ./tools
COPY docs ./docs
COPY tests ./tests
COPY README.md ./

# 运行期数据（任务库、缓存）放在可挂载目录
RUN mkdir -p /app/data

EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8100/healthz', timeout=2).status==200 else 1)"

CMD ["python", "-m", "gutcare_agents", "serve"]
