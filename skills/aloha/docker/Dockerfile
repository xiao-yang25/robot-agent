FROM ghcr.io/astral-sh/uv:0.12.13 AS uv
FROM ubuntu:22.04

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       build-essential cmake git ca-certificates procps \
       libosmesa6 libgl1 libegl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
RUN useradd --create-home --uid 1000 --shell /bin/bash developer \
    && mkdir /workspace && chown developer:developer /workspace

USER developer
WORKDIR /workspace
ENV MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa
CMD ["/bin/bash"]
