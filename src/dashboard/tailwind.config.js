/** @type {import('tailwindcss').Config} */
export default {
    content: ['./src/**/*.{html,js,svelte,ts}'],
    theme: {
        extend: {
            colors: {
                dias: {
                    primary: '#0ea5e9',
                    secondary: '#6366f1',
                    dark: '#0f172a',
                    accent: '#f59e0b'
                }
            }
        },
    },
    plugins: [],
}
