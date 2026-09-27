/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        navy: {
          950: "#06101c",
          900: "#0b1f3a",
          800: "#123055",
          700: "#1c4a78",
        },
        gold: "#c9a227",
        saffron: "#ff9933",
        india: "#138808",
        paper: "#f3efe6",
      },
      fontFamily: {
        serif: ['"Source Serif 4"', "Georgia", "serif"],
        sans: ['"IBM Plex Sans"', '"Segoe UI"', "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 0 rgba(6,16,28,0.04), 0 16px 40px rgba(6,16,28,0.06)",
      },
    },
  },
  plugins: [],
};
