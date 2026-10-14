/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef4ff", 100: "#dbe6fe", 200: "#bfd3fe", 300: "#93b4fd",
          400: "#608afa", 500: "#3b6bf6", 600: "#254deb", 700: "#1d3ad8",
          800: "#1e32af", 900: "#1e2f8a",
        },
      },
    },
  },
  plugins: [],
};
