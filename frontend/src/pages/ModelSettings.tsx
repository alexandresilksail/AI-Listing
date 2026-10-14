import React, { useEffect, useState } from "react";
import { settingsApi } from "../api/client";
import { Badge, Card, Empty, Field, PageHeader, Table, toast } from "../components/ui";
import type { ModelSettings } from "../types";

interface SettingsForm {
  text_api_base: string;
  text_api_key: string;
  text_model: string;
  image_api_base: string;
  image_api_key: string;
  image_model: string;
  daily_budget_usd: number;
  per_task_budget_usd: number;
  max_skus_per_task: number;
  max_upload_mb: number;
}

interface TestResult {
  ok: boolean;
  status_code?: number;
  latency_ms?: number;
  message: string;
}

interface CostLog {
  id: number;
  provider: string;
  model: string;
  purpose: string;
  status: string;
  latency_ms: number;
  cost_usd: number;
  error: string;
  created_at: string;
}

const DEFAULT_FORM: SettingsForm = {
  text_api_base: "",
  text_api_key: "",
  text_model: "",
  image_api_base: "",
  image_api_key: "",
  image_model: "",
  daily_budget_usd: 10,
  per_task_budget_usd: 2,
  max_skus_per_task: 50,
  max_upload_mb: 10,
};

const LOG_STATUS_TEXT: Record<string, string> = {
  success: "成功",
  failed: "失败",
  simulated: "模拟",
};

const LOG_STATUS_TONE: Record<string, string> = {
  success: "success",
  failed: "high",
  simulated: "info",
};

const fmtTime = (t: string) => (t ? t.replace("T", " ").slice(0, 19) : "—");

const TestPanel: React.FC<{ result: TestResult | null }> = ({ result }) => {
  if (result === null) {
    return <p className="mt-2 text-xs text-slate-400">尚未测试</p>;
  }
  return (
    <div
      className={`mt-2 rounded-lg border px-3 py-2 text-xs ${
        result.ok ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-red-200 bg-red-50 text-red-700"
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={result.ok ? "success" : "high"}>{result.ok ? "连接成功" : "连接失败"}</Badge>
        {result.status_code !== undefined && <span>HTTP {result.status_code}</span>}
        {result.latency_ms !== undefined && <span>耗时 {result.latency_ms} ms</span>}
      </div>
      <p className="mt-1 break-all">{result.message}</p>
    </div>
  );
};

const ModelSettings: React.FC = () => {
  const [settings, setSettings] = useState<ModelSettings | null>(null);
  const [form, setForm] = useState<SettingsForm>(DEFAULT_FORM);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<"" | "text" | "image">("");
  const [testResult, setTestResult] = useState<Record<"text" | "image", TestResult | null>>({ text: null, image: null });
  const [logs, setLogs] = useState<CostLog[]>([]);

  useEffect(() => {
    document.title = "模型设置 · PolyListing AI";
    reload();
    settingsApi.costLogs()
      .then((d) => setLogs(d as CostLog[]))
      .catch(() => setLogs([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const reload = async () => {
    try {
      const d = (await settingsApi.get()) as ModelSettings;
      setSettings(d);
      setForm({
        text_api_base: d.text_api_base,
        text_api_key: "",
        text_model: d.text_model,
        image_api_base: d.image_api_base,
        image_api_key: "",
        image_model: d.image_model,
        daily_budget_usd: d.daily_budget_usd,
        per_task_budget_usd: d.per_task_budget_usd,
        max_skus_per_task: d.max_skus_per_task,
        max_upload_mb: d.max_upload_mb,
      });
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      await settingsApi.update({ ...form });
      toast("设置已保存");
      await reload();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  };

  const test = async (kind: "text" | "image") => {
    setTesting(kind);
    try {
      const r = (await settingsApi.test(kind)) as TestResult;
      setTestResult((prev) => ({ ...prev, [kind]: r }));
      if (r.ok) toast("连接成功");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setTesting("");
    }
  };

  const totalCost = logs.reduce((s, l) => s + (l.cost_usd || 0), 0);

  return (
    <div>
      <PageHeader title="模型设置" desc="配置文本 / 图像模型 API、预算与并发限制，密钥仅保存在服务端" />

      <div className="mb-5 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
        <div className="font-bold">🔒 密钥安全提示</div>
        <ul className="mt-1 list-inside list-disc space-y-0.5 text-xs">
          <li>API Key 仅保存在服务端 .env 或运行时配置文件，API 输出永不明文返回，前端只显示脱敏结果。</li>
          <li>密钥不会写入日志，也不会通过接口下发给前端页面。</li>
          <li>请勿将包含密钥的配置文件提交到版本库。</li>
        </ul>
      </div>

      {settings === null ? (
        <Card>
          <Empty text="设置加载中…" />
        </Card>
      ) : (
        <>
          <div className="grid gap-5 lg:grid-cols-2">
            <Card
              title="文本模型（Listing / SEO / 审核）"
              extra={
                settings.text_configured ? <Badge tone="success">已配置</Badge> : <Badge tone="high">未配置</Badge>
              }
            >
              <div className="space-y-3">
                <Field label="API Base" hint="OpenAI 兼容接口，如 https://api.openai.com/v1">
                  <input
                    className="input"
                    placeholder="https://api.openai.com/v1"
                    value={form.text_api_base}
                    onChange={(e) => setForm({ ...form, text_api_base: e.target.value })}
                  />
                </Field>
                <Field label="API Key" hint={`当前：${settings.text_api_key_masked || "未配置"}；留空表示不修改`}>
                  <input
                    type="password"
                    className="input"
                    placeholder="留空表示不修改"
                    value={form.text_api_key}
                    onChange={(e) => setForm({ ...form, text_api_key: e.target.value })}
                  />
                </Field>
                <Field label="模型名称">
                  <input
                    className="input"
                    placeholder="gpt-4o-mini"
                    value={form.text_model}
                    onChange={(e) => setForm({ ...form, text_model: e.target.value })}
                  />
                </Field>
                <div className="flex items-center gap-2 border-t border-slate-100 pt-3">
                  <button className="btn-secondary btn-sm" onClick={() => test("text")} disabled={testing !== ""}>
                    {testing === "text" ? "测试中…" : "测试连接"}
                  </button>
                </div>
                <TestPanel result={testResult.text} />
              </div>
            </Card>

            <Card
              title="图像模型（商品图生成）"
              extra={
                settings.image_configured ? <Badge tone="success">已配置</Badge> : <Badge tone="high">未配置</Badge>
              }
            >
              <div className="space-y-3">
                <Field label="API Base" hint="OpenAI 兼容接口，如 https://api.openai.com/v1">
                  <input
                    className="input"
                    placeholder="https://api.openai.com/v1"
                    value={form.image_api_base}
                    onChange={(e) => setForm({ ...form, image_api_base: e.target.value })}
                  />
                </Field>
                <Field label="API Key" hint={`当前：${settings.image_api_key_masked || "未配置"}；留空表示不修改`}>
                  <input
                    type="password"
                    className="input"
                    placeholder="留空表示不修改"
                    value={form.image_api_key}
                    onChange={(e) => setForm({ ...form, image_api_key: e.target.value })}
                  />
                </Field>
                <Field label="模型名称">
                  <input
                    className="input"
                    placeholder="gpt-image-1"
                    value={form.image_model}
                    onChange={(e) => setForm({ ...form, image_model: e.target.value })}
                  />
                </Field>
                <div className="flex items-center gap-2 border-t border-slate-100 pt-3">
                  <button className="btn-secondary btn-sm" onClick={() => test("image")} disabled={testing !== ""}>
                    {testing === "image" ? "测试中…" : "测试连接"}
                  </button>
                </div>
                <TestPanel result={testResult.image} />
              </div>
            </Card>
          </div>

          <Card title="预算与限制" className="mt-5">
            <div className="grid gap-4 lg:grid-cols-4">
              <Field label="每日预算（USD）">
                <input
                  type="number"
                  min={0}
                  step={0.5}
                  className="input"
                  value={form.daily_budget_usd}
                  onChange={(e) => setForm({ ...form, daily_budget_usd: Number(e.target.value) || 0 })}
                />
              </Field>
              <Field label="单任务预算（USD）">
                <input
                  type="number"
                  min={0}
                  step={0.1}
                  className="input"
                  value={form.per_task_budget_usd}
                  onChange={(e) => setForm({ ...form, per_task_budget_usd: Number(e.target.value) || 0 })}
                />
              </Field>
              <Field label="单任务 SKU 上限">
                <input
                  type="number"
                  min={1}
                  className="input"
                  value={form.max_skus_per_task}
                  onChange={(e) => setForm({ ...form, max_skus_per_task: Number(e.target.value) || 1 })}
                />
              </Field>
              <Field label="上传大小上限（MB）">
                <input
                  type="number"
                  min={1}
                  className="input"
                  value={form.max_upload_mb}
                  onChange={(e) => setForm({ ...form, max_upload_mb: Number(e.target.value) || 1 })}
                />
              </Field>
            </div>
            <div className="mt-4 flex items-center gap-3 border-t border-slate-100 pt-4">
              <button className="btn-primary" onClick={save} disabled={saving}>
                {saving ? "保存中…" : "保存设置"}
              </button>
              <span className="text-xs text-slate-400">
                密钥仅保存在服务端 .env 或运行时配置文件，API 输出永不明文返回；密钥输入框留空表示不修改
              </span>
            </div>
          </Card>
        </>
      )}

      <Card
        title={`调用成本日志（${logs.length} 条，合计 $${totalCost.toFixed(4)}）`}
        className="mt-5"
        extra={
          <button className="btn-secondary btn-sm" onClick={() => settingsApi.costLogs().then((d) => setLogs(d as CostLog[])).catch((e: Error) => toast(e.message, "error"))}>
            刷新
          </button>
        }
      >
        <Table head={["服务商", "模型", "用途", "状态", "耗时", "费用", "错误信息", "调用时间"]} empty="暂无调用记录">
          {logs.map((l) => (
            <tr key={l.id}>
              <td className="td">{l.provider || "—"}</td>
              <td className="td text-xs">{l.model || "—"}</td>
              <td className="td text-xs">{l.purpose || "—"}</td>
              <td className="td">
                <Badge tone={LOG_STATUS_TONE[l.status] || "low"}>{LOG_STATUS_TEXT[l.status] || l.status}</Badge>
              </td>
              <td className="td text-xs">{l.latency_ms ? `${l.latency_ms} ms` : "—"}</td>
              <td className="td text-xs">${(l.cost_usd || 0).toFixed(4)}</td>
              <td className="td max-w-[220px] text-xs text-red-600">{l.error || <span className="text-slate-400">—</span>}</td>
              <td className="td text-xs text-slate-500">{fmtTime(l.created_at)}</td>
            </tr>
          ))}
        </Table>
      </Card>
    </div>
  );
};

export default ModelSettings;
