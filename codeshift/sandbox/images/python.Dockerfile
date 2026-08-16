# Sandbox image for executing source (Python) code during differential testing.
#
# Nothing is installed beyond the stdlib: the differential harness imports one
# module and calls one function, and every package absent here is a package the
# sandboxed code cannot reach for.
#
# Runs as uid 1000. `docker_runner` also passes --user 1000:1000, so the image
# and the run agree; either alone would be enough, which is the point.
FROM python:3.12-slim

RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp

WORKDIR /work
USER 1000:1000
