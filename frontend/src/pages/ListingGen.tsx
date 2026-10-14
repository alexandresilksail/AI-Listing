import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listingsApi, metaApi, productsApi } from "../api/client";
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
  usePoll,
} from "../components/ui";
import type { ListingTask, MarketMeta, Meta, ProductBrief } from "../types";

const PLATFORM_LABEL: Record<string, string> = {
  amazon: "Amazon",
  temu: "Temu",
  独立站: "独立站（自建站 / Shopify 等）",
};

const FIELD_LABEL: Record<string, string> = {
  title: "标题",
  marketing_slogan: "营销标语",
  bullets: "核心卖点",
  description: "详情描述",
  faq: "常见问题",
  search_terms: "搜索词",
  image_alt: "图片 Alt 文本",
};

const asText = (v: unknown): string => {
  if (v === null || v === undefined) return "";
  if (typeof v === "string") return v;
  if (Array.isArray(v)) return v.map((x) => String(x)).join(" ");
  return String(v);
};

const asList = (v: unknown): string[] => {
  if (Array.isArray(v)) return v.map((x) => String(x));
  const s = asText(v);
  return s ? [s] : [];
};

const asFaq = (v: unknown): { q: string; a: string }[] => {
  if (!Array.isArray(v)) return [];
  return v.map((item) => {
    if (Array.isArray(item)) {
      return { q: String(item[0] ?? ""), a: String(item[1] ?? "") };
    }
    if (item && typeof item === "object") {
      const o = item as Record<string, unknown>;
      return { q: String(o.q ?? o.question ?? ""), a: String(o.a ?? o.answer ?? "") };
    }
    return { q: String(item), a: "" };
  });
};

const ListingGen: React.FC = () => {
  const [products, setProducts] = useState<ProductBrief[]>([]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [health, setHealth] = useState<{ text_configured: boolean } | null>(null);
  const [productId, setProductId] = useState<number | null>(null);
  const [platform, setPlatform] = useState("amazon");
  const [markets, setMarkets] = useState<string[]>([]);
  const [tasks, setTasks] = useState<ListingTask[]>([]);
  const [generating, setGenerating] = useState(false);
  const [polling, setPolling] = useState(false);
  const [detail, setDetail] = useState<ListingTask | null>(null);

  useEffect(() => {
    productsApi.list().then((d) => setProducts(d as ProductBrief[])).catch((e: Error) => toast(e.message, "error"));
    metaApi.get().then((d) => {
      setMeta(d);
      if (d.platforms && d.platforms.length) setPlatform(d.platforms[0]);
    }).catch((e: Error) => toast(e.message, "error"));
    fetch("/api/health").then((r) => r.json()).then(setHealth).catch(() => {});
  }, []);

  const refresh = () => {
    if (productId === null) {
      setTasks([]);
      return;
    }
    listingsApi
      .listTasks(productId)
      .then((d) => {
        const list = d as ListingTask[];
        setTasks(list);
        const active = list.some((t) => t.status === "pending" || t.status === "processing");
        setPolling(active);
      })
      .catch(() => {});
  };

  // 切换商品时立即加载一次任务列表
  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productId]);

  // 仅在存在进行中任务时轮询，全部结束后自动停止
  usePoll(() => {
    if (polling) refresh();
  }, 2500, [productId, polling]);

  const toggleMarket = (code: string) => {
    setMarkets((prev) => (prev.includes(code) ? prev.filter((m) => m !== code) : [...prev, code]));
  };

  const startGenerate = async () => {
    if (productId === null) {
      toast("请先选择商品", "error");
      return;
    }
    if (markets.length === 0) {
      toast("请至少选择一个目标市场", "error");
      return;
    }
    setGenerating(true);
    try {
      await listingsApi.createTasks({ product_id: productId, platform, markets });
      toast(`已提交 ${markets.length} 个市场的生成任务`);
      setPolling(true);
      refresh();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setGenerating(false);
    }
  };

  const retry = async (taskId: number) => {
    try {
      await listingsApi.retry(taskId);
      toast("任务已重新提交");
      setPolling(true);
      refresh();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const openDetail = (t: ListingTask) => {
    if (!t.version) {
      toast("该任务暂无可查看的 Listing 版本", "error");
      return;
    }
    setDetail(t);
  };

  const marketList: [string, MarketMeta][] = meta ? Object.entries(meta.markets) : [];
  const marketLabel = (code: string) => marketList.find(([c]) => c === code)?.[1]?.label ?? code;
  const simulated = health !== null && !health.text_configured;

  const fields: Record<string, unknown> = {};
  (detail?.version?.fields || []).forEach((f) => {
    fields[f.field] = f.content;
  });

  return (
    <div>
      <PageHeader
        title="Listing 生成"
        desc="选择商品、平台与目标市场，批量生成多语种 Listing 文案"
        extra={
          <Link to="/seo" className="btn-secondary btn-sm">
            一键 SEO 优化 →
          </Link>
        }
      />

      {/* 模拟模式醒目提示 */}
      {simulated && (
        <div className="mb-5 rounded-lg border-2 border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <div className="font-bold">⚠ 当前为模拟模式：未配置文本模型 API</div>
          <p className="mt-1">
            生成结果为<b>占位演示内容</b>，仅用于展示字段结构与流程，禁止直接用于实际发布。请前往
            <Link to="/settings" className="mx-1 font-semibold text-brand-700 underline">
              模型设置
            </Link>
            配置文本模型 API 后重新生成。
          </p>
        </div>
      )}

      {/* 生成配置 */}
      <Card title="生成配置">
        <div className="grid gap-4 lg:grid-cols-3">
          <Field label="商品" hint="显示 SKU + 商品名称">
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

          <Field label="目标平台">
            <select className="input" value={platform} onChange={(e) => setPlatform(e.target.value)}>
              {(meta?.platforms || []).map((p) => (
                <option key={p} value={p}>
                  {PLATFORM_LABEL[p] || p}
                </option>
              ))}
            </select>
          </Field>

          <Field label="已选市场" hint={`已选 ${markets.length} 个市场`}>
            <div className="flex flex-wrap gap-1">
              {markets.length === 0 ? (
                <span className="text-sm text-slate-400">尚未选择</span>
              ) : (
                markets.map((m) => (
                  <Badge key={m} tone="info">
                    {marketLabel(m)}
                  </Badge>
                ))
              )}
            </div>
            <button
              className="btn-secondary btn-sm mt-2"
              onClick={() => setMarkets(marketList.map(([c]) => c))}
              disabled={marketList.length === 0}
            >
              全选市场
            </button>
            <button className="btn-secondary btn-sm ml-2 mt-2" onClick={() => setMarkets([])}>
              清空
            </button>
          </Field>
        </div>

        <div className="mt-4 border-t border-slate-100 pt-4">
          <div className="label">目标市场（多选）</div>
          {marketList.length === 0 ? (
            <Empty text="正在加载市场列表…" />
          ) : (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
              {marketList.map(([code, m]) => (
                <label
                  key={code}
                  className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors ${
                    markets.includes(code)
                      ? "border-brand-400 bg-brand-50 text-brand-800"
                      : "border-slate-200 hover:bg-slate-50"
                  }`}
                >
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border-slate-300 text-brand-600"
                    checked={markets.includes(code)}
                    onChange={() => toggleMarket(code)}
                  />
                  <span>{m.label}</span>
                </label>
              ))}
            </div>
          )}
        </div>

        <div className="mt-4 flex items-center gap-3 border-t border-slate-100 pt-4">
          <button className="btn-primary" onClick={startGenerate} disabled={generating}>
            {generating ? "提交中…" : "开始生成"}
          </button>
          <button className="btn-secondary" onClick={refresh} disabled={productId === null}>
            刷新任务
          </button>
          <span className="text-xs text-slate-400">
            同一商品的平台 + 市场组合存在进行中任务时不会重复提交
          </span>
        </div>
      </Card>

      {/* 任务列表 */}
      <Card
        title="生成任务"
        className="mt-5"
        extra={<span className="text-xs text-slate-400">点击任务行查看生成的 Listing 内容</span>}
      >
        {productId === null ? (
          <Empty text="请先在上方选择商品" />
        ) : tasks.length === 0 ? (
          <Empty text="暂无生成任务，配置市场后点击「开始生成」" />
        ) : (
          <Table
            head={["市场", "语言", "状态", "是否模拟", "模型", "耗时 (ms)", "费用 ($)", "错误信息", "操作"]}
          >
            {tasks.map((t) => (
              <tr key={t.id} className="cursor-pointer hover:bg-slate-50" onClick={() => openDetail(t)}>
                <td className="td">
                  <div className="font-medium">{marketLabel(t.market)}</div>
                  <div className="text-xs text-slate-400">{t.market}</div>
                </td>
                <td className="td">{t.language}</td>
                <td className="td">
                  <StatusBadge status={t.status} />
                </td>
                <td className="td">
                  <SimBadge simulated={t.is_simulated} />
                </td>
                <td className="td text-xs text-slate-500">{t.model_name || "—"}</td>
                <td className="td">{t.duration_ms ?? 0}</td>
                <td className="td">${(t.cost_usd ?? 0).toFixed(4)}</td>
                <td className="td max-w-[220px] text-xs text-red-600">{t.error || "—"}</td>
                <td className="td">
                  <button
                    className="btn-secondary btn-sm"
                    disabled={t.status === "pending" || t.status === "processing"}
                    onClick={(e) => {
                      e.stopPropagation();
                      retry(t.id);
                    }}
                  >
                    重试
                  </button>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      {/* Listing 详情 */}
      <Modal
        open={detail !== null}
        wide
        title={
          detail
            ? `Listing 详情 · ${marketLabel(detail.market)} · ${detail.language}`
            : "Listing 详情"
        }
        onClose={() => setDetail(null)}
      >
        {detail?.version && (
          <div>
            <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg bg-slate-50 px-3 py-2">
              <SimBadge simulated={detail.version.is_simulated} />
              <Badge>平台：{PLATFORM_LABEL[detail.version.platform] || detail.version.platform}</Badge>
              <Badge>版本 v{detail.version.version}</Badge>
              <Badge>市场：{detail.version.market}</Badge>
            </div>

            {(detail.version.localization_note || detail.version.risk_note) && (
              <div className="mb-4 space-y-2">
                {detail.version.localization_note && (
                  <div className="rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-800">
                    <b>本地化说明：</b>
                    {detail.version.localization_note}
                  </div>
                )}
                {detail.version.risk_note && (
                  <div className="rounded-lg border border-amber-100 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                    <b>风险提示：</b>
                    {detail.version.risk_note}
                  </div>
                )}
              </div>
            )}

            <div className="space-y-4">
              {["title", "marketing_slogan"].map((f) =>
                fields[f] ? (
                  <div key={f}>
                    <div className="label">{FIELD_LABEL[f]}</div>
                    <p className="text-sm font-medium text-slate-800">{asText(fields[f])}</p>
                  </div>
                ) : null
              )}

              {asList(fields.bullets).length > 0 && (
                <div>
                  <div className="label">{FIELD_LABEL.bullets}</div>
                  <ol className="list-decimal space-y-1 pl-5 text-sm text-slate-700">
                    {asList(fields.bullets).map((b, i) => (
                      <li key={i}>{b}</li>
                    ))}
                  </ol>
                </div>
              )}

              {fields.description ? (
                <div>
                  <div className="label">{FIELD_LABEL.description}</div>
                  <p className="whitespace-pre-wrap text-sm text-slate-700">{asText(fields.description)}</p>
                </div>
              ) : null}

              {asFaq(fields.faq).length > 0 && (
                <div>
                  <div className="label">{FIELD_LABEL.faq}</div>
                  <ul className="space-y-2">
                    {asFaq(fields.faq).map((qa, i) => (
                      <li key={i} className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-sm">
                        <div className="font-medium text-slate-800">Q：{qa.q}</div>
                        <div className="mt-1 text-slate-600">A：{qa.a}</div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="grid gap-4 sm:grid-cols-2">
                {fields.search_terms ? (
                  <div>
                    <div className="label">{FIELD_LABEL.search_terms}</div>
                    <p className="break-all text-sm text-slate-700">{asText(fields.search_terms)}</p>
                  </div>
                ) : null}
                {fields.image_alt ? (
                  <div>
                    <div className="label">{FIELD_LABEL.image_alt}</div>
                    <p className="text-sm text-slate-700">{asText(fields.image_alt)}</p>
                  </div>
                ) : null}
              </div>
            </div>

            <div className="mt-5 flex items-center gap-3 border-t border-slate-100 pt-4 text-xs text-slate-500">
              <Link to="/seo" className="font-semibold text-brand-700 underline">
                对该 Listing 做一键 SEO 优化 →
              </Link>
              <span>请在 SEO 工作台选择对应商品与市场</span>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default ListingGen;
