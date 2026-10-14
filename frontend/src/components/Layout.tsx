import { NavLink } from "react-router-dom";
import React, { useCallback, useEffect, useState } from "react";
import { Badge, registerToast } from "./ui";

const NAV = [
  { to: "/", label: "工作台", icon: "◎", group: "总览" },
  { to: "/products", label: "商品管理", icon: "▤", group: "商品" },
  { to: "/listings", label: "Listing 生成", icon: "✎", group: "生成" },
  { to: "/seo", label: "SEO 工作台", icon: "⌕", group: "生成" },
  { to: "/images", label: "图片工作台", icon: "▣", group: "生成" },
  { to: "/editor", label: "文案编辑器", icon: "✍", group: "生成" },
  { to: "/reviews", label: "图片审核中心", icon: "✓", group: "审核" },
  { to: "/tasks", label: "批量任务", icon: "⟳", group: "管理" },
  { to: "/exports", label: "导出中心", icon: "⤓", group: "管理" },
  { to: "/settings", label: "模型设置", icon: "⚙", group: "配置" },
  { to: "/rules", label: "规则中心", icon: "⚖", group: "配置" },
];

type Config = { text: boolean; image: boolean };

const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [config, setConfig] = useState<Config>({ text: false, image: false });
  const [toastMsg, setToastMsg] = useState<{ msg: string; type: string } | null>(null);
  const [collapsed, setCollapsed] = useState(false);

  const showToast = useCallback((msg: string, type: "success" | "error" = "success") => {
    setToastMsg({ msg, type });
    window.setTimeout(() => setToastMsg(null), 3000);
  }, []);

  useEffect(() => {
    registerToast(showToast);
  }, [showToast]);

  useEffect(() => {
    const load = () =>
      fetch("/api/health")
        .then((r) => r.json())
        .then((d: { text_configured: boolean; image_configured: boolean }) =>
          setConfig({ text: d.text_configured, image: d.image_configured }))
        .catch(() => {});
    load();
    const t = window.setInterval(load, 15000);
    return () => window.clearInterval(t);
  }, []);

  const groups = NAV.reduce<Record<string, typeof NAV>>((acc, item) => {
    (acc[item.group] = acc[item.group] || []).push(item);
    return acc;
  }, {});

  return (
    <div className="flex min-h-screen">
      <aside className={`${collapsed ? "w-16" : "w-56"} shrink-0 border-r border-slate-200 bg-white transition-all`}>
        <div className="flex h-14 items-center gap-2 border-b border-slate-100 px-4">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-600 text-sm font-bold text-white">PL</span>
          {!collapsed && <span className="text-sm font-bold text-slate-800">PolyListing AI</span>}
        </div>
        <nav className="p-2">
          {Object.entries(groups).map(([g, items]) => (
            <div key={g} className="mb-2">
              {!collapsed && <div className="px-2 py-1 text-[11px] font-semibold uppercase text-slate-400">{g}</div>}
              {items.map((it) => (
                <NavLink
                  key={it.to}
                  to={it.to}
                  end={it.to === "/"}
                  className={({ isActive }) =>
                    `flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm transition-colors ${
                      isActive ? "bg-brand-50 font-semibold text-brand-700" : "text-slate-600 hover:bg-slate-50"
                    }`
                  }
                  title={it.label}
                >
                  <span className="w-4 text-center">{it.icon}</span>
                  {!collapsed && <span>{it.label}</span>}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="mx-2 mb-3 w-[calc(100%-16px)] rounded-lg border border-slate-200 py-1.5 text-xs text-slate-500 hover:bg-slate-50"
        >
          {collapsed ? "展开" : "收起"}
        </button>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-between border-b border-slate-200 bg-white px-6">
          <span className="text-sm text-slate-500">跨境电商多语种 Listing 与商品图片生成平台</span>
          <div className="flex items-center gap-2 text-xs">
            <Badge tone={config.text ? "success" : "info"}>
              文本模型：{config.text ? "已配置" : "未配置（模拟模式）"}
            </Badge>
            <Badge tone={config.image ? "success" : "info"}>
              图像模型：{config.image ? "已配置" : "未配置（模拟模式）"}
            </Badge>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
        <footer className="border-t border-slate-200 bg-white px-6 py-2 text-[11px] text-slate-400">
          AI 检查不能替代平台官方审核；无法确认的规则已标记“待人工核实”。模拟内容禁止用于实际发布。
        </footer>
      </div>

      {toastMsg && (
        <div
          className={`fixed bottom-6 right-6 z-50 rounded-lg px-4 py-2 text-sm text-white shadow-lg ${
            toastMsg.type === "error" ? "bg-red-600" : "bg-emerald-600"
          }`}
        >
          {toastMsg.msg}
        </div>
      )}
    </div>
  );
};

export default Layout;
