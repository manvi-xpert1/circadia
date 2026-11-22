/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#FAF7F0",
        surface: "#FFFDF8",
        beige: "#F1EADB",
        line: "#E4DCCB",
        ink: "#1F2A26",
        muted: "#5B6660",
        teal: { DEFAULT: "#1F6F6B", hover: "#185A57", tint: "#DDEBE9" },
        sage: { DEFAULT: "#8FA98A", tint: "#E3EBDF", ink: "#4E6B4A" },
        brown: { DEFAULT: "#8A6A4F", tint: "#F1E6DA" },
        warn: { DEFAULT: "#96581F", tint: "#F6E9DA" },
        danger: { DEFAULT: "#A3423A", tint: "#F7E3E0" },
      },
      fontFamily: { sans: ['"IBM Plex Sans"', "system-ui", "sans-serif"] },
      borderRadius: { card: "12px" },
      boxShadow: {
        glass: "0 8px 24px rgba(31,42,38,0.08)",
        lift: "0 2px 6px rgba(31,42,38,0.06)",
      },
    },
  },
  plugins: [],
};
