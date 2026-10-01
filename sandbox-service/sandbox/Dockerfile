FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends util-linux && rm -rf /var/lib/apt/lists/*
RUN groupadd --system sandbox && useradd --system --gid sandbox sandbox
RUN mkdir /work /output && chown -R sandbox:sandbox /work /output
COPY entrypoint.sh /runner-entrypoint
RUN chmod 755 /runner-entrypoint
WORKDIR /tmp
ENTRYPOINT ["/runner-entrypoint"]
