import React, { useEffect, useState } from "react";
import { listingsApi, metaApi, productsApi, seoApi } from "../api/client";
import {
  Badge,
  Card,
  Empty,
  Field,
  PageHeader,
  SimBadge,
  Table,
  toast,
} from "../components/ui";
import type { ListingVersion, Meta, ProductBrief, SeoKeyword, TitleCandidate } from "../types";

interface CoverageRow {
  keyword: string;
  type: string;
  in_title: boolean;
  in_bullets: boolean;
  in_description: boolean;
  occurrences: number;
  verdict: string;
}

interface CoverageResult {
  coverage_percent: number;
  keywords: CoverageRow[];
  missing_must_include: string[];
  banned_used: string[];
  note?: string;
}

const KW_TYPE_TEXT: Record<string, string> = {
  core: "核心",
  longtail: "长尾",
  scene: "场景",
  attribute: "属性",
};

const KW_TYPE_OPTIONS = [
  { value: "core", label: "核心词" },
  { value: "longtail", label: "长尾词" },
  { value: "scene", label: "场景词" },
  { value: "attribute", label: "属性词" },
];

const PLATFORM_LABEL: Record<string, string> = {
  amazon: "Amazon",
  temu: "Temu",
  独立站: "独立站",
};

const ScoreBar: React.FC<{ label: string; value: number }> = ({ label, value }) => {
  const pct = Math.max(0, Math.min(100, Math.round(value || 0)));
  return (
    <div>
      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>{label}</span>
        <span className="font-medium text-slate-700">{pct}</span>
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
        <div className="h-1.5 rounded-full bg-brand-500" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
};

const SeoStudio: React.FC = () => {
  const [products, setProducts] = useState<ProductBrief[]>([]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [productId, setProductId] = useState<number | null>(null);
  const [market, setMarket] = useState("US");
  const [keywords, setKeywords] = useState<SeoKeyword[]>([]);
  const [titles, setTitles] = useState<TitleCandidate[]>([]);
  const [versions, setVersions] = useState<ListingVersion[]>([]);
  const [versionId, setVersionId] = useState<number | null>(null);
  const [coverage, setCoverage] = useState<CoverageResult | null>(null);
  const [generating, setGenerating] = useState(false);
  const [kwText, setKwText] = useState("");
  const [kwType, setKwType] = useState("core");
  const [kwMust, setKwMust] = useState(false);
  const [kwBanned, setKwBanned] = useState(false);

  useEffect(() => {
    productsApi.list().then((d) => setProducts(d as ProductBrief[])).catch((e: Error) => toast(e.message, "error"));
    metaApi.get().then(setMeta).catch((e: Error) => toast(e.message, "error"));
  }, []);

  const loadSeo = () => {
    if (productId === null) {
      setKeywords([]);
      setTitles([]);
      return;
    }
    seoApi.keywords(productId, market).then((d) => setKeywords(d as SeoKeyword[])).catch(() => {});
    seoApi.titles(productId, market).then((d) => setTitles(d as TitleCandidate[])).catch(() => {});
  };

  useEffect(() => {
    loadSeo();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productId, market]);

  useEffect(() => {
    if (productId === null) {
      setVersions([]);
      setVersionId(null);
      return;
    }
    listingsApi.listVersions(productId).then((d) => {
      const list = d as ListingVersion[];
      setVersions(list);
      const same = list.find((v) => v.market === market);
      if (same) setVersionId(same.id);
      else setVersionId(list.length ? list[0].id : null);
    }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productId, market]);

  useEffect(() => {
    if (versionId === null) {
      setCoverage(null);
      return;
    }
    seoApi.coverage(versionId).then((d) => setCoverage(d as CoverageResult)).catch((e: Error) => {
      setCoverage(null);
      toast(e.message, "error");
    });
  }, [versionId]);

  const marketList = meta ? Object.entries(meta.markets) : [];
  const marketLabel = (code: string) => {
    const hit = marketList.find(([c]) => c === code);
    return hit ? hit[1].label : code;
  };

  const generate = async () => {
    if (productId === null) {
      toast("请先选择商品", "error");
      return;
    }
    setGenerating(true);
    try {
      const r = await seoApi.generate(productId, market);
      const t = (r as { titles?: unknown[] }).titles;
      toast(`已生成 ${Array.isArray(t) ? t.length : 0} 个标题候选`);
      loadSeo();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setGenerating(false);
    }
  };

  const toggleMust = async (kw: SeoKeyword) => {
    try {
      await seoApi.updateKeyword(kw.id, { must_include: !kw.must_include });
      loadSeo();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const toggleBanned = async (kw: SeoKeyword) => {
    try {
      await seoApi.updateKeyword(kw.id, { banned: !kw.banned });
      loadSeo();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const removeKeyword = async (id: number) => {
    try {
      await seoApi.deleteKeyword(id);
      toast("已删除关键词");
      loadSeo();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const addKeyword = async () => {
    if (productId === null) {
      toast("请先选择商品", "error");
      return;
    }
    const text = kwText.trim();
    if (!text) {
      toast("请输入关键词", "error");
      return;
    }
    try {
      await seoApi.addKeyword(
        productId,
        { keyword: text, kw_type: kwType, must_include: kwMust, banned: kwBanned },
        market
      );
      toast("已添加关键词");
      setKwText("");
      setKwMust(false);
      setKwBanned(false);
      loadSeo();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const selectTitle = async (id: number) => {
    try {
      await seoApi.selectTitle(id);
      toast("已选用该标题");
      loadSeo();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const pct = coverage ? Math.max(0, Math.min(100, Math.round(coverage.coverage_percent || 0))) : 0;

  return (
    <div>
      <PageHeader title="SEO 工作台" desc="关键词管理、标题候选评分与 Listing 覆盖率分析" />

      {/* 重要声明：无真实搜索量数据源 */}
      <div className="mb-5 rounded-lg border-2 border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
        <div className="font-bold">⚠ 数据说明</div>
        <p className="mt-1">
          本模块输出为 <b>AI 关键词建议</b>，未接入真实搜索量数据源，<b>不含搜索量 / 竞争度 / 排名数据</b>
          ；评分仅用于辅助优化，<b>不保证搜索排名或销量</b>。
        </p>
      </div>

      {/* 选择区 */}
      <Card title="分析对象">
        <div className="grid gap-4 lg:grid-cols-4">
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
          <Field label="目标市场">
            <select className="input" value={market} onChange={(e) => setMarket(e.target.value)}>
              {marketList.map(([code, m]) => (
                <option key={code} value={code}>
                  {m.label}（{code}）
                </option>
              ))}
            </select>
          </Field>
          <div className="flex items-end">
            <button className="btn-primary w-full" onClick={generate} disabled={generating || productId === null}>
              {generating ? "生成中…" : "生成关键词与标题候选"}
            </button>
          </div>
          <div className="flex items-end text-xs text-slate-400">
            生成将覆盖该市场下旧的 AI 建议，手动添加的词会保留
          </div>
        </div>
      </Card>

      {productId === null ? (
        <Card title="关键词" className="mt-5">
          <Empty text="请先选择商品与市场" />
        </Card>
      ) : (
        <>
          {/* 关键词表 */}
          <Card
            title={`关键词（${keywords.length}）`}
            className="mt-5"
            extra={<Badge tone="info">{marketLabel(market)}</Badge>}
          >
            {keywords.length === 0 ? (
              <Empty text="暂无关键词，点击「生成关键词与标题候选」" />
            ) : (
              <Table head={["关键词", "类型", "来源", "状态", "备注", "操作"]}>
                {keywords.map((k) => (
                  <tr key={k.id}>
                    <td className="td font-medium">{k.keyword}</td>
                    <td className="td">
                      <Badge>{KW_TYPE_TEXT[k.kw_type] || k.kw_type}</Badge>
                    </td>
                    <td className="td">{k.source === "manual" ? "手动添加" : "AI 建议"}</td>
                    <td className="td">
                      {k.must_include && <Badge tone="success">必须包含</Badge>}
                      {k.banned && <Badge tone="high">禁用</Badge>}
                      {!k.must_include && !k.banned && <span className="text-slate-400">—</span>}
                    </td>
                    <td className="td max-w-[240px] text-xs text-slate-500">{k.note || "—"}</td>
                    <td className="td">
                      <div className="flex flex-wrap gap-1">
                        <button
                          className={`btn-sm ${k.must_include ? "btn-primary" : "btn-secondary"}`}
                          onClick={() => toggleMust(k)}
                        >
                          {k.must_include ? "✓ 必须包含" : "必须包含"}
                        </button>
                        <button
                          className={`btn-sm ${k.banned ? "btn-danger" : "btn-secondary"}`}
                          onClick={() => toggleBanned(k)}
                        >
                          {k.banned ? "✓ 禁用" : "禁用"}
                        </button>
                        <button className="btn-secondary btn-sm" onClick={() => removeKeyword(k.id)}>
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </Table>
            )}

            {/* 手动添加 */}
            <div className="mt-4 border-t border-slate-100 pt-4">
              <div className="label">手动添加关键词</div>
              <div className="grid gap-3 lg:grid-cols-5">
                <input
                  className="input lg:col-span-2"
                  placeholder="输入关键词，如 waterproof hiking backpack"
                  value={kwText}
                  onChange={(e) => setKwText(e.target.value)}
                />
                <select className="input" value={kwType} onChange={(e) => setKwType(e.target.value)}>
                  {KW_TYPE_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
                <div className="flex items-center gap-4 text-sm">
                  <label className="flex items-center gap-1.5">
                    <input
                      type="checkbox"
                      className="h-4 w-4 rounded border-slate-300 text-brand-600"
                      checked={kwMust}
                      onChange={(e) => setKwMust(e.target.checked)}
                    />
                    必须包含
                  </label>
                  <label className="flex items-center gap-1.5">
                    <input
                      type="checkbox"
                      className="h-4 w-4 rounded border-slate-300 text-brand-600"
                      checked={kwBanned}
                      onChange={(e) => setKwBanned(e.target.checked)}
                    />
                    禁用
                  </label>
                </div>
                <button className="btn-secondary" onClick={addKeyword}>
                  添加
                </button>
              </div>
            </div>
          </Card>

          {/* 标题候选 */}
          <Card title={`标题候选（${titles.length}）`} className="mt-5">
            {titles.length === 0 ? (
              <Empty text="暂无标题候选，请先生成" />
            ) : (
              <div className="grid gap-4 lg:grid-cols-2">
                {titles.map((t) => {
                  const s = t.scores || {};
                  return (
                    <div
                      key={t.id}
                      className={`rounded-lg border p-4 ${
                        t.is_selected ? "border-brand-400 bg-brand-50" : "border-slate-200"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <p className="text-sm font-medium text-slate-800">{t.title}</p>
                        {t.is_selected && <Badge tone="success">已选用</Badge>}
                      </div>
                      <div className="mt-3 grid grid-cols-2 gap-3">
                        <ScoreBar label="综合评分" value={s.overall ?? 0} />
                        <ScoreBar label="长度合规" value={s.length ?? 0} />
                        <ScoreBar label="关键词覆盖" value={s.keyword_coverage ?? 0} />
                        <ScoreBar label="可读性" value={s.readability ?? 0} />
                      </div>
                      <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
                        <span>
                          字符数 {s.char_count ?? 0} / 上限 {s.max_chars ?? "—"}
                        </span>
                        <button
                          className={t.is_selected ? "btn-secondary btn-sm" : "btn-primary btn-sm"}
                          onClick={() => selectTitle(t.id)}
                          disabled={t.is_selected}
                        >
                          {t.is_selected ? "当前选用" : "选用"}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>

          {/* 覆盖率分析 */}
          <Card title="覆盖率分析" className="mt-5">
            <div className="grid gap-4 lg:grid-cols-4">
              <Field label="Listing 版本">
                <select
                  className="input"
                  value={versionId ?? ""}
                  onChange={(e) => setVersionId(e.target.value ? Number(e.target.value) : null)}
                >
                  <option value="">请选择版本…</option>
                  {versions.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.market} · {PLATFORM_LABEL[v.platform] || v.platform} · v{v.version}
                      {v.is_current ? " · 当前" : ""}
                    </option>
                  ))}
                </select>
              </Field>
              <div className="flex items-center gap-3">
                <div
                  className="h-20 w-20 shrink-0 rounded-full"
                  style={{
                    background: `conic-gradient(#254deb ${pct}%, #e2e8f0 ${pct}%)`,
                  }}
                >
                  <div className="grid h-full w-full place-items-center">
                    <div className="grid h-14 w-14 place-items-center rounded-full bg-white text-sm font-bold text-slate-800">
                      {pct}%
                    </div>
                  </div>
                </div>
                <div className="text-xs text-slate-500">
                  <div className="font-medium text-slate-700">关键词覆盖率</div>
                  <div>命中 {coverage?.keywords.filter((r) => r.occurrences > 0).length ?? 0} / {coverage?.keywords.length ?? 0}</div>
                </div>
              </div>
              <div className="lg:col-span-2 space-y-2">
                {(coverage?.missing_must_include || []).length > 0 && (
                  <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                    <b>⚠ 必须包含但未融入：</b>
                    {(coverage?.missing_must_include || []).join("、")}
                  </div>
                )}
                {(coverage?.banned_used || []).length > 0 && (
                  <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                    <b>⚠ 禁用词仍出现在文案中：</b>
                    {(coverage?.banned_used || []).join("、")}
                  </div>
                )}
                {(coverage?.missing_must_include || []).length === 0 &&
                  (coverage?.banned_used || []).length === 0 &&
                  coverage !== null && (
                    <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
                      ✓ 未发现必须包含词缺失或禁用词命中
                    </div>
                  )}
              </div>
            </div>

            {coverage === null ? (
              <Empty text="请选择 Listing 版本以查看覆盖率" />
            ) : (
              <div className="mt-4">
                <Table head={["关键词", "类型", "标题", "卖点", "详情", "出现次数", "结论"]}>
                  {coverage.keywords.map((r, i) => (
                    <tr key={i}>
                      <td className="td font-medium">{r.keyword}</td>
                      <td className="td">
                        <Badge>{KW_TYPE_TEXT[r.type] || r.type}</Badge>
                      </td>
                      <td className="td">{r.in_title ? "✓" : "—"}</td>
                      <td className="td">{r.in_bullets ? "✓" : "—"}</td>
                      <td className="td">{r.in_description ? "✓" : "—"}</td>
                      <td className="td">{r.occurrences}</td>
                      <td className="td">
                        <Badge tone={r.occurrences > 0 ? "success" : "low"}>{r.verdict}</Badge>
                      </td>
                    </tr>
                  ))}
                </Table>
                {coverage.note && (
                  <p className="mt-3 text-xs text-slate-400">说明：{coverage.note}</p>
                )}
                {versionId !== null && (
                  <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
                    <span>该版本生成模式：</span>
                    <SimBadge
                      simulated={versions.find((v) => v.id === versionId)?.is_simulated ?? false}
                    />
                  </div>
                )}
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
};

export default SeoStudio;
