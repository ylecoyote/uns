/**
 * Vitest + React Testing Library test setup
 *
 * This file is automatically loaded before each test file.
 * It configures:
 * - Jest-DOM matchers for DOM assertions (toBeInTheDocument, etc.)
 * - Mock global browser APIs not available in jsdom
 * - Cleanup handlers
 */

import '@testing-library/jest-dom';
import { afterEach, beforeEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

// Cleanup after each test case (e.g., clearing jsdom)
afterEach(() => {
  cleanup();
});

// Reset all mocks between tests
beforeEach(() => {
  vi.clearAllMocks();
});

// Mock window.matchMedia (not implemented in jsdom)
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(), // deprecated
    removeListener: vi.fn(), // deprecated
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock window.ResizeObserver (not implemented in jsdom)
class ResizeObserverMock {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}

Object.defineProperty(window, 'ResizeObserver', {
  writable: true,
  value: ResizeObserverMock,
});

// Mock IntersectionObserver (not implemented in jsdom)
class IntersectionObserverMock {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
  root = null;
  rootMargin = '';
  thresholds = [];
}

Object.defineProperty(window, 'IntersectionObserver', {
  writable: true,
  value: IntersectionObserverMock,
});

// Mock scrollTo (not implemented in jsdom)
Object.defineProperty(window, 'scrollTo', {
  writable: true,
  value: vi.fn(),
});

// Suppress console errors/warnings in tests unless debugging
// Uncomment the lines below to silence noisy console output in tests
// const originalError = console.error;
// const originalWarn = console.warn;
// beforeAll(() => {
//   console.error = vi.fn();
//   console.warn = vi.fn();
// });
// afterAll(() => {
//   console.error = originalError;
//   console.warn = originalWarn;
// });
