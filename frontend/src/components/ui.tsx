import React from "react";

export const Card: React.FC<{ title?: React.ReactNode; extra?: React.ReactNode; children: React.ReactNode; className?: string }> = ({ title, extra, children, className = "" }) => (
  <div className={`card ${className}`}>
    {(title || extra) && (
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
        {extra}
      </div>
    )}
    <div className="p-4">{children}</div>
  </div>
);

export const PageHeader: React.FC<{ title: string; desc?: string; extra?: React.ReactNode }> = ({ title, desc, extra }) => (
  <div className="mb-5 flex items-start justify-between">
    <div>
      <h1 className="text-xl font-bold text-slate-900">{title}</h1>
      {desc && <p className="mt-1 text-sm text-slate-500">{desc}</p>}
    </div>
    {extra}
  </div>
);

const LEVEL_STYLES: Record<string, string> = {
  high: "bg-red-100 text-red-700",
  medium: "bg-amber-100 text-amber-700",
  low: "bg-slate-100 text-slate-600",
  info: "bg-blue-100 text-blue-700",
  success: "bg-emerald-100 text-emerald-700",
};

export const Badge: React.FC<{ children: React.ReactNode; tone?: keyof typeof LEVEL_STYLES | string; title?: string }> = ({ children, tone = "low", title }) => (
  <span className={`badge ${LEVEL_STYLES[tone] || LEVEL_STYLES.low}`} title={title}>{children}</span>
);

export const STATUS_TONE: Record<string, string> = {
  pending: "bg-slate-100 text-slate-600",
  processing: "bg-blue-100 text-blue-700",
  completed: "bg-emerald-100 text-emerald-700",
  partial: "bg-amber-100 text-amber-700",
  failed: "bg-red-100 text-red-700",
  approved: "bg-emerald-100 text-emerald-700",
  rejected: "bg-red-100 text-red-700",
  open: "bg-amber-100 text-amber-700",
  resolved: "bg-emerald-100 text-emerald-700",
  ignored: "bg-slate-100 text-slate-500",
};

export const STATUS_TEXT: Record<string, string> = {
  pending: "待处理", processing: "处理中", completed: "已完成",
  partial: "部分失败", failed: "失败",
  approved: "已通过", rejected: "已驳回",
  open: "待处理", resolved: "已处理", ignored: "已忽略",
};

export const StatusBadge: React.FC<{ status: string }> = ({ status }) => (
  <span className={`badge ${STATUS_TONE[status] || "bg-slate-100 text-slate-600"}`}>
    {STATUS_TEXT[status] || status}
  </span>
);

/** 模拟结果警示徽章：未配置 API 时必须在所有衍生内容上显示 */
export const SimBadge: React.FC<{ simulated?: boolean }> = ({ simulated }) =>
  simulated ? (
    <Badge tone="info" title="未配置 AI 模型 API，该结果为模拟演示内容，禁止用于实际发布">
      ⚠ 模拟演示
    </Badge>
  ) : (
    <Badge tone="success">真实 AI 生成</Badge>
  );

export const Table: React.FC<{ head: React.ReactNode[]; children: React.ReactNode; empty?: string }> = ({ head, children, empty = "暂无数据" }) => {
  const rows = React.Children.count(children);
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="min-w-full divide-y divide-slate-200">
        <thead>
          <tr>{head.map((h, i) => <th key={i} className="th">{h}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-slate-100 bg-white">
          {rows === 0 ? (
            <tr><td className="td text-center text-slate-400 py-8" colSpan={head.length}>{empty}</td></tr>
          ) : children}
        </tbody>
      </table>
    </div>
  );
};

export const Modal: React.FC<{ open: boolean; title: string; onClose: () => void; children: React.ReactNode; wide?: boolean }> = ({ open, title, onClose, children, wide }) => {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className={`w-full ${wide ? "max-w-4xl" : "max-w-lg"} rounded-xl bg-white shadow-xl`}>
        <div className="flex items-center justify-between border-b px-5 py-3">
          <h3 className="font-semibold text-slate-800">{title}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">✕</button>
        </div>
        <div className="max-h-[75vh] overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  );
};

export const Empty: React.FC<{ text: string }> = ({ text }) => (
  <div className="py-12 text-center text-sm text-slate-400">{text}</div>
);

export const Field: React.FC<{ label: string; children: React.ReactNode; hint?: string }> = ({ label, children, hint }) => (
  <label className="block">
    <span className="label">{label}</span>
    {children}
    {hint && <span className="mt-1 block text-xs text-slate-400">{hint}</span>}
  </label>
);

/** 轻量 Toast */
let toastFn: ((msg: string, type?: "success" | "error") => void) | null = null;
export const registerToast = (fn: (msg: string, type?: "success" | "error") => void) => { toastFn = fn; };
export const toast = (msg: string, type: "success" | "error" = "success") => toastFn?.(msg, type);

/** 轮询刷新 hook */
export const usePoll = (fn: () => void, intervalMs = 2500, deps: unknown[] = []) => {
  React.useEffect(() => {
    fn();
    const t = setInterval(fn, intervalMs);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
};
