FROM python:3.12-slim

WORKDIR /app

# Install pre-built wheel (built in CI where git tags are available)
COPY dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

ENV AGENTLEDGER_HOST=0.0.0.0
ENV AGENTLEDGER_PORT=8000
ENV AGENTLEDGER_DSN=sqlite:////data/agentledger.db
ENV AGENTLEDGER_UPSTREAM_URL=https://api.openai.com

VOLUME ["/data"]
EXPOSE 8000

CMD ["python", "-m", "agentledger.proxy"]
