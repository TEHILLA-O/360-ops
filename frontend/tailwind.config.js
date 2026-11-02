/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        graphite: {
          950: "#101114",
          900: "#16181d",
          800: "#22262e",
          700: "#31363f",
        },
        paper: "#f4f1ea",
        paper2: "#e7e2d8",
        ink: "#1c1e22",
        slate: "#5c6570",
        cobalt: "#2a4f86",
        violet: "#5d5674",
        teal: "#1c6b5a",
        amber: "#8a5a10",
        coral: "#a33d3a",
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "Segoe UI", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      boxShadow: {
        lift: "0 16px 40px rgba(16, 17, 20, 0.08)",
      },
    },
  },
  plugins: [],
};
