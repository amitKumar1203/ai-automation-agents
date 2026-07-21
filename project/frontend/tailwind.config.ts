import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Monaco", "Consolas", "monospace"],
      },
      colors: {
        background: "rgb(var(--color-bg) / <alpha-value>)",
        surface: {
          DEFAULT: "rgb(var(--color-bg) / <alpha-value>)",
          raised: "rgb(var(--color-surface) / <alpha-value>)",
          card: "rgb(var(--color-card) / <alpha-value>)",
          border: "rgb(var(--color-border) / <alpha-value>)",
        },
        accent: {
          primary: "rgb(var(--color-accent) / <alpha-value>)",
          blue: "rgb(var(--color-accent) / <alpha-value>)",
          amber: "rgb(var(--color-warning) / <alpha-value>)",
          green: "rgb(var(--color-success) / <alpha-value>)",
          red: "rgb(var(--color-danger) / <alpha-value>)",
          neutral: "rgb(var(--color-muted) / <alpha-value>)",
          info: "rgb(var(--color-warning) / <alpha-value>)",
        },
      },
      borderRadius: {
        card: "var(--radius-card)",
        control: "var(--radius-control)",
      },
    },
  },
  plugins: [],
};

export default config;
