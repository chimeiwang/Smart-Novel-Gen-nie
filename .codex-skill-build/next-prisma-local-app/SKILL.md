---
name: next-prisma-local-app
description: Use when modifying NovelWriter's Next.js App Router code, Prisma SQLite schema or queries, server actions, API routes, local-first data flow, database migrations, or TypeScript data boundaries.
---

# Next Prisma Local App

Use this skill for NovelWriter application work involving Next.js App Router, Prisma, SQLite, server actions, API routes, and local-first persistence.

## Required References

Read the relevant files before changing data flow:

```text
AGENTS.md
prisma/schema.prisma
src/shared/db/prisma.ts
src/app/actions.ts
src/app/api/
src/app/workspace/[novelId]/page.tsx
```

Load only what is needed for the task.

## Project Rules

- Use Next.js App Router conventions.
- Keep data mutations in server actions or route handlers; do not mutate data directly from client components.
- Use the existing Prisma singleton from `src/shared/db/prisma.ts`.
- Keep SQLite/local-first assumptions in mind.
- Preserve TypeScript strictness and existing `@/*` imports.
- Prefer explicit data shapes across server/client boundaries.
- When Prisma schema changes, add a migration and regenerate Prisma Client when required.
- Avoid broad refactors unrelated to the requested behavior.

## Validation

- Run `npm run typecheck`.
- For Prisma schema changes, run the appropriate Prisma command requested by the task, usually `npm run db:generate` and `npm run db:migrate`.
- For API changes, inspect request/response shapes and frontend callers together.

