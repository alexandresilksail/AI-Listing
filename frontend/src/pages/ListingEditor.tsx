import React, { useEffect, useMemo, useState } from "react";
import { listingsApi, productsApi } from "../api/client";
import { Badge, Card, Empty, Field, Modal, PageHeader, SimBadge, Table, toast } from "../components/ui";
import type { ListingField, ListingVersion, Product, ProductBrief } from "../types";

/** 字段内容形态，决定使用哪种编辑控件 */
type FieldKind = "string" | "list" | "pairs" | "json";

const FIELD_LABELS: Record<string, string> = {
  title: "标题",
  bullets: "五点描述",
  description: "详情描述",
  faq: "常见问题",
  search_terms: "搜索词",
  image_alt: "图片替代文本",
  marketing_slogan: "营销标语",
};

const FIELD_HINTS: Record<string, string> = {
  bullets: "每行一条卖点",
  faq: "每行一条，格式：问题||答案",
  search_terms: "多个词用逗号分隔",
};

const fieldLabel = (f: string) => FIELD_LABELS[f] || f;
const fmtTime = (s: string) => (s ? String(s).replace("T", " ").slice(0, 16) : "-");

/** 依据后端返回的 content 判定字段形态 */
const kindOf = (content: unknown): FieldKind => {
  if (Array.isArray(content)) {
    const first = content[0];
    return Array.isArray(first) ? "pairs" : "list";
  }
  if (content !== null && typeof content === "object") return "json";
  return "string";
};

/** 任意 content → 可编辑的字符串 */
const serialize = (content: unknown): string => {
  if (Array.isArray(content)) {
    const first = content[0];
    if (Array.isArray(first)) {
      return (content as unknown[][]).map((pair) => (pair || []).map((x) => String(x ?? "")).join(" || ")).join("\n");
    }
    return (content as unknown[]).map((x) => String(x ?? "")).join("\n");
  }
  if (content === null || content === undefined) return "";
  if (typeof content === "object") return JSON.stringify(content, null, 2);
  return String(content);
};

/** 编辑字符串 → 还原为后端期望的结构 */
const deserialize = (text: string, kind: FieldKind): unknown => {
  if (kind === "list") {
    return text
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
  }
  if (kind === "pairs") {
    return text
      .split("\n")
      .map((line) => line.split("||").map((s) => s.trim()))
      .filter((arr) => arr.length > 0 && arr.some(Boolean));
  }
  if (kind === "json") {
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }
  return text;
};

interface DiffRow {
  field: string;
  old: unknown;
  new: unknown;
}

const ListingEditor: React.FC = () => {
  const [products, setProducts] = useState<ProductBrief[]>([]);
  const [productId, setProductId] = useState<number | null>(null);
  const [product, setProduct] = useState<Product | null>(null);

  const [versions, setVersions] = useState<ListingVersion[]>([]);
  const [versionId, setVersionId] = useState<number | null>(null);

  const [draft, setDraft] = useState<Record<string, string>>({});
  const [kinds, setKinds] = useState<Record<string, FieldKind>>({});
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [regenField, setRegenField] = useState("");

  // 版本对比
  const [diffOld, setDiffOld] = useState<number | null>(null);
  const [diffNew, setDiffNew] = useState<number | null>(null);
  const [diffOpen, setDiffOpen] = useState(false);
  const [diffRows, setDiffRows] = useState<DiffRow[]>([]);

  useEffect(() => {
    document.title = "文案编辑器 · PolyListing AI";
  }, []);

  useEffect(() => {
    productsApi
      .list()
      .then((data) => setProducts((data || []) as ProductBrief[]))
      .catch((e: Error) => toast(e.message, "error"));
  }, []);

  // 商品原文
  useEffect(() => {
    if (productId === null) {
      setProduct(null);
      return;
    }
    productsApi
      .get(productId)
      .then((data) => setProduct(data as Product))
      .catch((e: Error) => toast(e.message, "error"));
  }, [productId]);

  const loadVersions = (pid: number | null, keepVersion?: number) => {
    if (pid === null) {
      setVersions([]);
      setVersionId(null);
      return;
    }
    listingsApi
      .listVersions(pid)
      .then((data) => {
        const list = (data || []) as ListingVersion[];
        setVersions(list);
        if (keepVersion && list.some((v) => v.id === keepVersion)) {
          setVersionId(keepVersion);
        } else {
          const current = list.find((v) => v.is_current);
          setVersionId(current ? current.id : list.length ? list[0].id : null);
        }
      })
      .catch((e: Error) => toast(e.message, "error"));
  };

  useEffect(() => {
    loadVersions(productId);
    setDiffOld(null);
    setDiffNew(null);
  }, [productId]);

  const current = useMemo(
    () => versions.find((v) => v.id === versionId) || null,
    [versions, versionId]
  );

  // 切换版本时重建可编辑草稿
  useEffect(() => {
    if (!current) {
      setDraft({});
      setKinds({});
      setNote("");
      return;
    }
    const d: Record<string, string> = {};
    const k: Record<string, FieldKind> = {};
    (current.fields || []).forEach((f: ListingField) => {
      k[f.field] = kindOf(f.content);
      d[f.field] = serialize(f.content);
    });
    setDraft(d);
    setKinds(k);
    setNote("");
  }, [current?.id]);

  const fields: ListingField[] = current?.fields || [];

  const saveAsNewVersion = async () => {
    if (!current) return;
    const payload = fields.map((f) => ({
      field: f.field,
      content: deserialize(draft[f.field] ?? "", kinds[f.field] || "string"),
    }));
    setSaving(true);
    try {
      const r = (await listingsApi.edit(current.id, { fields: payload, note })) as ListingVersion & { id?: number };
      toast("已保存为新版本");
      const newId = r?.id ?? null;
      loadVersions(productId, newId || undefined);
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  };

  const regenerate = async (field: string) => {
    if (!current) return;
    setRegenField(field);
    try {
      const r = (await listingsApi.regenerate(current.id, field)) as {
        field?: string;
        content?: unknown;
      };
      const f = r?.field || field;
      if (r && r.content !== undefined) {
        setKinds((prev) => ({ ...prev, [f]: kindOf(r.content) }));
        setDraft((prev) => ({ ...prev, [f]: serialize(r.content) }));
      }
      toast(`字段「${fieldLabel(f)}」已重新生成`);
      loadVersions(productId, current.id);
    } catch (e) {
      // 未配置 API 时后端会返回中文错误，必须如实展示，不能伪装成功
      toast(`重新生成失败：${(e as Error).message}`, "error");
    } finally {
      setRegenField("");
    }
  };

  const runDiff = async () => {
    if (diffOld === null || diffNew === null) {
      toast("请选择要对比的两个版本", "error");
      return;
    }
    try {
      const r = (await listingsApi.diff(diffOld, diffNew)) as unknown;
      const rows: DiffRow[] = Array.isArray(r)
        ? (r as DiffRow[])
        : ((r as { changes?: DiffRow[]; diffs?: DiffRow[]; items?: DiffRow[] }).changes ||
            (r as { diffs?: DiffRow[] }).diffs ||
            (r as { items?: DiffRow[] }).items ||
            []);
      setDiffRows(rows);
      setDiffOpen(true);
      if (rows.length === 0) toast("两个版本内容一致");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  return (
    <div>
      <PageHeader
        title="文案编辑器"
        desc="原文与本地化结果左右对照，支持逐字段编辑、单字段重新生成与版本对比"
      />

      <Card title="选择商品与版本">
        <div className="flex flex-wrap items-end gap-4">
          <div className="min-w-[240px]">
            <Field label="商品">
              <select
                className="input"
                value={productId ?? ""}
                onChange={(e) => setProductId(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">请选择商品</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.sku} · {p.name}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <div className="min-w-[200px]">
            <Field label="版本对比（旧）">
              <select
                className="input"
                value={diffOld ?? ""}
                onChange={(e) => setDiffOld(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">选择旧版本</option>
                {versions.map((v) => (
                  <option key={v.id} value={v.id}>
                    v{v.version} · {v.market}/{v.language}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <div className="min-w-[200px]">
            <Field label="版本对比（新）">
              <select
                className="input"
                value={diffNew ?? ""}
                onChange={(e) => setDiffNew(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">选择新版本</option>
                {versions.map((v) => (
                  <option key={v.id} value={v.id}>
                    v{v.version} · {v.market}/{v.language}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <button className="btn-secondary" onClick={runDiff}>
            对比版本
          </button>
          <button
            className="btn-secondary"
            onClick={() => {
              loadVersions(productId, versionId ?? undefined);
            }}
          >
            刷新版本
          </button>
        </div>
      </Card>

      {productId === null ? (
        <Card title="Listing 版本" className="mt-5">
          <Empty text="请先选择一个商品" />
        </Card>
      ) : (
        <Card title={`Listing 版本（${versions.length}）`} className="mt-5">
          {versions.length === 0 ? (
            <Empty text="该商品暂无 Listing 版本，请先前往「Listing 生成」创建" />
          ) : (
            <Table head={["版本", "市场", "语言", "平台", "生成方式", "创建时间", "操作"]}>
              {versions.map((v) => (
                <tr key={v.id} className={v.id === versionId ? "bg-brand-50" : ""}>
                  <td className="td font-mono">
                    v{v.version}
                    {v.is_current && (
                      <>
                        {" "}
                        <Badge tone="success">当前</Badge>
                      </>
                    )}
                  </td>
                  <td className="td">{v.market}</td>
                  <td className="td">{v.language}</td>
                  <td className="td">{v.platform}</td>
                  <td className="td">
                    <SimBadge simulated={v.is_simulated} />
                  </td>
                  <td className="td text-xs text-slate-500">{fmtTime(v.created_at)}</td>
                  <td className="td">
                    <button className="btn-secondary btn-sm" onClick={() => setVersionId(v.id)}>
                      编辑
                    </button>
                  </td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      )}

      {current && (
        <>
          <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
            {/* 左：原文 */}
            <Card
              title="商品原文（中文）"
              extra={<Badge tone="low">{product?.sku || "-"}</Badge>}
            >
              <div className="mb-3 text-sm font-medium text-slate-800">{product?.name || "-"}</div>
              <div className="whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm leading-relaxed text-slate-700">
                {product?.source_text || "（该商品暂无中文详情）"}
              </div>
              {product?.params && product.params.length > 0 && (
                <div className="mt-4 border-t border-slate-100 pt-3">
                  <div className="label">原始参数</div>
                  <div className="space-y-1 text-xs text-slate-600">
                    {product.params.map((p) => (
                      <div key={p.id}>
                        {p.key}：{p.value}
                        {p.unit ? ` ${p.unit}` : ""}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Card>

            {/* 右：本地化结果 */}
            <Card
              title={`本地化结果 · ${current.market}/${current.language} · v${current.version}`}
              extra={<SimBadge simulated={current.is_simulated} />}
            >
              {fields.length === 0 ? (
                <Empty text="该版本暂无字段内容" />
              ) : (
                <div className="space-y-4">
                  {fields.map((f) => {
                    const kind = kinds[f.field] || "string";
                    const value = draft[f.field] ?? "";
                    return (
                      <div key={f.field}>
                        <div className="mb-1 flex items-center justify-between">
                          <span className="label mb-0">
                            {fieldLabel(f.field)}
                            <span className="ml-1 font-normal text-slate-400">({kind})</span>
                          </span>
                          <button
                            className="btn-secondary btn-sm"
                            disabled={regenField === f.field}
                            onClick={() => regenerate(f.field)}
                          >
                            {regenField === f.field ? "生成中…" : "重新生成"}
                          </button>
                        </div>
                        {kind === "string" && value.length > 120 ? (
                          <textarea
                            className="input min-h-[140px]"
                            value={value}
                            onChange={(e) => setDraft({ ...draft, [f.field]: e.target.value })}
                          />
                        ) : kind === "string" ? (
                          <input
                            className="input"
                            value={value}
                            onChange={(e) => setDraft({ ...draft, [f.field]: e.target.value })}
                          />
                        ) : (
                          <textarea
                            className="input min-h-[120px]"
                            value={value}
                            onChange={(e) => setDraft({ ...draft, [f.field]: e.target.value })}
                          />
                        )}
                        {FIELD_HINTS[f.field] && (
                          <div className="mt-1 text-xs text-slate-400">{FIELD_HINTS[f.field]}</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              <div className="mt-5 border-t border-slate-100 pt-4">
                <Field label="修改备注" hint="保存为新版本时一并记录">
                  <input
                    className="input"
                    placeholder="例如：人工调整标题长度与卖点顺序"
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                  />
                </Field>
                <div className="mt-3 flex justify-end">
                  <button className="btn-primary" onClick={saveAsNewVersion} disabled={saving}>
                    {saving ? "保存中…" : "保存为新版本"}
                  </button>
                </div>
              </div>
            </Card>
          </div>

          <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
            <Card title="本地化说明">
              <div className="whitespace-pre-wrap text-sm text-slate-700">
                {current.localization_note || "暂无本地化说明"}
              </div>
            </Card>
            <Card title="风险提示">
              <div className="whitespace-pre-wrap text-sm text-slate-700">
                {current.risk_note || "暂无风险提示"}
              </div>
            </Card>
          </div>
        </>
      )}

      {/* 版本对比弹窗 */}
      <Modal open={diffOpen} title="版本对比" onClose={() => setDiffOpen(false)} wide>
        {diffRows.length === 0 ? (
          <Empty text="两个版本内容一致，无差异" />
        ) : (
          <Table head={["字段", "旧版本", "新版本"]}>
            {diffRows.map((d, i) => (
              <tr key={`${d.field}-${i}`}>
                <td className="td font-medium">{fieldLabel(d.field)}</td>
                <td className="td whitespace-pre-wrap text-slate-500">{serialize(d.old)}</td>
                <td className="td whitespace-pre-wrap">{serialize(d.new)}</td>
              </tr>
            ))}
          </Table>
        )}
        <div className="mt-4 flex justify-end border-t border-slate-100 pt-4">
          <button className="btn-secondary" onClick={() => setDiffOpen(false)}>
            关闭
          </button>
        </div>
      </Modal>
    </div>
  );
};

export default ListingEditor;
