FROM python:3.11-slim

ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    WEB_HOST=0.0.0.0

WORKDIR /app

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock \
    -i ${PIP_INDEX_URL}

COPY . .

# HF Spaces 要求监听 7860；本地 compose 用 PORT=8000 覆盖
ENV PORT=7860
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '7860') + '/health')"

CMD ["python", "main.py", "serve"]
