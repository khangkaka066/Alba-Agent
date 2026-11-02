import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "var(--text-primary)",
        muted: "var(--text-secondary)",
        line: "var(--border-subtle)",
        canvas: "var(--surface-canvas)",
        leaf: "#10B981",
        mint: "rgba(16,185,129,.14)",
        amber: "#F59E0B",
        studio: {
          ground: "#090A0F",
          panel: "#11131A",
          elevated: "#191B24",
          indigo: "#6366F1",
          cyan: "#06B6D4",
          emerald: "#10B981",
          amber: "#F59E0B",
          rose: "#F43F5E",
        },
      },
      boxShadow: { panel: "0 18px 48px rgba(0, 0, 0, .26)" },
    },
  },
  plugins: [],
};

export default config;
