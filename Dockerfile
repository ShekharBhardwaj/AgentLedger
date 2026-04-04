FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY README.md .
COPY agentledger/ agentledger/

ARG VERSION=0.0.0.dev0
RUN pip install --no-cache-dir hatchling hatch-vcs && \
    HATCH_VCS_PRETEND_VERSION=${VERSION} pip install --no-cache-dir --no-build-isolation .

ENV AGENTLEDGER_HOST=0.0.0.0
ENV AGENTLEDGER_PORT=8000
ENV AGENTLEDGER_DSN=sqlite:////data/agentledger.db
ENV AGENTLEDGER_UPSTREAM_URL=https://api.openai.com

VOLUME ["/data"]
EXPOSE 8000

CMD ["python", "-m", "agentledger.proxy"]
