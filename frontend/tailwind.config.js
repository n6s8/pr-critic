/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: '#0f0f0f',
        elevated: '#141414',
        card: '#1a1a1a',
        active: '#1e1e1e',
        border: '#1e1e1e',
        border2: '#252525',
        border3: '#2e2e2e',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}