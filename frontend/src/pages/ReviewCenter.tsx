import React, { useCallback, useEffect, useState } from "react";
import { imagesApi, productsApi, reviewsApi } from "../api/client";
import {
  Badge,
  Card,
  Empty,
  Field,
  Modal,
  PageHeader,
  SimBadge,
  StatusBadge,
  Table,
  toast,
} from "../components/ui";
import type { GeneratedImage, Product, ProductBrief, ProductImage, ReviewItem } from "../types";

interface ReviewSummary {
  total: number;
  high: number;
  medium: number;
  low: number;
  info: number;
  needs_manual: number;
}

const LEVEL_TEXT: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
  info: "提示",
};

const TARGET_TEXT: Record<string, string> = {
  listing: "文案",
  image: "图片",
};

const TYPE_FALLBACK: Record<string, string> = {
  main: "商品主图优化",
  scene: "商品场景图",
  selling: "商品卖点图",
  info: "商品信息图",
  brand: "品牌营销图",
  localize: "多语言图片本地化",
};

const KIND_TEXT: Record<string, string> = {
  main: "主图",
  scene: "场景图",
  detail: "细节图",
  size: "尺寸图",
  package: "包装图",
  extra: "补充图",
};

const StatCard: React.FC<{ label: string; value: React.ReactNode; tone?: string }> = ({ label, value, tone = "bg-white" }) => (
  <div className={`card p-4 ${tone}`}>
    <div className="text-xs font-medium text-slate-500">{label}</div>
    <div className="mt-1 text-2xl font-bold text-slate-900">{value}</div>
  </div>
);

const ReviewCenter: React.FC = () => {
  const [products, setProducts] = useState<ProductBrief[]>([]);
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [summary, setSummary] = useState<ReviewSummary | null>(null);

  const [targetType, setTargetType] = useState("");
  const [productId, setProductId] = useState<number | null>(null);
  const [level, setLevel] = useState("");
  const [status, setStatus] = useState("open");

  const [active, setActive] = useState<ReviewItem | null>(null);
  const [origin, setOrigin] = useState<Product | null>(null);
  const [genList, setGenList] = useState<GeneratedImage[]>([]);

  const load = useCallback(async () => {
    try {
      const data = await reviewsApi.list({
        target_type: targetType || undefined,
        product_id: productId ?? undefined,
        level: level || undefined,
        status: status || undefined,
      });
      setReviews(data as ReviewItem[]);
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }, [targetType, productId, level, status]);

  const loadSummary = useCallback(async () => {
    try {
      setSummary((await reviewsApi.summary()) as ReviewSummary);
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }, []);

  useEffect(() => {
    document.title = "审核中心 · PolyListing AI";
    productsApi.list().then((d) => setProducts(d as ProductBrief[])).catch((e: Error) => toast(e.message, "error"));
  }, []);

  useEffect(() => {
    load();
    loadSummary();
  }, [load, loadSummary]);

  const skuOf = (id: number) => {
    const hit = products.find((p) => p.id === id);
    return hit ? hit.sku : `#${id}`;
  };

  const patch = async (id: number, next: "resolved" | "ignored") => {
    try {
      await reviewsApi.patch(id, next);
      toast(next === "resolved" ? "已标记为已处理" : "已忽略该项");
      await load();
      await loadSummary();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const openCompare = async (item: ReviewItem) => {
    setActive(item);
    setOrigin(null);
    setGenList([]);
    try {
      const [p, g] = await Promise.all([
        productsApi.get(item.product_id),
        imagesApi.listGenerated(item.product_id),
      ]);
      setOrigin(p as Product);
      setGenList(g as GeneratedImage[]);
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const genImage: GeneratedImage | undefined = active
    ? genList.find((g) => g.id === active.target_id)
    : undefined;
  const originImage: ProductImage | undefined = origin
    ? origin.images.find((i) => i.id === active?.target_id) || origin.images[0]
    : undefined;
  const sameTargetReviews = active
    ? reviews.filter((r) => r.target_type === active.target_type && r.target_id === active.target_id)
    : [];

  return (
    <div>
      <PageHeader title="审核中心" desc="AI 风险检查项与人工审核：原图 / 生成图对比、逐项处理与放行" />

      {/* 固定免责提示 */}
      <div className="sticky top-0 z-10 mb-5 rounded-lg border-2 border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
        <b>⚠ AI 检查不能替代平台官方审核</b>；
        <b>needs_manual = 需人工核实的项目必须由人工确认</b>，未经人工确认不得直接发布或投放。
      </div>

      {/* 统计概览 */}
      <div className="mb-5 grid grid-cols-2 gap-4 lg:grid-cols-6">
        <StatCard label="待处理总数" value={summary?.total ?? 0} />
        <StatCard label="高风险" value={summary?.high ?? 0} tone={(summary?.high ?? 0) > 0 ? "bg-red-50" : "bg-white"} />
        <StatCard label="中风险" value={summary?.medium ?? 0} tone="bg-amber-50" />
        <StatCard label="低风险" value={summary?.low ?? 0} />
        <StatCard label="提示项" value={summary?.info ?? 0} />
        <StatCard
          label="需人工核实"
          value={summary?.needs_manual ?? 0}
          tone={(summary?.needs_manual ?? 0) > 0 ? "bg-red-50" : "bg-white"}
        />
      </div>

      {/* 筛选栏 */}
      <Card title="筛选条件">
        <div className="grid gap-4 lg:grid-cols-5">
          <Field label="商品">
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
          <Field label="目标类型">
            <select className="input" value={targetType} onChange={(e) => setTargetType(e.target.value)}>
              <option value="">全部</option>
              <option value="listing">文案</option>
              <option value="image">图片</option>
            </select>
          </Field>
          <Field label="风险级别">
            <select className="input" value={level} onChange={(e) => setLevel(e.target.value)}>
              <option value="">全部</option>
              <option value="high">高</option>
              <option value="medium">中</option>
              <option value="low">低</option>
              <option value="info">提示</option>
            </select>
          </Field>
          <Field label="状态">
            <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">全部</option>
              <option value="open">待处理</option>
              <option value="resolved">已处理</option>
              <option value="ignored">已忽略</option>
            </select>
          </Field>
          <div className="flex items-end">
            <button className="btn-secondary w-full" onClick={() => { void load(); void loadSummary(); }}>
              刷新
            </button>
          </div>
        </div>
      </Card>

      {/* 审核项列表 */}
      <Card title={`审核项（${reviews.length}）`} className="mt-5">
        {reviews.length === 0 ? (
          <Empty text="当前筛选条件下暂无审核项" />
        ) : (
          <Table head={["级别", "商品", "目标类型", "规则代码", "原因", "位置", "修改建议", "人工", "操作"]}>
            {reviews.map((r) => (
              <tr key={r.id}>
                <td className="td">
                  <Badge tone={r.level}>{LEVEL_TEXT[r.level] || r.level}</Badge>
                </td>
                <td className="td font-mono text-xs">{skuOf(r.product_id)}</td>
                <td className="td">{TARGET_TEXT[r.target_type] || r.target_type}</td>
                <td className="td font-mono text-xs">{r.rule_code || "—"}</td>
                <td className="td max-w-[220px]">{r.reason}</td>
                <td className="td max-w-[160px] text-xs text-slate-500">{r.location || "—"}</td>
                <td className="td max-w-[220px] text-xs text-slate-600">{r.suggestion || "—"}</td>
                <td className="td">
                  {r.needs_manual ? <Badge tone="high">需人工核实</Badge> : <span className="text-slate-400">—</span>}
                </td>
                <td className="td">
                  <div className="flex flex-wrap items-center gap-1">
                    {r.target_type === "image" && (
                      <button className="btn-primary btn-sm" onClick={() => openCompare(r)}>
                        图片对比
                      </button>
                    )}
                    <button className="btn-secondary btn-sm" onClick={() => patch(r.id, "resolved")}>
                      标记已处理
                    </button>
                    <button className="btn-secondary btn-sm" onClick={() => patch(r.id, "ignored")}>
                      忽略
                    </button>
                    <StatusBadge status={r.status} />
                  </div>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <div className="mt-5 rounded-lg border border-slate-200 bg-white px-4 py-3 text-xs text-slate-500">
        AI 检查仅覆盖已配置规则（尺寸、背景、文字占比、禁用词、本地化等），
        <b>不替代平台官方审核与合规流程</b>；
        <b>needs_manual = 需人工核实的项目必须由人工确认</b>后才能发布。
      </div>

      {/* 原图 / 生成图对比 */}
      <Modal
        open={active !== null}
        title={`图片对比审核 · ${active ? skuOf(active.product_id) : ""}`}
        onClose={() => setActive(null)}
        wide
      >
        {active === null ? null : (
          <div>
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <div className="mb-2 flex items-center gap-2">
                  <span className="label mb-0">原图</span>
                  {originImage && <Badge>{KIND_TEXT[originImage.kind] || originImage.kind}</Badge>}
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-2">
                  {originImage ? (
                    <img src={originImage.url} alt={originImage.filename} className="h-64 w-full object-contain" />
                  ) : (
                    <Empty text="该商品暂无原图" />
                  )}
                </div>
                {originImage && (
                  <div className="mt-2 text-xs text-slate-500">
                    {originImage.filename} · {originImage.width}×{originImage.height}
                  </div>
                )}
              </div>
              <div>
                <div className="mb-2 flex items-center gap-2">
                  <span className="label mb-0">生成图</span>
                  {genImage && <Badge>{TYPE_FALLBACK[genImage.image_type] || genImage.image_type}</Badge>}
                  {genImage && <Badge>{genImage.market}</Badge>}
                </div>
                <div
                  className={`rounded-lg border p-2 ${
                    genImage?.is_simulated ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-slate-50"
                  }`}
                >
                  {genImage ? (
                    <img src={genImage.url} alt={genImage.filename} className="h-64 w-full object-contain" />
                  ) : (
                    <Empty text="未找到对应的生成图，可能已被删除" />
                  )}
                </div>
                {genImage && (
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <span>
                      {genImage.filename} · {genImage.width}×{genImage.height} · v{genImage.version}
                    </span>
                    <SimBadge simulated={genImage.is_simulated} />
                    <StatusBadge status={genImage.review_status} />
                  </div>
                )}
              </div>
            </div>

            <div className="mt-5">
              <div className="label">该文件命中项（{sameTargetReviews.length}）</div>
              {sameTargetReviews.length === 0 ? (
                <Empty text="暂无命中项" />
              ) : (
                <Table head={["级别", "规则代码", "原因", "位置", "修改建议", "人工", "操作"]}>
                  {sameTargetReviews.map((r) => (
                    <tr key={r.id}>
                      <td className="td"><Badge tone={r.level}>{LEVEL_TEXT[r.level] || r.level}</Badge></td>
                      <td className="td font-mono text-xs">{r.rule_code || "—"}</td>
                      <td className="td max-w-[200px]">{r.reason}</td>
                      <td className="td text-xs text-slate-500">{r.location || "—"}</td>
                      <td className="td max-w-[200px] text-xs text-slate-600">{r.suggestion || "—"}</td>
                      <td className="td">
                        {r.needs_manual ? <Badge tone="high">需人工核实</Badge> : <span className="text-slate-400">—</span>}
                      </td>
                      <td className="td">
                        <div className="flex flex-wrap gap-1">
                          <button className="btn-secondary btn-sm" onClick={() => patch(r.id, "resolved")}>
                            标记已处理
                          </button>
                          <button className="btn-secondary btn-sm" onClick={() => patch(r.id, "ignored")}>
                            忽略
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </Table>
              )}
            </div>

            <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              <b>需人工核实</b>：请人工比对原图与生成图的一致性（商品主体、参数、Logo、文字），
              AI 检查结果不作为最终放行依据。
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default ReviewCenter;
