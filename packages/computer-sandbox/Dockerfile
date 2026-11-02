FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OTEL_SDK_DISABLED=true \
    CREWAI_DISABLE_TELEMETRY=true

WORKDIR /workspace
# ffmpeg renders and edits media; chromium is the headless browser for screenshots/PDFs of local pages.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg chromium fonts-liberation fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && printf '#!/bin/sh\nexec chromium --headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage --disable-crash-reporter "$@"\n' > /usr/local/bin/headless-browser \
    && chmod 0755 /usr/local/bin/headless-browser
RUN mkdir -p /var/lib/nexus/artifacts && chown 10001:10001 /var/lib/nexus/artifacts
RUN pip install --no-cache-dir pandas==2.2.3 matplotlib==3.9.2 openpyxl==3.1.5 pillow==11.0.0 pytest==9.2.0
COPY scripts/check-python-licenses.py /tmp/check-python-licenses.py
RUN python /tmp/check-python-licenses.py && rm /tmp/check-python-licenses.py
CMD ["python", "-c", "import time; time.sleep(2147483647)"]
