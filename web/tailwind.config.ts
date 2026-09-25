import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        canvas: {
          DEFAULT: "#FAF9F6",
          subtle: "#F5F3ED",
          muted: "#EBE8DF",
        },
        ink: {
          DEFAULT: "#121212",
          secondary: "#555555",
          muted: "#888888",
        },
        edge: {
          DEFAULT: "#E5E3DC",
          subtle: "#EFECE6",
          dark: "#242424",
        },
        night: {
          DEFAULT: "#0F0F0F",
          surface: "#181818",
          edge: "#282828",
        },
      },
      fontFamily: {
        serif: [
          "var(--font-serif)",
          "Newsreader",
          "Lora",
          "Charter",
          "Bitstream Charter",
          "Georgia",
          "serif",
        ],
        sans: [
          "var(--font-geist-sans)",
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "var(--font-geist-mono)",
          "Menlo",
          "Monaco",
          "Consolas",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
};
export default config;
