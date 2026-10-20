/// <reference types="vitest" />
import { defineConfig, mergeConfig } from 'vitest/config';
import viteConfig from './vite.config';

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      include: ['tests/**/*.{test,spec}.{ts,tsx}', 'src/**/*.{test,spec}.{ts,tsx}'],
      exclude: ['node_modules', 'dist', '.idea', '.git', '.cache'],
      coverage: {
        provider: 'v8',
        include: ['src/**/*.{ts,tsx}'],
        reporter: ['text', 'json', 'html', 'lcov'],
        reportsDirectory: './coverage',
        exclude: [
          'node_modules/',
          'dist/',
          '**/*.d.ts',
          'src/test/**',
          'tests/**',
          '**/*.config.ts',
          '**/*.config.js',
          'src/main.tsx',
          'src/vite-env.d.ts',
        ],
        thresholds: {
          statements: 50,
          branches: 50,
          functions: 50,
          lines: 50,
        },
      },
      reporters: ['default', 'html'],
      outputFile: {
        html: './test-results/index.html',
      },
      testTimeout: 10000,
      hookTimeout: 10000,
    },
  })
);
