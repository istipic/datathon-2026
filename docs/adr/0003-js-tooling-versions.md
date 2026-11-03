# ADR 0003: JavaScript tooling beyond the fixed list, and Node 20 version pins

- Status: accepted
- Date: 2026-11-03

## Context

The fixed stack names React 18, Vite, TypeScript, Tailwind 3, vitest, Testing Library, Playwright,
ESLint, Prettier on **Node 20 LTS**. Some of the newest releases do not run on Node 20.

## Decisions

Pins (all verified by running `pnpm -r lint test build` on Node 20.20.2):

- **vitest 4.x**, not 5: vitest 5 requires Node ≥ 22.12.
- **jsdom 27.x**, not 30: jsdom 30 pulls undici 8, which crashes on Node 20 (`reading 'bind'`).
- **TypeScript 5.9**, not 7: typescript-eslint supports TypeScript < 6.1.
- React 18.3 (as specified), `@types/react` 18.

Additional dev dependencies (essential, not listed in the stack):

| Package                                                                   | Why                                         |
| ------------------------------------------------------------------------- | ------------------------------------------- |
| `jsdom`                                                                   | DOM for vitest component tests              |
| `@testing-library/dom`                                                    | peer dependency of `@testing-library/react` |
| `@vitejs/plugin-react`                                                    | JSX transform for Vite/vitest               |
| `@types/react`, `@types/react-dom`                                        | typings for strict TypeScript               |
| `typescript-eslint`, `@eslint/js`, `eslint-plugin-react-hooks`, `globals` | ESLint 9 flat config for TypeScript/React   |

No `@testing-library/jest-dom` / `user-event`: plain assertions and `fireEvent` suffice.
`@playwright/test` is installed at the root as specified (browsers are not downloaded until an app adds e2e tests).

## Consequences

Revisit the pins when the project moves to Node 22+.
