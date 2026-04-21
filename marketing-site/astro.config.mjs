import { defineConfig } from 'astro/config';

// Production hostname after DNS points the apex here (GUIDEAI-20).
export default defineConfig({
  site: 'https://amprealize.ai',
  compressHTML: true,
});
