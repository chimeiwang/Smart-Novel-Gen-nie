# ---- 构建阶段 ----
FROM public.ecr.aws/docker/library/node:22-slim AS builder
WORKDIR /app

RUN apt-get update && apt-get install -y python3 make g++ git openssl && rm -rf /var/lib/apt/lists/*

COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps

COPY . .
RUN npx prisma generate
RUN npm run build

# ---- 运行阶段 ----
FROM public.ecr.aws/docker/library/node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=43119

RUN apt-get update && apt-get install -y openssl libssl3 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/prisma ./prisma
COPY --from=builder /app/node_modules/.prisma ./node_modules/.prisma

EXPOSE 43119
CMD ["node", "server.js"]
