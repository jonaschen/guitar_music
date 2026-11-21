import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./e2e',testMatch:'**/learning-theory.spec.ts',workers:1,outputDir:'../output/theory-test-results'});
