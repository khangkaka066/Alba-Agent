FROM python:3.11-slim
ENV OTEL_SDK_DISABLED=true CREWAI_DISABLE_TELEMETRY=true NEXT_TELEMETRY_DISABLED=1 \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends chromium nodejs npm ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
CMD ["/bin/sh", "-c", "while :; do sleep 3600; done"]
