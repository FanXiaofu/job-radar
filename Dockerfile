FROM python:3.11-slim

ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    WEB_HOST=0.0.0.0

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

# HF Spaces 要求监听 7860；本地 compose 用 PORT=8000 覆盖
ENV PORT=7860
EXPOSE 7860

CMD ["python", "main.py", "serve"]
