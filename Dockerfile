# syntax=docker/dockerfile:1
#
# The deployable unit: the pipeline, the gate, and the MCP server.
#
# There is no build stage and nothing compiled, because the pipeline is
# stdlib Python by design. That is not minimalism for its own sake -- an
# image with no native extensions and no transitive C toolchain is an
# image a broadcaster's security review can finish in an afternoon.
#
# Built and exercised in CI on every push (.github/workflows/ci.yml), so
# "it containerises" is a thing that happened rather than a thing claimed.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependency metadata first so an unchanged dependency set reuses the
# layer. There are no runtime dependencies today; this keeps the shape
# right for when there are.
COPY pyproject.toml ./
COPY src/ ./src/
COPY kql/ ./kql/

RUN pip install --no-cache-dir ".[mcp]"

# Production environments ask who this runs as, and "root" is a bad
# answer to have to give.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin gegen
USER gegen

# The health signal is the gate measuring itself. A container whose
# process is alive but whose gate has stopped refusing unsupportable
# claims is not healthy, whatever the process table says -- and because
# the gate is deterministic, this check has one correct answer rather
# than a threshold somebody tuned.
HEALTHCHECK --interval=5m --timeout=90s --start-period=15s --retries=1 \
  CMD ["gegenpress", "eval", "--seeds", "2026", "--matches", "1"]

# `docker run <image> chaos` breaks each dependency in turn and prints
# what still reaches the viewer. `docker run <image> mcp` serves the gate
# over stdio.
ENTRYPOINT ["gegenpress"]
CMD ["--help"]
