/** 未就绪页（TASK-070 §F）：说明依赖哪张卡，**不用假数据填充**。 */

import { Link, useLocation } from "react-router-dom";

import { NOT_READY_FEATURES, notReadyFor } from "../app/connect-info";
import { Card } from "../components/ui";

export function NotReadyPage() {
  const { pathname } = useLocation();
  const feature = notReadyFor(pathname) ?? {
    path: pathname,
    title: "该页面",
    what: "尚未规划。",
    dependsOn: [],
  };

  return (
    <div className="space-y-4">
      <Card title={`${feature.title}：尚未就绪`}>
        <p className="text-sm text-slate-700">{feature.what}</p>
        <p className="mt-3 text-sm text-slate-600">
          后端当前是 <code className="rounded bg-slate-100 px-1">501 not_implemented</code> 占位。
          依赖任务卡：
          {feature.dependsOn.length > 0 ? (
            feature.dependsOn.map((card) => (
              <span
                key={card}
                className="ml-2 rounded border border-slate-300 px-2 py-0.5 font-mono text-xs"
              >
                {card}
              </span>
            ))
          ) : (
            <span className="ml-2 text-slate-400">—</span>
          )}
        </p>
        <p className="mt-3 text-xs text-slate-500">
          这里刻意不放示例数据：那会让人以为鉴权/统计已经可用，而实际上后端还没有这些端点。
        </p>
      </Card>

      <Card title="现在可以使用的功能">
        <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
          <li>
            <Link className="underline" to="/">
              项目总览
            </Link>
            ：项目列表、索引状态与统计、绑定本地目录、重扫、删除。
          </li>
          <li>
            <Link className="underline" to="/playground">
              Playground
            </Link>
            ：Fast 检索（服务端渲染的 ContextPack）与 Deep 降级包。
          </li>
          <li>
            <Link className="underline" to="/connect">
              接入指南
            </Link>
            ：编辑器 MCP 配置片段、HTTP API 示例、数据落点与隐私说明。
          </li>
        </ul>
      </Card>
    </div>
  );
}

/** 首页/其它位置的"未就绪"提示条（不占整页时用）。 */
export function NotReadyNotice() {
  return (
    <p className="text-xs text-slate-500">
      未就绪页面：{NOT_READY_FEATURES.map((item) => item.title).join(" / ")}（依赖 TASK-060/061/062/064）
    </p>
  );
}
