FROM python:3.12-slim

ARG DATA_URL=https://github.com/mirkobechini/openvehicle-data/releases/download/data-v0.5.0/openvehicle-data.db
ARG DATA_SHA256=cc8d0690469b1cfe54b06a5f0a84b258c4278d0e06b588681b2a2e6f1b1a86b1

WORKDIR /app
COPY pyproject.toml README.md LICENSE LICENSE-DATA NOTICE ./
COPY core core
COPY pipeline pipeline
COPY service service
RUN pip install --no-cache-dir .

RUN mkdir -m 0755 /data
ADD --checksum=sha256:${DATA_SHA256} --chmod=0444 ${DATA_URL} /data/openvehicle-data.db

RUN useradd --system --no-create-home app
USER app

ENV OVD_DB=/data/openvehicle-data.db PORT=10000
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn --factory service.app:create_app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
