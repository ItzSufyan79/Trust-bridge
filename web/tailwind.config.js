export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"] ,
  theme: {
    extend: {
      colors: {
        ink: "#0c0f12",
        coal: "#151a20",
        slate: "#2a3340",
        mint: "#6ee7b7",
        ember: "#ff7849",
        sky: "#7dd3fc",
        sand: "#fde68a",
      },
      fontFamily: {
        display: ["Fraunces", "serif"],
        body: ["Space Grotesk", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 40px rgba(125, 211, 252, 0.25)",
      },
      keyframes: {
        floaty: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-10px)" },
        },
        sweep: {
          "0%": { transform: "translateX(-30%)" },
          "100%": { transform: "translateX(30%)" },
        },
      },
      animation: {
        floaty: "floaty 6s ease-in-out infinite",
        sweep: "sweep 10s linear infinite",
      },
    },
  },
  plugins: [],
};
