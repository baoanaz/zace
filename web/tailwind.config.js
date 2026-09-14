/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      /*
       * 字体（TASK-098 §A-2）：复古感靠**衬线标题**营造，不下载任何字体文件。
       *
       * `serif` 是给标题/品牌字的系统衬线栈：西文用系统 Georgia/Times，
       * 中文落到 Songti/SimSun（Windows/macOS 自带）；Linux 无宋体时由
       * fontconfig 回落到 Noto Serif CJK——同样是衬线，离线可用。
       * 正文保留 sans（中文可读性优先），代码保留 mono。
       */
      fontFamily: {
        serif: [
          "ui-serif",
          "Georgia",
          "Cambria",
          '"Songti SC"',
          '"SimSun"',
          '"Noto Serif CJK SC"',
          "serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      colors: {
        /*
         * 复古博物画主题 token（TASK-098 §A-1）：米黄老纸底 + 深墨文字 + 朱砂强调。
         *
         * 为什么集中成 token：组件里不出现裸色值，调色只改一处；
         * 旧 TASK-086 的 `grid`（浅蓝灰网格）由 `paper` 取代——见 index.css 的说明。
         */
        paper: {
          base: "#f3e4c7", // 主背景：米黄牛皮纸（用户指定）
          raised: "#f7ecd8", // 次级背景：侧边栏 / hover
          card: "#ffffff", // 卡片：保持纯白，与老纸底形成层次
        },
        ink: {
          primary: "#2a2419", // 主文字：深墨（不是纯黑——纯黑在米黄底上太硬）
          muted: "#6b5d48", // 次级文字
          line: "#d9c9a8", // 边框线
        },
        accent: {
          seal: "#8c3a2b", // 强调色：朱砂印泥（active 态 / 主按钮）
        },
      },
    },
  },
  plugins: [],
};
