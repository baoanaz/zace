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
         * 复古博物画主题 token（TASK-098 §A-1；TASK-100 调整色阶）。
         *
         * 为什么集中成 token：组件里不出现裸色值，调色只改一处；
         * 旧 TASK-086 的 `grid`（浅蓝灰网格）由 `paper` 取代——见 index.css 的说明。
         *
         * TASK-100 调色（用户 2026-09-14 反馈）：
         * - 底色曾经偏深偏黄（#f3e4c7），卡片纯白落在深底上"很突兀" →
         *   底色提到用户给的浅米（#f7ecd8），卡片改为米白（#fdfdf7）而非纯白，
         *   底面与卡片的亮度差从 ~22 降到 ~6，层次靠**边框线**而不是大面积色差；
         * - 强调色曾经是朱砂红（#8c3a2b），整页"偏红" → 改为深赭褐（#6b4f32），
         *   与老纸同色系（同属暖褐），只作深浅对比，不再引入第二个色相；
         * - 危险操作（删除）仍保留红色系，但改用更收敛的 `danger` 一组。
         */
        paper: {
          base: "#f7ecd8", // 主背景：浅米（用户 2026-09-14 指定）
          raised: "#fdf6e8", // 次级背景：侧边栏 / hover（比 base 略亮）
          card: "#fdfdf7", // 卡片：米白，不是纯白（避免在浅底上"突兀"）
        },
        ink: {
          primary: "#2a2419", // 主文字：深墨（不是纯黑——纯黑在米黄底上太硬）
          muted: "#6b5d48", // 次级文字
          line: "#ddceb2", // 边框线（底色变浅后同步提亮，保持"细线"观感）
        },
        accent: {
          seal: "#6b4f32", // 强调色：深赭褐（active 态 / 主按钮），与老纸同色系
          soft: "#e8dcc3", // 强调色的浅底（选中项背景等），不用于文字
        },
        danger: {
          base: "#9c3d2e", // 危险操作（删除）：收敛的砖红，不是高饱和正红
          hover: "#833326", // 悬停态：同色相再深一档
        },
      },
    },
  },
  plugins: [],
};
