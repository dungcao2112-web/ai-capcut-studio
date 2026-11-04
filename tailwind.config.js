/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Be Vietnam Pro"', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      colors: {
        studio: {
          950: '#0b0b0e',
          900: '#111114',
          850: '#16161a',
          800: '#1c1c21',
          750: '#232329',
          700: '#2a2a31',
          600: '#3a3a43',
          500: '#55555f',
        },
        accent: {
          DEFAULT: '#22d3ee',
          soft: '#0e7490',
        },
        muse: '#a855f7',
        goc: '#10b981',
      },
      boxShadow: {
        glow: '0 0 0 1px rgba(34,211,238,.5), 0 0 18px rgba(34,211,238,.25)',
      },
    },
  },
  plugins: [],
};
