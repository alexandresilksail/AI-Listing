import React, { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { productsApi } from "../api/client";
import { Badge, Card, Empty, Field, Modal, PageHeader, Table, toast } from "../components/ui";
import type { ImportResult, Product, ProductBrief } from "../types";

/** 新建商品表单中的参数行（本地编辑态，id 由后端生成） */
interface ParamRow {
  group: string;
  key: string;
  value: string;
  unit: string;
  verified: boolean;
}

const emptyRow = (): ParamRow => ({ group: "", key: "", value: "", unit: "", verified: false });

/** 原始图片类型：与后端 image kind 取值保持一致 */
const IMAGE_KINDS: { value: string; label: string }[] = [
  { value: "main", label: "主图" },
  { value: "real", label: "实物" },
  { value: "detail", label: "细节" },
  { value: "package", label: "包装" },
  { value: "scene", label: "场景" },
  { value: "logo", label: "Logo" },
  { value: "reference", label: "参考" },
];

const kindLabel = (kind: string) => IMAGE_KINDS.find((k) => k.value === kind)?.label || kind;

const fmtTime = (s: string) => (s ? String(s).replace("T", " ").slice(0, 16) : "-");

const Products: React.FC = () => {
  const [searchParams] = useSearchParams();
  const skuFromUrl = searchParams.get("sku") || "";

  const [q, setQ] = useState(skuFromUrl);
  const [products, setProducts] = useState<ProductBrief[]>([]);
  const [listFlag, setListFlag] = useState(0);

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<Product | null>(null);
  const [detailFlag, setDetailFlag] = useState(0);

  // 右侧编辑态
  const [edit, setEdit] = useState({ name: "", brand: "", model: "", category: "", source_text: "" });
  const [newParam, setNewParam] = useState<ParamRow>(emptyRow());

  // 新建商品弹窗
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({
    sku: "", name: "", brand: "", model: "", category: "", source_text: "",
  });
  const [rows, setRows] = useState<ParamRow[]>([emptyRow()]);
  const [saving, setSaving] = useState(false);

  // 图片上传
  const [imgFile, setImgFile] = useState<File | null>(null);
  const [imgKind, setImgKind] = useState("main");
  const [uploading, setUploading] = useState(false);

  // 批量导入
  const [importing, setImporting] = useState(false);

  useEffect(() => {
    document.title = "商品管理 · PolyListing AI";
  }, []);

  // 商品列表
  useEffect(() => {
    productsApi
      .list(q)
      .then((data) => setProducts((data || []) as ProductBrief[]))
      .catch((e: Error) => toast(e.message, "error"));
  }, [q, listFlag]);

  // 支持从 URL ?sku=xxx 自动定位并选中商品
  useEffect(() => {
    if (!skuFromUrl || products.length === 0) return;
    const hit = products.find((p) => p.sku === skuFromUrl);
    if (hit) setSelectedId((prev) => (prev === hit.id ? prev : hit.id));
  }, [products, skuFromUrl]);

  // 商品详情
  useEffect(() => {
    if (selectedId === null) {
      setDetail(null);
      return;
    }
    productsApi
      .get(selectedId)
      .then((data) => setDetail(data as Product))
      .catch((e: Error) => toast(e.message, "error"));
  }, [selectedId, detailFlag]);

  // 详情加载后同步编辑态
  useEffect(() => {
    if (!detail) return;
    setEdit({
      name: detail.name || "",
      brand: detail.brand || "",
      model: detail.model || "",
      category: detail.category || "",
      source_text: detail.source_text || "",
    });
    setNewParam(emptyRow());
    setImgFile(null);
  }, [detail?.id]);

  const refreshList = () => setListFlag((n) => n + 1);
  const refreshDetail = () => setDetailFlag((n) => n + 1);

  // ---------------- 新建商品 ----------------
  const openCreate = () => {
    setForm({ sku: "", name: "", brand: "", model: "", category: "", source_text: "" });
    setRows([emptyRow()]);
    setCreateOpen(true);
  };

  const submitCreate = async () => {
    if (!form.sku.trim()) {
      toast("SKU 为必填项", "error");
      return;
    }
    setSaving(true);
    try {
      await productsApi.create({
        sku: form.sku.trim(),
        name: form.name.trim(),
        brand: form.brand.trim(),
        model: form.model.trim(),
        category: form.category.trim(),
        source_text: form.source_text,
        params: rows
          .filter((r) => r.key.trim() || r.value.trim())
          .map((r) => ({
            group: r.group.trim(),
            key: r.key.trim(),
            value: r.value.trim(),
            unit: r.unit.trim(),
            verified: r.verified,
          })),
      });
      toast("商品已创建");
      setCreateOpen(false);
      setQ("");
      refreshList();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  };

  // ---------------- 批量导入 ----------------
  const doImport = async (file: File) => {
    setImporting(true);
    try {
      const r = (await productsApi.import(file)) as ImportResult;
      const errs = r.errors || [];
      toast(`导入完成：成功 ${r.imported ?? 0} 条，跳过 ${r.skipped ?? 0} 条，错误 ${errs.length} 条`);
      if (errs.length) alert(`导入错误明细：\n${errs.join("\n")}`);
      refreshList();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setImporting(false);
    }
  };

  // ---------------- 详情操作 ----------------
  const removeProduct = async (id: number, sku: string) => {
    if (!window.confirm(`确认删除商品 ${sku}？该操作不可恢复。`)) return;
    try {
      await productsApi.remove(id);
      toast("商品已删除");
      setSelectedId(null);
      setDetail(null);
      refreshList();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const saveDetail = async () => {
    if (!detail) return;
    try {
      await productsApi.update(detail.id, {
        name: edit.name,
        brand: edit.brand,
        model: edit.model,
        category: edit.category,
        source_text: edit.source_text,
      });
      toast("商品信息已保存");
      refreshDetail();
      refreshList();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const extractParams = async () => {
    if (!detail) return;
    try {
      const r = (await productsApi.extractParams(detail.id)) as { count?: number; params?: unknown[] };
      const n = r?.count ?? r?.params?.length ?? 0;
      toast(`已从中文详情提取 ${n} 条参数`);
      refreshDetail();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const addParam = async () => {
    if (!detail) return;
    if (!newParam.key.trim()) {
      toast("参数名为必填项", "error");
      return;
    }
    try {
      await productsApi.addParams(detail.id, [
        {
          group: newParam.group.trim(),
          key: newParam.key.trim(),
          value: newParam.value.trim(),
          unit: newParam.unit.trim(),
          verified: newParam.verified,
        },
      ]);
      toast("参数已添加");
      setNewParam(emptyRow());
      refreshDetail();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const deleteParam = async (paramId: number) => {
    if (!detail) return;
    try {
      await productsApi.deleteParam(detail.id, paramId);
      toast("参数已删除");
      refreshDetail();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const uploadImage = async () => {
    if (!detail || !imgFile) {
      toast("请先选择要上传的图片", "error");
      return;
    }
    setUploading(true);
    try {
      await productsApi.uploadImage(detail.id, imgFile, imgKind);
      toast("图片已上传");
      setImgFile(null);
      refreshDetail();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setUploading(false);
    }
  };

  const deleteImage = async (imageId: number) => {
    if (!detail) return;
    if (!window.confirm("确认删除该图片？")) return;
    try {
      await productsApi.deleteImage(detail.id, imageId);
      toast("图片已删除");
      refreshDetail();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  return (
    <div>
      <PageHeader
        title="商品管理"
        desc="维护商品资料、参数与原始图片，作为多语种 Listing 生成的数据源"
        extra={
          <div className="flex items-center gap-2">
            <label className={`btn-secondary ${importing ? "opacity-50" : "cursor-pointer"}`}>
              {importing ? "导入中…" : "批量导入"}
              <input
                type="file"
                accept=".xlsx,.xls,.csv,.json"
                className="hidden"
                disabled={importing}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  e.target.value = "";
                  if (f) doImport(f);
                }}
              />
            </label>
            <button className="btn-primary" onClick={openCreate}>
              新建商品
            </button>
          </div>
        }
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[380px_1fr]">
        {/* 左：商品列表 */}
        <div>
          <Card
            title={`商品列表（${products.length}）`}
            extra={
              <button className="text-xs text-brand-700" onClick={refreshList}>
                刷新
              </button>
            }
          >
            <input
              className="input mb-3"
              placeholder="搜索 SKU / 名称 / 品牌"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
            {products.length === 0 ? (
              <Empty text="暂无商品，可新建或批量导入" />
            ) : (
              <Table head={["SKU", "名称", "品牌", "类目", "图片", "创建时间", "操作"]}>
                {products.map((p) => (
                  <tr
                    key={p.id}
                    onClick={() => setSelectedId(p.id)}
                    className={`cursor-pointer hover:bg-slate-50 ${selectedId === p.id ? "bg-brand-50" : ""}`}
                  >
                    <td className="td font-mono text-xs">
                      {p.sku}
                      {p.is_demo && (
                        <>
                          {" "}
                          <Badge tone="info">演示</Badge>
                        </>
                      )}
                    </td>
                    <td className="td max-w-[130px] truncate" title={p.name}>
                      {p.name}
                    </td>
                    <td className="td">{p.brand || "-"}</td>
                    <td className="td">{p.category || "-"}</td>
                    <td className="td">{p.image_count}</td>
                    <td className="td text-xs text-slate-500">{fmtTime(p.created_at)}</td>
                    <td className="td">
                      <button
                        className="btn-danger btn-sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          removeProduct(p.id, p.sku);
                        }}
                      >
                        删除
                      </button>
                    </td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
        </div>

        {/* 右：商品详情 */}
        <div>
          {!detail ? (
            <Card title="商品详情">
              <Empty text="请从左侧选择一个商品以查看并编辑详情" />
            </Card>
          ) : (
            <div className="space-y-5">
              <Card
                title={
                  <span className="flex items-center gap-2">
                    <span className="font-mono">{detail.sku}</span>
                    {detail.is_demo && <Badge tone="info">演示</Badge>}
                  </span>
                }
                extra={
                  <div className="flex items-center gap-2">
                    <button className="btn-secondary btn-sm" onClick={extractParams}>
                      从中文详情提取参数
                    </button>
                    <button className="btn-primary btn-sm" onClick={saveDetail}>
                      保存修改
                    </button>
                  </div>
                }
              >
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  <Field label="商品名称">
                    <input className="input" value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} />
                  </Field>
                  <Field label="品牌">
                    <input className="input" value={edit.brand} onChange={(e) => setEdit({ ...edit, brand: e.target.value })} />
                  </Field>
                  <Field label="型号">
                    <input className="input" value={edit.model} onChange={(e) => setEdit({ ...edit, model: e.target.value })} />
                  </Field>
                  <Field label="类目">
                    <input className="input" value={edit.category} onChange={(e) => setEdit({ ...edit, category: e.target.value })} />
                  </Field>
                </div>
                <div className="mt-3">
                  <Field label="中文详情（原文）" hint="多语种生成与参数提取均以此为准">
                    <textarea
                      className="input min-h-[120px]"
                      value={edit.source_text}
                      onChange={(e) => setEdit({ ...edit, source_text: e.target.value })}
                    />
                  </Field>
                </div>
              </Card>

              {/* 参数 */}
              <Card title={`商品参数（${detail.params?.length || 0}）`}>
                {!detail.params || detail.params.length === 0 ? (
                  <Empty text="暂无参数，可点击「从中文详情提取参数」或手动新增" />
                ) : (
                  <Table head={["分组", "参数名", "参数值", "单位", "已核实", "操作"]}>
                    {detail.params.map((p) => (
                      <tr key={p.id}>
                        <td className="td">{p.group || "-"}</td>
                        <td className="td font-medium">{p.key}</td>
                        <td className="td">{p.value}</td>
                        <td className="td">{p.unit || "-"}</td>
                        <td className="td">
                          {p.verified ? <Badge tone="success">已核实</Badge> : <Badge tone="low">待核实</Badge>}
                        </td>
                        <td className="td">
                          <button className="btn-danger btn-sm" onClick={() => deleteParam(p.id)}>
                            删除
                          </button>
                        </td>
                      </tr>
                    ))}
                  </Table>
                )}

                <div className="mt-4 grid grid-cols-2 gap-3 border-t border-slate-100 pt-4 md:grid-cols-6">
                  <input
                    className="input"
                    placeholder="分组"
                    value={newParam.group}
                    onChange={(e) => setNewParam({ ...newParam, group: e.target.value })}
                  />
                  <input
                    className="input"
                    placeholder="参数名"
                    value={newParam.key}
                    onChange={(e) => setNewParam({ ...newParam, key: e.target.value })}
                  />
                  <input
                    className="input"
                    placeholder="参数值"
                    value={newParam.value}
                    onChange={(e) => setNewParam({ ...newParam, value: e.target.value })}
                  />
                  <input
                    className="input"
                    placeholder="单位"
                    value={newParam.unit}
                    onChange={(e) => setNewParam({ ...newParam, unit: e.target.value })}
                  />
                  <label className="flex items-center gap-2 text-sm text-slate-600">
                    <input
                      type="checkbox"
                      checked={newParam.verified}
                      onChange={(e) => setNewParam({ ...newParam, verified: e.target.checked })}
                    />
                    已核实
                  </label>
                  <button className="btn-secondary btn-sm" onClick={addParam}>
                    新增参数
                  </button>
                </div>
              </Card>

              {/* 原始图片 */}
              <Card title={`原始图片（${detail.images?.length || 0}）`}>
                <div className="mb-4 flex flex-wrap items-end gap-3 border-b border-slate-100 pb-4">
                  <div>
                    <span className="label">选择图片</span>
                    <input
                      type="file"
                      accept="image/*"
                      className="input py-1.5"
                      onChange={(e) => setImgFile(e.target.files?.[0] || null)}
                    />
                  </div>
                  <div>
                    <span className="label">图片类型</span>
                    <select className="input" value={imgKind} onChange={(e) => setImgKind(e.target.value)}>
                      {IMAGE_KINDS.map((k) => (
                        <option key={k.value} value={k.value}>
                          {k.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <button className="btn-primary" onClick={uploadImage} disabled={uploading || !imgFile}>
                    {uploading ? "上传中…" : "上传图片"}
                  </button>
                  {imgFile && <span className="text-xs text-slate-500">已选择：{imgFile.name}</span>}
                </div>

                {!detail.images || detail.images.length === 0 ? (
                  <Empty text="暂无原始图片，上传后可用于图片生成参考" />
                ) : (
                  <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                    {detail.images.map((img) => (
                      <div key={img.id} className="rounded-lg border border-slate-200 p-2">
                        <img
                          src={img.url}
                          alt={img.filename}
                          className="h-28 w-full rounded object-cover"
                        />
                        <div className="mt-2 flex items-center justify-between">
                          <div className="min-w-0">
                            <Badge tone="low">{kindLabel(img.kind)}</Badge>
                            <div className="mt-1 truncate text-[11px] text-slate-400" title={img.filename}>
                              {img.filename}
                            </div>
                          </div>
                          <button className="btn-danger btn-sm" onClick={() => deleteImage(img.id)}>
                            删除
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </div>
          )}
        </div>
      </div>

      {/* 新建商品弹窗 */}
      <Modal open={createOpen} title="新建商品" onClose={() => setCreateOpen(false)} wide>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <Field label="SKU（必填）">
            <input className="input" value={form.sku} onChange={(e) => setForm({ ...form, sku: e.target.value })} />
          </Field>
          <Field label="商品名称">
            <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </Field>
          <Field label="品牌">
            <input className="input" value={form.brand} onChange={(e) => setForm({ ...form, brand: e.target.value })} />
          </Field>
          <Field label="型号">
            <input className="input" value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} />
          </Field>
          <Field label="类目">
            <input className="input" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
          </Field>
        </div>
        <div className="mt-3">
          <Field label="中文详情（source_text）" hint="用于多语种生成与参数提取">
            <textarea
              className="input min-h-[120px]"
              value={form.source_text}
              onChange={(e) => setForm({ ...form, source_text: e.target.value })}
            />
          </Field>
        </div>

        <div className="mt-4 border-t border-slate-100 pt-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-semibold text-slate-800">商品参数</span>
            <button className="btn-secondary btn-sm" onClick={() => setRows([...rows, emptyRow()])}>
              添加一行
            </button>
          </div>
          {rows.map((r, i) => (
            <div key={i} className="mb-2 grid grid-cols-2 items-center gap-2 md:grid-cols-6">
              <input
                className="input"
                placeholder="分组"
                value={r.group}
                onChange={(e) => setRows(rows.map((x, j) => (i === j ? { ...x, group: e.target.value } : x)))}
              />
              <input
                className="input"
                placeholder="参数名"
                value={r.key}
                onChange={(e) => setRows(rows.map((x, j) => (i === j ? { ...x, key: e.target.value } : x)))}
              />
              <input
                className="input"
                placeholder="参数值"
                value={r.value}
                onChange={(e) => setRows(rows.map((x, j) => (i === j ? { ...x, value: e.target.value } : x)))}
              />
              <input
                className="input"
                placeholder="单位"
                value={r.unit}
                onChange={(e) => setRows(rows.map((x, j) => (i === j ? { ...x, unit: e.target.value } : x)))}
              />
              <label className="flex items-center gap-2 text-sm text-slate-600">
                <input
                  type="checkbox"
                  checked={r.verified}
                  onChange={(e) => setRows(rows.map((x, j) => (i === j ? { ...x, verified: e.target.checked } : x)))}
                />
                已核实
              </label>
              <button
                className="btn-danger btn-sm"
                onClick={() => setRows(rows.length > 1 ? rows.filter((_, j) => j !== i) : [emptyRow()])}
              >
                删除
              </button>
            </div>
          ))}
        </div>

        <div className="mt-5 flex justify-end gap-2 border-t border-slate-100 pt-4">
          <button className="btn-secondary" onClick={() => setCreateOpen(false)}>
            取消
          </button>
          <button className="btn-primary" onClick={submitCreate} disabled={saving}>
            {saving ? "提交中…" : "创建商品"}
          </button>
        </div>
      </Modal>
    </div>
  );
};

export default Products;
