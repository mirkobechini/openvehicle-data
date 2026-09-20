FROM python:3.12-slim

ARG DATA_URL=https://github.com/mirkobechini/openvehicle-data/releases/download/data-v0.6.0/openvehicle-data.db
ARG DATA_SHA256=d1e67a918bd87beeafe6e4891e930932c8f24e060794d30ca8df26d69db863c5

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
