import React, { useEffect, useState } from "react";
import { exportsApi, imagesApi, productsApi } from "../api/client";
import { Badge, Card, Empty, Field, PageHeader, StatusBadge, Table, toast, usePoll } from "../components/ui";
import type { ExportTask, GeneratedImage, ProductBrief } from "../types";

type ExportType = "listing_csv" | "listing_xlsx" | "images_zip" | "full_package";

const TYPE_OPTIONS: { value: ExportType; label: string; desc: string }[] = [
  { value: "listing_csv", label: "文案 CSV", desc: "表格化的 Listing 标题、卖点与描述，便于批量上传" },
  { value: "listing_xlsx", label: "文案 Excel", desc: "多工作表 Excel，按市场 / 平台分表" },
  { value: "images_zip", label: "图片 ZIP 打包", desc: "按勾选的生成图片打包为 ZIP" },
  { value: "full_package", label: "完整商品内容包", desc: "文案 + SEO 关键词 + FAQ + 原图与生成图 + 两版审核报告" },
];

const TYPE_LABEL: Record<string, string> = {
  listing_csv: "文案 CSV",
  listing_xlsx: "文案 Excel",
  images_zip: "图片 ZIP",
  full_package: "完整商品包",
};

const fmtSize = (size: number) => {
  if (!size) return "—";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(2)} MB`;
};

const fmtTime = (t: string) => (t ? t.replace("T", " ").slice(0, 19) : "—");

const ExportCenter: React.FC = () => {
  const [products, setProducts] = useState<ProductBrief[]>([]);
  const [tasks, setTasks] = useState<ExportTask[]>([]);
  const [type, setType] = useState<ExportType>("listing_xlsx");
  const [productId, setProductId] = useState<number | null>(null);
  const [market, setMarket] = useState("");
  const [platform, setPlatform] = useState("");
  const [language, setLanguage] = useState("");
  const [imageIds, setImageIds] = useState<number[]>([]);
  const [images, setImages] = useState<GeneratedImage[]>([]);
  const [lastExport, setLastExport] = useState<ExportTask | null>(null);
  const [creating, setCreating] = useState(false);
  const [hasPending, setHasPending] = useState(false);

  useEffect(() => {
    productsApi.list().then((d) => setProducts(d as ProductBrief[])).catch((e: Error) => toast(e.message, "error"));
    document.title = "导出中心 · PolyListing AI";
  }, []);

  const loadTasks = () => {
    exportsApi.list()
      .then((d) => setTasks(d as ExportTask[]))
      .catch((e: Error) => toast(e.message, "error"));
  };

  usePoll(loadTasks, hasPending ? 2500 : 20000, [hasPending]);

  useEffect(() => {
    setHasPending(tasks.some((t) => t.status === "pending" || t.status === "processing"));
  }, [tasks]);

  useEffect(() => {
    if (type !== "images_zip") {
      setImages([]);
      setImageIds([]);
      return;
    }
    imagesApi.listGenerated(productId ?? undefined)
      .then((d) => setImages(d as GeneratedImage[]))
      .catch(() => setImages([]));
  }, [type, productId]);

  const toggleImage = (id: number) => {
    setImageIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const create = async () => {
    if (type === "full_package" && productId === null) {
      toast("完整商品包必须选择商品", "error");
      return;
    }
    if (type === "images_zip" && imageIds.length === 0) {
      toast("请至少勾选一张图片", "error");
      return;
    }
    setCreating(true);
    try {
      const r = (await exportsApi.create({
        type,
        product_id: productId,
        market: market || undefined,
        platform: platform || undefined,
        language: language || undefined,
        image_ids: type === "images_zip" ? imageIds : [],
      })) as ExportTask;
      setLastExport(r);
      if (r.status === "completed") toast("导出完成，可直接下载");
      else if (r.status === "failed") toast(r.error || "导出失败", "error");
      else toast("导出任务已创建");
      loadTasks();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div>
      <PageHeader title="导出中心" desc="将 Listing 文案、生成图片与审核结果批量导出为可交付文件" />

      <Card title="导出配置">
        <div className="space-y-4">
          <div>
            <span className="label">导出类型</span>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {TYPE_OPTIONS.map((o) => (
                <label
                  key={o.value}
                  className={`cursor-pointer rounded-lg border p-3 text-sm transition-colors ${
                    type === o.value ? "border-brand-500 bg-brand-50" : "border-slate-200 hover:border-brand-300"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="export-type"
                      className="h-4 w-4 border-slate-300 text-brand-600"
                      checked={type === o.value}
                      onChange={() => setType(o.value)}
                    />
                    <span className="font-medium text-slate-800">{o.label}</span>
                  </div>
                  <p className="mt-1 pl-6 text-xs text-slate-500">{o.desc}</p>
                </label>
              ))}
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-4">
            <Field label="商品" hint={type === "full_package" ? "完整商品包必填" : "留空表示导出全部商品"}>
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
            <Field label="市场过滤（可选）">
              <input
                className="input"
                placeholder="如 US / DE / JP，留空不过滤"
                value={market}
                onChange={(e) => setMarket(e.target.value)}
              />
            </Field>
            <Field label="平台过滤（可选）">
              <input
                className="input"
                placeholder="如 amazon / temu，留空不过滤"
                value={platform}
                onChange={(e) => setPlatform(e.target.value)}
              />
            </Field>
            <Field label="语言过滤（可选）">
              <input
                className="input"
                placeholder="如 en / de / ja，留空不过滤"
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
              />
            </Field>
          </div>

          {type === "images_zip" && (
            <div className="rounded-lg border border-slate-200 p-3">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-medium text-slate-700">
                  选择图片（已选 {imageIds.length} 张）
                </span>
                <div className="flex gap-2">
                  <button className="btn-secondary btn-sm" onClick={() => setImageIds(images.map((i) => i.id))}>
                    全选
                  </button>
                  <button className="btn-secondary btn-sm" onClick={() => setImageIds([])}>
                    清空
                  </button>
                </div>
              </div>
              {images.length === 0 ? (
                <Empty text="暂无生成图片，请先在图片工作台生成后重试" />
              ) : (
                <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-8">
                  {images.map((img) => (
                    <label
                      key={img.id}
                      className={`cursor-pointer overflow-hidden rounded-lg border ${
                        imageIds.includes(img.id) ? "border-brand-500 ring-1 ring-brand-400" : "border-slate-200"
                      }`}
                    >
                      <img src={img.url} alt={img.filename} className="h-20 w-full bg-slate-100 object-cover" />
                      <div className="flex items-center gap-1.5 px-2 py-1.5 text-[11px] text-slate-600">
                        <input
                          type="checkbox"
                          className="h-3.5 w-3.5 rounded border-slate-300 text-brand-600"
                          checked={imageIds.includes(img.id)}
                          onChange={() => toggleImage(img.id)}
                        />
                        <span className="truncate">{img.image_type}</span>
                      </div>
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="flex items-center gap-3">
            <button className="btn-primary" onClick={create} disabled={creating}>
              {creating ? "生成中…" : "生成导出"}
            </button>
            <span className="text-xs text-slate-400">
              完整商品包包含 Listing 文案、SEO 关键词、FAQ、原图与生成图、两版审核报告
            </span>
          </div>

          {lastExport && lastExport.status === "completed" && (
            <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
              <span>导出完成：</span>
              <span className="font-medium">{lastExport.file_name}</span>
              <a
                className="font-semibold underline"
                href={exportsApi.downloadUrl(lastExport.id)}
                target="_blank"
                rel="noreferrer"
              >
                点击下载
              </a>
            </div>
          )}
        </div>
      </Card>

      <Card title={`导出历史（${tasks.length}）`} className="mt-5">
        <Table head={["类型", "文件名", "大小", "状态", "创建时间", "错误信息", "操作"]} empty="暂无导出记录">
          {tasks.map((t) => (
            <tr key={t.id}>
              <td className="td"><Badge>{TYPE_LABEL[t.type] || t.type}</Badge></td>
              <td className="td max-w-[240px] truncate text-xs">{t.file_name || "—"}</td>
              <td className="td text-xs">{fmtSize(t.file_size)}</td>
              <td className="td"><StatusBadge status={t.status} /></td>
              <td className="td text-xs text-slate-500">{fmtTime(t.created_at)}</td>
              <td className="td max-w-[200px] text-xs text-red-600">{t.error || <span className="text-slate-400">—</span>}</td>
              <td className="td">
                {t.status === "completed" ? (
                  <a
                    className="btn-secondary btn-sm"
                    href={exportsApi.downloadUrl(t.id)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    下载
                  </a>
                ) : (
                  <span className="text-xs text-slate-400">—</span>
                )}
              </td>
            </tr>
          ))}
        </Table>
      </Card>
    </div>
  );
};

export default ExportCenter;
