/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          dark: "#091413",
          primary: "#285A48",
          secondary: "#408A71",
          light: "#B0E4CC",
        }
      }
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}