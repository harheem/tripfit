# 합의저울(hapui) 원격 MCP 서버 — Lightsail Container Service(linux/amd64)용
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HAPUI_HOST=0.0.0.0 \
    HAPUI_PORT=8080

# CBC(mip 내장 바이너리)가 쓰는 런타임 라이브러리
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 libgfortran5 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY hapui ./hapui
COPY ui ./ui

RUN useradd --create-home --uid 10001 hapui
USER hapui

EXPOSE 8080
CMD ["sh", "-c", "python -m hapui.server --port ${HAPUI_PORT}"]
