import React, { useEffect, useState } from "react";
import { imagesApi, listingsApi, productsApi, tasksApi } from "../api/client";
import {
  Badge,
  Card,
  Field,
  PageHeader,
  SimBadge,
  StatusBadge,
  Table,
  toast,
  usePoll,
} from "../components/ui";
import type { ImageTask, ListingTask, ProductBrief } from "../types";

interface TaskOverview {
  pending: number;
  processing: number;
  completed: number;
  partial: number;
  failed: number;
}

interface Overview {
  listing_tasks: TaskOverview;
  image_tasks: TaskOverview;
  today_spend_usd: number;
}

const EMPTY_STATUS: TaskOverview = { pending: 0, processing: 0, completed: 0, partial: 0, failed: 0 };

const STATUS_OPTIONS = [
  { value: "", label: "全部状态" },
  { value: "pending", label: "待处理" },
  { value: "processing", label: "处理中" },
  { value: "completed", label: "已完成" },
  { value: "partial", label: "部分失败" },
  { value: "failed", label: "失败" },
];

const fmtDuration = (ms: number) => {
  if (!ms) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
};

const MiniStat: React.FC<{ label: string; value: number; tone?: string }> = ({ label, value, tone = "text-slate-900" }) => (
  <div className="rounded-lg border border-slate-200 px-3 py-2">
    <div className="text-[11px] text-slate-500">{label}</div>
    <div className={`text-lg font-bold ${tone}`}>{value}</div>
  </div>
);

const StatusRow: React.FC<{ label: string; data: TaskOverview }> = ({ label, data }) => (
  <div>
    <div className="mb-2 text-xs font-medium text-slate-500">{label}</div>
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
      <MiniStat label="待处理" value={data.pending} />
      <MiniStat label="处理中" value={data.processing} tone="text-blue-600" />
      <MiniStat label="已完成" value={data.completed} tone="text-emerald-600" />
      <MiniStat label="部分失败" value={data.partial} tone="text-amber-600" />
      <MiniStat label="失败" value={data.failed} tone={data.failed > 0 ? "text-red-600" : "text-slate-900"} />
    </div>
  </div>
);

const BatchTasks: React.FC = () => {
  const [tab, setTab] = useState<"listing" | "image">("listing");
  const [products, setProducts] = useState<ProductBrief[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [listingTasks, setListingTasks] = useState<ListingTask[]>([]);
  const [imageTasks, setImageTasks] = useState<ImageTask[]>([]);
  const [productId, setProductId] = useState<number | null>(null);
  const [status, setStatus] = useState("");
  const [hasActive, setHasActive] = useState(false);
  const [retrying, setRetrying] = useState<number | null>(null);

  useEffect(() => {
    productsApi.list().then((d) => setProducts(d as ProductBrief[])).catch((e: Error) => toast(e.message, "error"));
  }, []);

  useEffect(() => {
    document.title = "批量任务中心 · PolyListing AI";
  }, []);

  const load = () => {
    tasksApi.overview().then((d) => setOverview(d as Overview)).catch(() => {});
    const pid = productId ?? undefined;
    const st = status || undefined;
    if (tab === "listing") {
      listingsApi.listTasks(pid, st)
        .then((d) => setListingTasks(d as ListingTask[]))
        .catch((e: Error) => toast(e.message, "error"));
    } else {
      imagesApi.listTasks(pid, st)
        .then((d) => setImageTasks(d as ImageTask[]))
        .catch((e: Error) => toast(e.message, "error"));
    }
  };

  usePoll(load, hasActive ? 2500 : 20000, [tab, productId, status, hasActive]);

  useEffect(() => {
    const list = tab === "listing" ? listingTasks : imageTasks;
    setHasActive(list.some((t) => t.status === "pending" || t.status === "processing"));
  }, [listingTasks, imageTasks, tab]);

  const retry = async (id: number) => {
    setRetrying(id);
    try {
      if (tab === "listing") await tasksApi.retryListing(id);
      else await tasksApi.retryImage(id);
      toast("重试任务已提交");
      load();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setRetrying(null);
    }
  };

  const lt = overview?.listing_tasks || EMPTY_STATUS;
  const it = overview?.image_tasks || EMPTY_STATUS;
  const canRetry = (s: string) => s === "failed" || s === "partial";

  return (
    <div>
      <PageHeader
        title="批量任务中心"
        desc="Listing 与图片生成任务的统一状态总览、筛选与失败重试"
        extra={
          hasActive ? (
            <Badge tone="info">有任务进行中 · 每 2.5 秒自动刷新</Badge>
          ) : (
            <Badge tone="low">暂无进行中任务</Badge>
          )
        }
      />

      <Card
        title="任务状态总览"
        extra={
          <div className="text-right">
            <div className="text-[11px] text-slate-400">今日花费</div>
            <div className="text-sm font-bold text-slate-900">
              ${(overview?.today_spend_usd ?? 0).toFixed(4)}
            </div>
          </div>
        }
      >
        <div className="space-y-4">
          <StatusRow label="Listing 生成任务" data={lt} />
          <StatusRow label="图片生成任务" data={it} />
        </div>
      </Card>

      <Card title="任务列表" className="mt-5">
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <div className="inline-flex rounded-lg border border-slate-300 p-0.5">
            {([
              { key: "listing" as const, label: "Listing 任务" },
              { key: "image" as const, label: "图片任务" },
            ]).map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`rounded-md px-4 py-1.5 text-sm font-medium ${
                  tab === t.key ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-50"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div className="w-56">
            <Field label="按商品筛选">
              <select
                className="input"
                value={productId ?? ""}
                onChange={(e) => setProductId(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">全部商品</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.sku} · {p.name}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <div className="w-40">
            <Field label="按状态筛选">
              <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
                {STATUS_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <button className="btn-secondary" onClick={load}>
            刷新
          </button>
        </div>

        {tab === "listing" ? (
          <Table head={["任务ID", "SKU", "市场", "语言", "状态", "生成模式", "模型", "耗时", "费用", "错误信息", "操作"]}>
            {listingTasks.map((t) => (
              <tr key={t.id}>
                <td className="td font-mono text-xs">#{t.id}</td>
                <td className="td font-mono text-xs">{t.product_sku || "—"}</td>
                <td className="td">{t.market}</td>
                <td className="td">{t.language || "—"}</td>
                <td className="td"><StatusBadge status={t.status} /></td>
                <td className="td"><SimBadge simulated={t.is_simulated} /></td>
                <td className="td text-xs text-slate-500">{t.model_name || "—"}</td>
                <td className="td text-xs">{fmtDuration(t.duration_ms)}</td>
                <td className="td text-xs">${(t.cost_usd || 0).toFixed(4)}</td>
                <td className="td max-w-[220px] text-xs text-red-600">{t.error || <span className="text-slate-400">—</span>}</td>
                <td className="td">
                  <button
                    className="btn-secondary btn-sm"
                    disabled={!canRetry(t.status) || retrying === t.id}
                    onClick={() => retry(t.id)}
                    title={canRetry(t.status) ? "重新执行该任务" : "仅失败 / 部分失败的任务可重试"}
                  >
                    {retrying === t.id ? "提交中…" : "重试"}
                  </button>
                </td>
              </tr>
            ))}
          </Table>
        ) : (
          <Table head={["任务ID", "SKU", "市场", "语言", "状态", "生成模式", "模型", "耗时", "费用", "错误信息", "操作"]}>
            {imageTasks.map((t) => (
              <tr key={t.id}>
                <td className="td font-mono text-xs">#{t.id}</td>
                <td className="td font-mono text-xs">{t.product_sku || "—"}</td>
                <td className="td">{t.market}</td>
                <td className="td">{t.language || "—"}</td>
                <td className="td"><StatusBadge status={t.status} /></td>
                <td className="td"><SimBadge simulated={t.is_simulated} /></td>
                <td className="td text-xs text-slate-500">{t.model_name || "—"}</td>
                <td className="td text-xs">{fmtDuration(t.duration_ms)}</td>
                <td className="td text-xs">${(t.cost_usd || 0).toFixed(4)}</td>
                <td className="td max-w-[220px] text-xs text-red-600">{t.error || <span className="text-slate-400">—</span>}</td>
                <td className="td">
                  <button
                    className="btn-secondary btn-sm"
                    disabled={!canRetry(t.status) || retrying === t.id}
                    onClick={() => retry(t.id)}
                    title={canRetry(t.status) ? "重新执行该任务" : "仅失败 / 部分失败的任务可重试"}
                  >
                    {retrying === t.id ? "提交中…" : "重试"}
                  </button>
                </td>
              </tr>
            ))}
          </Table>
        )}

        <p className="mt-3 text-xs text-slate-500">
          说明：任务失败时，已成功生成的内容会保留；点击「重试」会重新执行该任务并生成新版本，历史版本仍可在对应模块中查看与对比。
        </p>
      </Card>
    </div>
  );
};

export default BatchTasks;
