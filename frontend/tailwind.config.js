/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#0A0A0A",
        surface: "#131313",
        "surface-card": "#1C1B1B",
        primary: "#00FF41", // Neon Green
        secondary: "#0070F3", // Electric Blue
        accent: "#79FFE1",
        "on-surface": "#E5E2E1",
        warn: "#f59e0b",
        danger: "#ef4444",
        success: "#10b981",
        ia: "#8b5cf6",
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
      },
      borderRadius: {
        xl: "12px",
      },
      animation: {
        'pulse-slow': 'pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      }
    },
  },
  plugins: [],
}
