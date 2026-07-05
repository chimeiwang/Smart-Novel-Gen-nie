---
name: frontend-style-guide
description: Use when creating, reviewing, or modifying NovelWriter frontend UI, React components, CSS, layouts, visual states, chat/AI status displays, or interaction styling. Enforces the project frontend style guide: concise, clean, bright, calm, desktop-only, native CSS, and hidden-by-default tool details.
---

# Frontend Style Guide

Use this skill for any NovelWriter frontend work that affects UI, CSS, layout, component styling, interaction states, or AI/chat status presentation.

## Required Reference

Before editing frontend code, read:

```text
docs/FRONTEND_STYLE_GUIDE.md
```

Treat that file as the source of truth. Do not duplicate or replace it inside the skill. If the document is missing, search for `FRONTEND_STYLE_GUIDE.md` from the repository root and report the missing reference if it cannot be found.

## Core Rules

- Keep the interface simple, clean, bright, calm, and work-focused.
- Use native CSS and CSS custom properties. Do not introduce Tailwind.
- Reuse existing global classes and variables from `src/app/globals.css` before adding new local styles.
- The app is desktop-only: do not add mobile media queries unless the user explicitly changes the product target.
- Avoid large dark sections, heavy shadows, oversized gradients, excessive cards, candy-like roundness, and decorative backgrounds.
- Use cards only for list items, messages, modals, and isolated tool blocks.
- Keep text readable and prevent overlap, clipping, and layout shift.
- For AI/tool UI, show tool names and short parameter summaries by default. Do not show full tool return content in chat bubbles.

## Workflow

1. Read `docs/FRONTEND_STYLE_GUIDE.md`.
2. Inspect the relevant existing component and CSS files.
3. Prefer local changes that fit existing structure.
4. Verify UI state names and styling are consistent with the guide.
5. Run `npm run typecheck`; run `npm run lint` when practical.
6. For meaningful visual changes, use browser verification when a dev server is available.

## Typical Files

- `src/app/globals.css`
- `src/features/**/*.tsx`
- `src/features/**/*.css`
- `src/components/**/*.tsx`

