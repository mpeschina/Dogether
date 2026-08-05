FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

ARG MONGODB_DATABASE_TOOLS_VERSION=100.17.0

RUN curl -fsSL -o /tmp/mongodb-database-tools.deb \
      "https://fastdl.mongodb.org/tools/db/mongodb-database-tools-debian12-x86_64-${MONGODB_DATABASE_TOOLS_VERSION}.deb" \
    && dpkg -i /tmp/mongodb-database-tools.deb \
    && rm -f /tmp/mongodb-database-tools.deb
