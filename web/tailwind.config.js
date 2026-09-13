/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      colors: {
        /*
         * 全局背景纹理（TASK-086 §4）：底色 + 网格线色。
         * 集中成 token 而不是写死在 index.css，是为了以后调深度只改一处；
         * 线色带透明度（低于 0.5），保证低对比、不抢内容。
         */
        grid: {
          base: "#eef2f7",
          line: "rgba(100, 116, 139, 0.16)",
        },
      },
    },
  },
  plugins: [],
};
