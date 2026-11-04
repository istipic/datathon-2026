// Tiny DOM matchers (no extra dependency): toBeInTheDocument, toHaveAttribute, toHaveTextContent.
import { expect } from 'vitest';

expect.extend({
  toBeInTheDocument(received: Element | null) {
    const pass = received != null && received.ownerDocument.contains(received);
    return { pass, message: () => `expected element ${pass ? 'not ' : ''}to be in the document` };
  },
  toHaveAttribute(received: Element, name: string, value?: unknown) {
    const actual = received.getAttribute(name);
    const pass =
      value === undefined
        ? actual !== null
        : typeof value === 'object' && value !== null && 'asymmetricMatch' in value
          ? (value as { asymmetricMatch: (v: unknown) => boolean }).asymmetricMatch(actual)
          : actual === value;
    return {
      pass,
      message: () =>
        `expected attribute ${name} (${String(actual)}) ${pass ? 'not ' : ''}to match ${String(value)}`,
    };
  },
  toHaveTextContent(received: Element, text: string | RegExp) {
    const actual = received.textContent ?? '';
    const pass = typeof text === 'string' ? actual.includes(text) : text.test(actual);
    return {
      pass,
      message: () => `expected text "${actual}" ${pass ? 'not ' : ''}to contain ${String(text)}`,
    };
  },
});

declare module 'vitest' {
  interface Assertion {
    toBeInTheDocument(): void;
    toHaveAttribute(name: string, value?: unknown): void;
    toHaveTextContent(text: string | RegExp): void;
  }
  interface AsymmetricMatchersContaining {
    toBeInTheDocument(): void;
  }
}
