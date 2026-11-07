# build context = repo root (see docker-compose.yml)
FROM python:3.13-slim
WORKDIR /srv
COPY 04_flood_nlp_model/requirements.txt 04_flood_nlp_model/requirements.txt
COPY 03_intake_ai_agent/requirements.txt 03_intake_ai_agent/requirements.txt
RUN pip install --no-cache-dir -r 03_intake_ai_agent/requirements.txt
# WangchanBERTa model on CPU (~800 MB of packages). Build with  --build-arg WITH_WCB=0  to skip it (agent then uses v1).
ARG WITH_WCB=1
COPY 04_flood_nlp_model/requirements-wcb.txt 04_flood_nlp_model/requirements-wcb.txt
RUN if [ "$WITH_WCB" = "1" ]; then pip install --no-cache-dir -r 04_flood_nlp_model/requirements-wcb.txt; fi
COPY common common
COPY 04_flood_nlp_model 04_flood_nlp_model
COPY 03_intake_ai_agent 03_intake_ai_agent
ENV PYTHONPATH=/srv/common:/srv/03_intake_ai_agent:/srv/04_flood_nlp_model
WORKDIR /srv/03_intake_ai_agent
CMD ["uvicorn", "agent.server:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
