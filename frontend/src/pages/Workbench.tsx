import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { demoApi, productsApi, reviewsApi, tasksApi } from "../api/client";
import { Badge, Card, Empty, PageHeader, SimBadge, StatusBadge, Table, toast, usePoll } from "../components/ui";
import type { ProductBrief, ReviewItem } from "../types";

interface Overview {
  listing_tasks: Record<string, number>;
  image_tasks: Record<string, number>;
  today_spend_usd: number;
}

const StatCard: React.FC<{ label: string; value: React.ReactNode; sub?: string; tone?: string }> = ({ label, value, sub, tone = "bg-white" }) => (
  <div className={`card p-4 ${tone}`}>
    <div className="text-xs font-medium text-slate-500">{label}</div>
    <div className="mt-1 text-2xl font-bold text-slate-900">{value}</div>
    {sub && <div className="mt-1 text-[11px] text-slate-400">{sub}</div>}
  </div>
);

const Workbench: React.FC = () => {
  const [products, setProducts] = useState<ProductBrief[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [reviewSummary, setReviewSummary] = useState<Record<string, number> | null>(null);
  const [highRisks, setHighRisks] = useState<ReviewItem[]>([]);
  const [health, setHealth] = useState<{ text_configured: boolean; image_configured: boolean } | null>(null);
  const [seeding, setSeeding] = useState(false);

  const refresh = () => {
    productsApi.list().then(setProducts).catch((e) => toast(e.message, "error"));
    tasksApi.overview().then(setOverview).catch(() => {});
    reviewsApi.summary().then(setReviewSummary).catch(() => {});
    reviewsApi.list({ level: "high", status: "open" }).then(setHighRisks).catch(() => {});
    fetch("/api/health").then((r) => r.json()).then(setHealth).catch(() => {});
  };

  usePoll(refresh, 4000, []);
  useEffect(() => { document.title = "工作台 · PolyListing AI"; }, []);

  const seedDemo = async () => {
    setSeeding(true);
    try {
      const r = await demoApi.seed();
      toast(r.created?.length ? `已创建 ${r.created.length} 个演示商品` : "演示数据已存在");
      refresh();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSeeding(false);
    }
  };

  const lt = overview?.listing_tasks || {};
  const it = overview?.image_tasks || {};

  return (
    <div>
      <PageHeader
        title="工作台"
        desc="任务统计、SKU 数量、生成进度与风险提醒总览"
        extra={
          <button className="btn-secondary" onClick={seedDemo} disabled={seeding}>
            {seeding ? "创建中…" : "载入演示数据"}
          </button>
        }
      />

      {/* 配置状态提醒 */}
      {health && !(health.text_configured && health.image_configured) && (
        <div className="mb-5 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <b>⚠ 未配置 AI 模型 API</b>：当前处于模拟演示模式，所有生成结果均标记为
          <b>「模拟演示」</b>，不可用于实际发布。请前往
          <Link to="/settings" className="mx-1 font-semibold text-brand-700 underline">模型设置</Link>
          配置文本/图像模型 API 后重新生成。
        </div>
      )}

      {/* 统计卡片 */}
      <div className="mb-5 grid grid-cols-2 gap-4 lg:grid-cols-5">
        <StatCard label="商品 SKU" value={products.length} sub={`其中演示商品 ${products.filter((p) => p.is_demo).length} 个`} />
        <StatCard
          label="Listing 任务"
          value={(lt.completed || 0) + (lt.partial || 0)}
          sub={`完成 ${lt.completed || 0} · 进行中 ${lt.processing || 0} · 失败 ${lt.failed || 0}`}
        />
        <StatCard
          label="图片任务"
          value={(it.completed || 0) + (it.partial || 0)}
          sub={`完成 ${it.completed || 0} · 进行中 ${it.processing || 0} · 失败 ${it.failed || 0}`}
        />
        <StatCard
          label="待处理风险"
          value={reviewSummary?.total ?? 0}
          sub={`高风险 ${reviewSummary?.high ?? 0} · 需人工核实 ${reviewSummary?.needs_manual ?? 0}`}
          tone={reviewSummary?.high ? "bg-red-50" : "bg-white"}
        />
        <StatCard label="今日调用成本" value={`$${(overview?.today_spend_usd ?? 0).toFixed(4)}`} sub="模拟模式不产生费用" />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="高风险待处理项" extra={<Link to="/reviews" className="text-xs text-brand-700">查看全部 →</Link>}>
          {highRisks.length === 0 ? (
            <Empty text="暂无高风险项" />
          ) : (
            <Table head={["级别", "类型", "原因", "处理建议"]}>
              {highRisks.slice(0, 8).map((r) => (
                <tr key={r.id}>
                  <td className="td"><Badge tone={r.level}>{r.level === "high" ? "高" : r.level}</Badge></td>
                  <td className="td">{r.target_type === "listing" ? "文案" : "图片"}</td>
                  <td className="td max-w-[240px]">{r.reason}</td>
                  <td className="td text-slate-500">{r.suggestion}</td>
                </tr>
              ))}
            </Table>
          )}
        </Card>

        <Card title="最近任务" extra={<Link to="/tasks" className="text-xs text-brand-700">批量任务 →</Link>}>
          {products.length === 0 ? (
            <Empty text="暂无商品，请先导入或载入演示数据" />
          ) : (
            <Table head={["SKU", "名称", "图片数", "操作"]}>
              {products.slice(0, 8).map((p) => (
                <tr key={p.id}>
                  <td className="td font-mono text-xs">{p.sku}</td>
                  <td className="td">{p.name}</td>
                  <td className="td">{p.image_count}</td>
                  <td className="td">
                    <Link to={`/products?sku=${encodeURIComponent(p.sku)}`} className="text-xs text-brand-700">管理</Link>
                  </td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      </div>

      {/* 快速上手 */}
      <Card title="快速上手工作流" className="mt-5">
        <ol className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          {[
            { to: "/products", label: "① 导入商品资料与图片" },
            { to: "/listings", label: "② 选择市场生成 Listing" },
            { to: "/seo", label: "③ SEO 关键词优化" },
            { to: "/images", label: "④ 生成商品图片" },
            { to: "/reviews", label: "⑤ 人工审核" },
            { to: "/exports", label: "⑥ 批量导出" },
          ].map((s) => (
            <li key={s.to}>
              <Link to={s.to} className="rounded-lg border border-slate-200 px-3 py-2 hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700">
                {s.label}
              </Link>
            </li>
          ))}
        </ol>
        <div className="mt-4 flex items-center gap-2 border-t border-slate-100 pt-3 text-xs text-slate-500">
          <span>当前生成模式：</span>
          <SimBadge simulated={!(health?.text_configured && health?.image_configured)} />
          <StatusBadge status="info" />
        </div>
      </Card>
    </div>
  );
};

export default Workbench;
