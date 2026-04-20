import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	kit: {
		adapter: adapter({
			pages: 'build',
			assets: 'build',
			fallback: 'index.html',
			precompress: false,
			strict: false
		}),
		paths: {
			// PUBLIC_BASE_PATH=/dias in production (set at build time)
			// Empty string in local dev (npm run dev, porta 5173 — invariato)
			base: process.env.PUBLIC_BASE_PATH || ''
		}
	}
};

export default config;
