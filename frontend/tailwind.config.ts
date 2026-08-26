import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Presidio-exact palette
        surface: "#FFFFFF",
        canvas: "#EEECEA",        // Presidio warm off-white page background
        border: "#D8D5D0",        // Subtle warm grey border
        text: "#0F1F3D",          // Presidio deep navy
        muted: "#4A5568",         // Presidio body text grey
        accent: "#0F1F3D",        // Presidio primary dark navy (nav CTA)
        "accent-cta": "#F2C94C",  // Presidio signature golden yellow CTA
        "accent-soft": "#F5F4F1", // Presidio card/section bg
        teal: "#0A7A8F",          // Presidio gradient teal
        "teal-light": "#5BC8D0",  // Presidio gradient light teal
        success: "#1A7A4A",
        danger: "#C0392B",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      borderRadius: {
        full: "9999px",
        xl: "16px",
        "2xl": "20px",
        lg: "10px",
      },
      backgroundImage: {
        "presidio-gradient": "linear-gradient(90deg, #5BC8D0 0%, #0A7A8F 50%, #0F1F3D 100%)",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};

export default config;
