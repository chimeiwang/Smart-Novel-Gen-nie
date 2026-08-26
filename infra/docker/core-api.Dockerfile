# syntax=docker/dockerfile:1.7
FROM eclipse-temurin:21-jdk-jammy AS builder

WORKDIR /workspace
# Temurin builder 默认没有 unzip；Maven Wrapper 否则会改下 tar.gz，导致 zip 锁定哈希失效。
RUN apt-get update \
    && apt-get install --no-install-recommends --yes unzip \
    && rm -rf /var/lib/apt/lists/*
COPY .mvn .mvn
COPY mvnw pom.xml ./
COPY apps/core-api-java/pom.xml apps/core-api-java/pom.xml
COPY packages/service-auth-java/pom.xml packages/service-auth-java/pom.xml
COPY packages/service-contracts-java/pom.xml packages/service-contracts-java/pom.xml
COPY tools/inkforge-cli-java/pom.xml tools/inkforge-cli-java/pom.xml
COPY contracts contracts
COPY packages/service-auth-java packages/service-auth-java
COPY packages/service-contracts-java packages/service-contracts-java
COPY apps/core-api-java apps/core-api-java
COPY apps/core-api/src/inkforge_core/db/schema-contract.json \
     apps/core-api/src/inkforge_core/db/schema-contract.json
RUN --mount=type=cache,target=/root/.m2 \
    chmod 0555 mvnw \
    && ./mvnw --batch-mode --no-transfer-progress \
       -pl apps/core-api-java -am -DskipTests clean package

FROM eclipse-temurin:21-jre-jammy AS runtime

RUN apt-get update \
    && apt-get install --no-install-recommends --yes \
       ca-certificates curl ffmpeg fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 inkforge \
    && useradd --uid 10001 --gid 10001 --no-create-home inkforge
# 空命名卷会继承镜像挂载点的所有权；独立层避免权限调整重建 FFmpeg 与字体。
RUN install -d -o 10001 -g 10001 /data/uploads

WORKDIR /app
COPY --from=builder --chown=10001:10001 \
     /workspace/apps/core-api-java/target/inkforge-core-api-0.1.0-SNAPSHOT.jar \
     /app/inkforge-core-api.jar
COPY --chown=10001:10001 infra/docker/inkforge-schema-guard \
     /usr/local/bin/inkforge-schema-guard
RUN chmod 0555 /usr/local/bin/inkforge-schema-guard

LABEL cn.inkforge.core.runtime="java"

USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["java", "-jar", "/app/inkforge-core-api.jar"]
