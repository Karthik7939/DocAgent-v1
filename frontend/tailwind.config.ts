import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: "#fffdf6",
        canvas: "#f8f1e3",
        border: "#e7d7bc",
        text: "#443729",
        muted: "#7a6c5a",
        accent: "#a85f2d",
        "accent-soft": "#f4dfc6",
        success: "#39705e",
        danger: "#b44a3f",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      borderRadius: {
        lg: "10px",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};

export default config;
