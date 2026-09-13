import { createBrowserRouter, RouterProvider } from "react-router-dom";

import { Layout } from "./Layout";
import { ConnectPage } from "../pages/ConnectPage";
import { NotReadyPage } from "../pages/NotReadyPage";
import { PlaygroundPage } from "../pages/PlaygroundPage";
import { ProjectDetailPage } from "../pages/ProjectDetailPage";
import { ProjectsPage } from "../pages/ProjectsPage";

/**
 * 路由表（Module/07 §1）。
 *
 * 未就绪的六个页面**故意都指向同一个 `NotReadyPage`**：它按路径查出"依赖哪张卡"，
 * 因此后端落地后只需把对应路由换掉，不必先写一堆空壳组件。
 */
const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <ProjectsPage /> },
      { path: "projects/:id", element: <ProjectDetailPage /> },
      { path: "playground", element: <PlaygroundPage /> },
      { path: "connect", element: <ConnectPage /> },
      { path: "login", element: <NotReadyPage /> },
      { path: "register", element: <NotReadyPage /> },
      { path: "setup", element: <NotReadyPage /> },
      { path: "tokens", element: <NotReadyPage /> },
      { path: "usage", element: <NotReadyPage /> },
      { path: "settings", element: <NotReadyPage /> },
      { path: "*", element: <NotReadyPage /> },
    ],
  },
]);

export function App() {
  return <RouterProvider router={router} />;
}
