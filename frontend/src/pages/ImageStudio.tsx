import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { imagesApi, metaApi, productsApi } from "../api/client";
import {
  Badge,
  Card,
  Empty,
  Field,
  PageHeader,
  SimBadge,
  StatusBadge,
  Table,
  toast,
  usePoll,
} from "../components/ui";
import type { GeneratedImage, ImageTask, Meta, Product, ProductBrief, ProductImage } from "../types";

/** 图片类型兜底文案（meta 接口返回后以其为准） */
const IMAGE_TYPE_FALLBACK: Record<string, string> = {
  main: "商品主图优化",
  scene: "商品场景图",
  selling: "商品卖点图",
  info: "商品信息图",
  brand: "品牌营销图",
  localize: "多语言图片本地化",
};

const ASPECT_FALLBACK = ["1:1", "3:4", "4:3", "9:16", "16:9"];

const PLATFORM_LABEL: Record<string, string> = {
  amazon: "Amazon",
  temu: "Temu",
  独立站: "独立站",
};

const KIND_TEXT: Record<string, string> = {
  main: "主图",
  scene: "场景图",
  detail: "细节图",
  size: "尺寸图",
  package: "包装图",
  extra: "补充图",
};

const REVIEW_TEXT: Record<string, string> = {
  pending: "待审核",
  approved: "已通过",
  rejected: "已驳回",
};

const IMAGE_STATUS_TONE: Record<string, string> = {
  pending: "low",
  approved: "success",
  rejected: "high",
};

const fmtBytes = (n: number) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`);

const ImageStudio: React.FC = () => {
  const [products, setProducts] = useState<ProductBrief[]>([]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [productId, setProductId] = useState<number | null>(null);
  const [product, setProduct] = useState<Product | null>(null);
  const [imageConfigured, setImageConfigured] = useState<boolean | null>(null);

  // 生成配置
  const [imageType, setImageType] = useState("main");
  const [platform, setPlatform] = useState("amazon");
  const [market, setMarket] = useState("US");
  const [aspectRatio, setAspectRatio] = useState("1:1");
  const [count, setCount] = useState(1);
  const [style, setStyle] = useState("");
  const [background, setBackground] = useState("");
  const [prompt, setPrompt] = useState("");
  const [refIds, setRefIds] = useState<number[]>([]);
  const [submitting, setSubmitting] = useState(false);

  // 任务与结果
  const [tasks, setTasks] = useState<ImageTask[]>([]);
  const [generated, setGenerated] = useState<GeneratedImage[]>([]);
  const [filterMarket, setFilterMarket] = useState("");
  const [filterType, setFilterType] = useState("");
  const [polling, setPolling] = useState(false);

  useEffect(() => {
    productsApi.list().then((d) => setProducts(d as ProductBrief[])).catch((e: Error) => toast(e.message, "error"));
    metaApi.get().then(setMeta).catch((e: Error) => toast(e.message, "error"));
    fetch("/api/health")
      .then((r) => r.json())
      .then((d: { image_configured?: boolean }) => setImageConfigured(!!d.image_configured))
      .catch(() => setImageConfigured(null));
  }, []);

  useEffect(() => {
    document.title = "图片工作台 · PolyListing AI";
  }, []);

  // 切换商品：加载原图并清空参考图选择
  useEffect(() => {
    if (productId === null) {
      setProduct(null);
      setRefIds([]);
      return;
    }
    setRefIds([]);
    productsApi
      .get(productId)
      .then((d) => setProduct(d as Product))
      .catch((e: Error) => toast(e.message, "error"));
  }, [productId]);

  const loadTasks = useCallback(async () => {
    if (productId === null) {
      setTasks([]);
      setGenerated([]);
      setPolling(false);
      return;
    }
    try {
      const [t, g] = await Promise.all([
        imagesApi.listTasks(productId),
        imagesApi.listGenerated(productId, filterMarket || undefined, filterType || undefined),
      ]);
      const list = t as ImageTask[];
      setTasks(list);
      setGenerated(g as GeneratedImage[]);
      setPolling(list.some((x) => x.status === "pending" || x.status === "processing"));
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }, [productId, filterMarket, filterType]);

  // 存在进行中任务时高频轮询，否则低频刷新
  usePoll(loadTasks, polling ? 2500 : 30000, [loadTasks, polling]);

  const imageTypes = Object.entries(meta?.image_types || IMAGE_TYPE_FALLBACK);
  const marketList = meta ? Object.entries(meta.markets) : [];
  const platforms = meta?.platforms?.length ? meta.platforms : ["amazon", "temu", "独立站"];
  const aspectRatios = meta?.aspect_ratios?.length ? meta.aspect_ratios : ASPECT_FALLBACK;

  const typeLabel = (code: string) => IMAGE_TYPE_FALLBACK[code] || meta?.image_types?.[code] || code;
  const marketLabel = (code: string) => {
    const hit = marketList.find(([c]) => c === code);
    return hit ? hit[1].label : code;
  };

  const toggleRef = (id: number) => {
    setRefIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const submit = async () => {
    if (productId === null) {
      toast("请先选择商品", "error");
      return;
    }
    setSubmitting(true);
    try {
      await imagesApi.createTask({
        product_id: productId,
        image_type: imageType,
        platform: platform,
        market: market,
        aspect_ratio: aspectRatio,
        count: count,
        style: style,
        background: background,
        prompt: prompt,
        ref_image_ids: refIds,
      });
      toast("已提交生成任务");
      setPolling(true);
      await loadTasks();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSubmitting(false);
    }
  };

  const retry = async (taskId: number) => {
    try {
      await imagesApi.retry(taskId);
      toast("已重新提交任务");
      setPolling(true);
      await loadTasks();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const reviewImage = async (id: number, status: "approved" | "rejected") => {
    try {
      await imagesApi.review(id, status);
      toast(status === "approved" ? "已标记为通过" : "已标记为驳回");
      await loadTasks();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const recheck = async (id: number) => {
    try {
      const r = await imagesApi.recheck(id);
      const checked = (r as { checked?: number }).checked ?? 0;
      toast(`重新检查完成，命中 ${checked} 项`);
      await loadTasks();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const downloadAll = () => {
    if (generated.length === 0) {
      toast("当前没有可下载的图片", "error");
      return;
    }
    generated.forEach((img) => window.open(img.url, "_blank"));
    toast(`已打开 ${generated.length} 个下载链接`);
  };

  const images: ProductImage[] = product?.images || [];

  return (
    <div>
      <PageHeader
        title="图片工作台"
        desc="基于商品原图生成主图、场景图、卖点图与本地化营销图，生成后需人工审核"
      />

      {/* 顶部提示：未配置图像模型 API */}
      {imageConfigured === false && (
        <div className="mb-5 rounded-lg border-2 border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <div className="font-bold">⚠ 未配置图像模型 API</div>
          <p className="mt-1">
            当前生成的图片结果为 <b>模拟占位图</b>（非真实 AI 出图），<b>不可用于实际发布</b>。请前往
            <Link to="/settings" className="mx-1 font-semibold text-brand-700 underline">模型设置</Link>
            配置图像模型 API 后重新生成。
          </p>
        </div>
      )}

      <Card title="① 选择商品与参考原图">
        <div className="grid gap-4 lg:grid-cols-3">
          <Field label="商品">
            <select
              className="input"
              value={productId ?? ""}
              onChange={(e) => setProductId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">请选择商品…</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.sku} · {p.name}
                </option>
              ))}
            </select>
          </Field>
          <div className="lg:col-span-2 flex items-end text-xs text-slate-500">
            {product ? (
              <span>
                已选：<b className="text-slate-700">{product.sku}</b> · {product.name} · 品牌 {product.brand || "—"} ·
                原图 {images.length} 张
              </span>
            ) : (
              <span>选择商品后可在下方勾选原图作为生成参考（ref_image_ids）。</span>
            )}
          </div>
        </div>

        <div className="mt-4 border-t border-slate-100 pt-4">
          {productId === null ? (
            <Empty text="请先选择商品" />
          ) : images.length === 0 ? (
            <Empty text="该商品暂无原图，请先到商品管理上传" />
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
              {images.map((img) => {
                const checked = refIds.includes(img.id);
                return (
                  <label
                    key={img.id}
                    className={`cursor-pointer rounded-lg border p-2 ${
                      checked ? "border-brand-400 bg-brand-50" : "border-slate-200"
                    }`}
                  >
                    <div className="relative">
                      <img
                        src={img.url}
                        alt={img.filename}
                        className="h-28 w-full rounded-md object-cover"
                        loading="lazy"
                      />
                      <input
                        type="checkbox"
                        className="absolute left-1.5 top-1.5 h-4 w-4 rounded border-slate-300 text-brand-600"
                        checked={checked}
                        onChange={() => toggleRef(img.id)}
                      />
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-1">
                      <Badge>{KIND_TEXT[img.kind] || img.kind}</Badge>
                      <span className="text-[11px] text-slate-500">
                        {img.width}×{img.height}
                      </span>
                    </div>
                    <div className="mt-1 truncate text-[11px] text-slate-400" title={img.filename}>
                      {img.filename} · {fmtBytes(img.size)}
                    </div>
                  </label>
                );
              })}
            </div>
          )}
          <div className="mt-3 text-xs text-slate-400">
            已选参考图 {refIds.length} 张；不勾选时由 AI 依据商品参数自行构图。
          </div>
        </div>
      </Card>

      {/* 生成配置 */}
      <Card title="② 生成配置" className="mt-5">
        <div className="label">图片类型</div>
        <div className="flex flex-wrap gap-2">
          {imageTypes.map(([code, label]) => (
            <button
              key={code}
              className={`btn-sm ${imageType === code ? "btn-primary" : "btn-secondary"}`}
              onClick={() => setImageType(code)}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="mt-4 grid gap-4 lg:grid-cols-4">
          <Field label="平台">
            <select className="input" value={platform} onChange={(e) => setPlatform(e.target.value)}>
              {platforms.map((p) => (
                <option key={p} value={p}>
                  {PLATFORM_LABEL[p] || p}
                </option>
              ))}
            </select>
          </Field>
          <Field label="目标市场">
            <select className="input" value={market} onChange={(e) => setMarket(e.target.value)}>
              {marketList.length === 0 ? (
                <option value="US">US</option>
              ) : (
                marketList.map(([code, m]) => (
                  <option key={code} value={code}>
                    {m.label}（{code}）
                  </option>
                ))
              )}
            </select>
          </Field>
          <Field label="画幅比例">
            <select className="input" value={aspectRatio} onChange={(e) => setAspectRatio(e.target.value)}>
              {aspectRatios.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </Field>
          <Field label="生成数量" hint="单次最多 4 张">
            <select className="input" value={count} onChange={(e) => setCount(Number(e.target.value))}>
              {[1, 2, 3, 4].map((n) => (
                <option key={n} value={n}>
                  {n} 张
                </option>
              ))}
            </select>
          </Field>
          <Field label="风格 style">
            <input
              className="input"
              placeholder="如：简约高级、ins 风、极简白底"
              value={style}
              onChange={(e) => setStyle(e.target.value)}
            />
          </Field>
          <Field label="背景要求 background">
            <input
              className="input"
              placeholder="如：纯白背景 / 居家场景 / 户外草地"
              value={background}
              onChange={(e) => setBackground(e.target.value)}
            />
          </Field>
          <div className="lg:col-span-2">
            <Field label="自定义提示词 prompt">
              <textarea
                className="input h-20 resize-y"
                placeholder="补充画面元素、文案位置、构图要求等"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
              />
            </Field>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
          <div className="text-xs text-slate-500">
            当前模式：<SimBadge simulated={imageConfigured !== true} />
            {imageConfigured !== true && <span className="ml-2 text-amber-700">生成结果为模拟占位图</span>}
          </div>
          <button
            className="btn-primary"
            onClick={submit}
            disabled={submitting || productId === null}
          >
            {submitting ? "提交中…" : "开始生成"}
          </button>
        </div>
      </Card>

      {/* 任务列表 */}
      <Card
        title={`③ 生成任务（${tasks.length}）`}
        className="mt-5"
        extra={polling ? <Badge tone="info">进行中，自动刷新</Badge> : null}
      >
        {productId === null ? (
          <Empty text="请先选择商品" />
        ) : tasks.length === 0 ? (
          <Empty text="暂无生成任务，配置参数后点击「开始生成」" />
        ) : (
          <Table
            head={["类型", "市场", "画幅", "数量", "状态", "是否模拟", "模型", "耗时", "费用", "错误", "操作"]}
          >
            {tasks.map((t) => (
              <tr key={t.id}>
                <td className="td">{typeLabel(t.image_type)}</td>
                <td className="td">{marketLabel(t.market)}</td>
                <td className="td">{t.aspect_ratio}</td>
                <td className="td">{t.count}</td>
                <td className="td"><StatusBadge status={t.status} /></td>
                <td className="td"><SimBadge simulated={t.is_simulated} /></td>
                <td className="td text-xs text-slate-500">{t.model_name || "—"}</td>
                <td className="td">{t.duration_ms ? `${(t.duration_ms / 1000).toFixed(1)}s` : "—"}</td>
                <td className="td">{`$${(t.cost_usd ?? 0).toFixed(4)}`}</td>
                <td className="td max-w-[200px] text-xs text-red-600">{t.error || "—"}</td>
                <td className="td">
                  <button
                    className="btn-secondary btn-sm"
                    onClick={() => retry(t.id)}
                    disabled={t.status === "pending" || t.status === "processing"}
                  >
                    重试
                  </button>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      {/* 生成图展示区 */}
      <Card
        title={`④ 生成图（${generated.length}）`}
        className="mt-5"
        extra={
          <div className="flex items-center gap-2">
            <select
              className="input w-32 py-1 text-xs"
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
            >
              <option value="">全部类型</option>
              {imageTypes.map(([code, label]) => (
                <option key={code} value={code}>
                  {label}
                </option>
              ))}
            </select>
            <select
              className="input w-28 py-1 text-xs"
              value={filterMarket}
              onChange={(e) => setFilterMarket(e.target.value)}
            >
              <option value="">全部市场</option>
              {marketList.map(([code, m]) => (
                <option key={code} value={code}>
                  {m.label}
                </option>
              ))}
            </select>
            <button className="btn-secondary btn-sm" onClick={downloadAll} disabled={generated.length === 0}>
              批量下载
            </button>
          </div>
        }
      >
        {productId === null ? (
          <Empty text="请先选择商品" />
        ) : generated.length === 0 ? (
          <Empty text="暂无生成图片，请先提交生成任务" />
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {generated.map((img) => (
                <div
                  key={img.id}
                  className={`overflow-hidden rounded-lg border ${
                    img.is_simulated ? "border-amber-300" : "border-slate-200"
                  }`}
                >
                  <div className="bg-slate-50">
                    <img
                      src={img.url}
                      alt={img.filename}
                      className="h-44 w-full object-contain"
                      loading="lazy"
                    />
                  </div>
                  <div className="space-y-2 p-3">
                    <div className="flex flex-wrap items-center gap-1">
                      <Badge>{typeLabel(img.image_type)}</Badge>
                      <Badge>{marketLabel(img.market)}</Badge>
                      <span className="text-[11px] text-slate-500">v{img.version}</span>
                      <span className="text-[11px] text-slate-400">
                        {img.width}×{img.height}
                      </span>
                    </div>
                    <div className="flex items-center gap-1">
                      <SimBadge simulated={img.is_simulated} />
                      <Badge tone={IMAGE_STATUS_TONE[img.review_status] || "low"}>
                        {REVIEW_TEXT[img.review_status] || img.review_status}
                      </Badge>
                    </div>
                    {img.is_simulated && (
                      <div className="rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-800">
                        ⚠ 模拟占位图：未配置图像模型 API，禁止用于实际发布
                      </div>
                    )}
                    <div className="flex flex-wrap gap-1">
                      <button className="btn-secondary btn-sm" onClick={() => reviewImage(img.id, "approved")}>
                        通过
                      </button>
                      <button className="btn-danger btn-sm" onClick={() => reviewImage(img.id, "rejected")}>
                        驳回
                      </button>
                      <button className="btn-secondary btn-sm" onClick={() => recheck(img.id)}>
                        重新检查
                      </button>
                      <a
                        className="btn-secondary btn-sm"
                        href={img.url}
                        download
                        target="_blank"
                        rel="noreferrer"
                      >
                        下载
                      </a>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-500">
              批量下载会逐个打开图片链接；需要按 SKU 打包 ZIP 请前往
              <Link to="/exports" className="mx-1 font-semibold text-brand-700 underline">导出中心</Link>
              创建导出任务。
            </div>
          </>
        )}
      </Card>
    </div>
  );
};

export default ImageStudio;
