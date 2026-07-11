# syntax=docker/dockerfile:1.7
FROM node:22-slim AS builder
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages/api-client/package.json packages/api-client/package.json
RUN npm ci
COPY apps/web apps/web
COPY packages/api-client packages/api-client
RUN npm run build --workspace @inkforge/web

FROM node:22-slim AS runtime
RUN groupadd --gid 10001 inkforge && useradd --uid 10001 --gid 10001 --no-create-home inkforge
WORKDIR /app
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=43119
COPY --from=builder --chown=10001:10001 /app/apps/web/.next/standalone ./
COPY --from=builder --chown=10001:10001 /app/apps/web/.next/static ./apps/web/.next/static
USER 10001:10001
EXPOSE 43119
CMD ["node", "apps/web/server.js"]
