FROM docker:27-cli AS dockercli
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OTEL_SDK_DISABLED=true \
    CREWAI_DISABLE_TELEMETRY=true \
    ANONYMIZED_TELEMETRY=false \
    DO_NOT_TRACK=true \
    ANONYMIZED_TELEMETRY=false \
    DO_NOT_TRACK=true \
    LITELLM_TELEMETRY_DISABLED=true \
    LITELLM_OFFLINE_MODE=true \
    PYTHONPATH=/workspace/apps/api:/workspace/packages/core-schema/python:/workspace/packages/core-schema/templates:/workspace/packages/model-gateway:/workspace/packages/agent-runtime:/workspace/packages/learning-transfer:/workspace/packages/computer-sandbox:/workspace/packages/rag-engine:/workspace/packages/mcp-hub:/workspace/packages/agent-skills:/workspace/packages/builtin-tools

WORKDIR /workspace
RUN useradd --system --uid 10001 --create-home nexus && mkdir -p /var/lib/nexus/artifacts && chown -R nexus:nexus /home/nexus /var/lib/nexus/artifacts
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY apps/api/requirements.txt ./apps/api/requirements.txt
RUN pip install --no-cache-dir -r apps/api/requirements.txt
COPY scripts/check-python-licenses.py ./scripts/check-python-licenses.py
COPY scripts/smoke_test.py ./scripts/smoke_test.py
RUN python scripts/check-python-licenses.py
COPY apps/api ./apps/api
COPY packages ./packages
RUN chmod +x apps/api/start.sh
USER nexus
EXPOSE 8000
ENTRYPOINT ["/workspace/apps/api/start.sh"]
CMD ["api"]
