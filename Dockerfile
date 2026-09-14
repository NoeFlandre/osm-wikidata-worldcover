# Reproducible build environment for the dataset pipeline.
#
# The image carries the code and its pinned dependencies only. Data is never
# baked in: mount a volume at /data and point --out and --cache at it, so a
# 229 GB run writes to the host rather than into a layer.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    HF_HOME=/data/hf \
    PATH="/app/.venv/bin:$PATH"

# exactextract ships no aarch64 wheel, so it is compiled from source and needs
# a C/C++ toolchain and GEOS headers. Everything else installs as a wheel.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake libgeos-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies resolve from the lockfile alone, so this layer is cached until
# the lockfile itself changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src/ src/
COPY README.md ./
RUN uv sync --frozen --no-dev

VOLUME /data
ENTRYPOINT ["owc"]
CMD ["--help"]
