# Sandbox image for executing translated (TypeScript) code during differential
# testing.
#
# `tsx` is installed at build time, not fetched at run time: containers run with
# --network none, so an `npx tsx` that had to download anything would simply
# fail. Build has the network; the run never does.
#
# node:20-slim already ships a `node` user at uid 1000, which is the uid
# `docker_runner` pins with --user.
FROM node:20-slim

RUN npm install -g tsx@4 typescript@5 && npm cache clean --force

ENV HOME=/tmp \
    XDG_CACHE_HOME=/tmp \
    TSX_DISABLE_CACHE=1

WORKDIR /work
USER 1000:1000
