/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        severity: {
          benign: '#22c55e',
          low: '#eab308',
          medium: '#f97316',
          high: '#ef4444',
          critical: '#991b1b',
        },
        surface: {
          0: '#0a0a0f',
          1: '#12121a',
          2: '#1a1a25',
          3: '#222230',
          4: '#2a2a3a',
        },
        accent: {
          blue: '#3b82f6',
          purple: '#8b5cf6',
          cyan: '#06b6d4',
        },
      },
    },
  },
  plugins: [],
}
