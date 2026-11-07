# build context = repo root (see docker-compose.yml)
FROM python:3.13-slim
COPY 02_api_backend/requirements.txt /tmp/req.txt
RUN pip install --no-cache-dir -r /tmp/req.txt
WORKDIR /srv
COPY common common
COPY 02_api_backend 02_api_backend
COPY 06_chat_assistant 06_chat_assistant
COPY 05_evaluation/data 05_evaluation/data
ENV PYTHONPATH=/srv/common:/srv/02_api_backend:/srv/06_chat_assistant DB_PATH=/data/floodlink.db
WORKDIR /srv/02_api_backend
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
