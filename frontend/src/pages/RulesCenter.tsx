import React, { useEffect, useState } from "react";
import { metaApi, rulesApi } from "../api/client";
import { Badge, Card, Field, Modal, PageHeader, Table, toast } from "../components/ui";
import type { Meta, Rule } from "../types";

interface RuleForm {
  platform: string;
  market: string;
  category: string;
  rule_type: string;
  code: string;
  level: string;
  description: string;
  suggestion: string;
  source: string;
  needs_verify: boolean;
  enabled: boolean;
}

const EMPTY_FORM: RuleForm = {
  platform: "amazon",
  market: "*",
  category: "*",
  rule_type: "text",
  code: "",
  level: "medium",
  description: "",
  suggestion: "",
  source: "用户自定义",
  needs_verify: true,
  enabled: true,
};

const LEVEL_TEXT: Record<string, string> = { high: "高", medium: "中", low: "低" };

const RULE_TYPE_TEXT: Record<string, string> = { text: "文案", image: "图片" };

const PLATFORM_LABEL: Record<string, string> = { amazon: "Amazon", temu: "Temu", 独立站: "独立站", "*": "通用" };

const TABS = [
  { value: "", label: "全部" },
  { value: "text", label: "文案规则" },
  { value: "image", label: "图片规则" },
];

const RulesCenter: React.FC = () => {
  const [rules, setRules] = useState<Rule[]>([]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [ruleType, setRuleType] = useState("");
  const [platformFilter, setPlatformFilter] = useState("");
  const [editing, setEditing] = useState<Rule | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<RuleForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    document.title = "规则中心 · PolyListing AI";
    metaApi.get().then(setMeta).catch(() => setMeta(null));
  }, []);

  useEffect(() => {
    rulesApi.list(ruleType || undefined, platformFilter || undefined)
      .then((d) => setRules(d as Rule[]))
      .catch((e: Error) => toast(e.message, "error"));
  }, [ruleType, platformFilter]);

  const openCreate = () => {
    setForm({ ...EMPTY_FORM, rule_type: ruleType || "text", platform: platformFilter || "amazon" });
    setCreating(true);
  };

  const openEdit = (r: Rule) => {
    setForm({
      platform: r.platform,
      market: r.market,
      category: r.category,
      rule_type: r.rule_type,
      code: r.code,
      level: r.level,
      description: r.description,
      suggestion: r.suggestion,
      source: r.source,
      needs_verify: r.needs_verify,
      enabled: r.enabled,
    });
    setEditing(r);
  };

  const closeModal = () => {
    setCreating(false);
    setEditing(null);
  };

  const reload = () => {
    rulesApi.list(ruleType || undefined, platformFilter || undefined)
      .then((d) => setRules(d as Rule[]))
      .catch((e: Error) => toast(e.message, "error"));
  };

  const submit = async () => {
    if (!form.code.trim()) {
      toast("请填写规则代码", "error");
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        await rulesApi.update(editing.id, { ...form });
        toast("规则已更新");
      } else {
        await rulesApi.create({ ...form });
        toast("规则已新增");
      }
      closeModal();
      reload();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (r: Rule) => {
    if (!window.confirm(`确认删除规则「${r.code}」？删除后相关审核将不再命中该规则。`)) return;
    try {
      await rulesApi.remove(r.id);
      toast("规则已删除");
      reload();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const platformOptions = meta?.platforms?.length ? meta.platforms : ["amazon", "temu", "独立站"];
  const marketOptions = meta ? Object.keys(meta.markets) : ["US", "DE", "JP", "SA"];

  return (
    <div>
      <PageHeader
        title="规则中心"
        desc="维护平台 / 市场 / 类目的文案与图片检查规则，供 AI 审核与人工复核使用"
        extra={<button className="btn-primary" onClick={openCreate}>新增规则</button>}
      />

      <div className="mb-5 rounded-lg border-2 border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
        <p>
          内置规则均为 <b>基线参考</b>，一切以平台官方最新规则为准；无法从官方渠道确认的内容一律标记
          <Badge tone="info">待核实</Badge>。
        </p>
        <p className="mt-1">AI 检查只能减少明显违规，<b>不能替代平台官方审核</b>，发布前请务必人工复核。</p>
      </div>

      <Card title={`规则列表（${rules.length}）`}>
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <div className="inline-flex rounded-lg border border-slate-300 p-0.5">
            {TABS.map((t) => (
              <button
                key={t.value}
                onClick={() => setRuleType(t.value)}
                className={`rounded-md px-4 py-1.5 text-sm font-medium ${
                  ruleType === t.value ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-50"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div className="w-48">
            <Field label="按平台过滤">
              <select
                className="input"
                value={platformFilter}
                onChange={(e) => setPlatformFilter(e.target.value)}
              >
                <option value="">全部平台</option>
                {platformOptions.map((p) => (
                  <option key={p} value={p}>
                    {PLATFORM_LABEL[p] || p}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <button className="btn-secondary" onClick={reload}>刷新</button>
        </div>

        <Table
          head={["平台", "市场", "类目", "类型", "规则代码", "级别", "描述", "处理建议", "来源", "核实", "启用", "操作"]}
          empty="暂无规则"
        >
          {rules.map((r) => (
            <tr key={r.id}>
              <td className="td">{PLATFORM_LABEL[r.platform] || r.platform}</td>
              <td className="td text-xs">{r.market}</td>
              <td className="td text-xs">{r.category}</td>
              <td className="td"><Badge>{RULE_TYPE_TEXT[r.rule_type] || r.rule_type}</Badge></td>
              <td className="td font-mono text-xs">{r.code}</td>
              <td className="td"><Badge tone={r.level}>{LEVEL_TEXT[r.level] || r.level}</Badge></td>
              <td className="td max-w-[240px] text-xs">{r.description || "—"}</td>
              <td className="td max-w-[200px] text-xs text-slate-500">{r.suggestion || "—"}</td>
              <td className="td text-xs text-slate-500">{r.source || "—"}</td>
              <td className="td">{r.needs_verify ? <Badge tone="info">需核实</Badge> : <span className="text-xs text-slate-400">—</span>}</td>
              <td className="td">{r.enabled ? <Badge tone="success">启用</Badge> : <Badge tone="low">停用</Badge>}</td>
              <td className="td">
                <div className="flex gap-1">
                  <button className="btn-secondary btn-sm" onClick={() => openEdit(r)}>编辑</button>
                  <button className="btn-danger btn-sm" onClick={() => remove(r)}>删除</button>
                </div>
              </td>
            </tr>
          ))}
        </Table>
      </Card>

      <Modal open={creating || editing !== null} title={editing ? `编辑规则 · ${editing.code}` : "新增规则"} onClose={closeModal} wide>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="平台">
            <select className="input" value={form.platform} onChange={(e) => setForm({ ...form, platform: e.target.value })}>
              {platformOptions.map((p) => (
                <option key={p} value={p}>{PLATFORM_LABEL[p] || p}</option>
              ))}
              <option value="*">通用</option>
            </select>
          </Field>
          <Field label="市场" hint="* 表示适用全部市场">
            <input className="input" placeholder="* / US / DE / JP" value={form.market} onChange={(e) => setForm({ ...form, market: e.target.value })} />
          </Field>
          <Field label="类目" hint="* 表示适用全部类目">
            <input className="input" placeholder="* / electronics" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
          </Field>
          <Field label="规则类型">
            <select className="input" value={form.rule_type} onChange={(e) => setForm({ ...form, rule_type: e.target.value })}>
              <option value="text">文案</option>
              <option value="image">图片</option>
            </select>
          </Field>
          <Field label="规则代码" hint="唯一标识，如 TITLE_MAX_LEN">
            <input className="input" placeholder="TITLE_MAX_LEN" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
          </Field>
          <Field label="级别">
            <select className="input" value={form.level} onChange={(e) => setForm({ ...form, level: e.target.value })}>
              <option value="high">高</option>
              <option value="medium">中</option>
              <option value="low">低</option>
            </select>
          </Field>
          <div className="sm:col-span-2">
            <Field label="规则描述">
              <textarea className="input" rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Field label="处理建议">
              <textarea className="input" rows={2} value={form.suggestion} onChange={(e) => setForm({ ...form, suggestion: e.target.value })} />
            </Field>
          </div>
          <Field label="来源">
            <input className="input" placeholder="平台官方文档 / 用户自定义" value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} />
          </Field>
          <div className="flex items-end gap-6 pb-2">
            <label className="flex items-center gap-1.5 text-sm text-slate-700">
              <input type="checkbox" className="h-4 w-4 rounded border-slate-300 text-brand-600" checked={form.needs_verify} onChange={(e) => setForm({ ...form, needs_verify: e.target.checked })} />
              需核实
            </label>
            <label className="flex items-center gap-1.5 text-sm text-slate-700">
              <input type="checkbox" className="h-4 w-4 rounded border-slate-300 text-brand-600" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
              启用
            </label>
          </div>
        </div>
        <p className="mt-3 text-xs text-slate-400">
          无法从平台官方渠道确认的规则请勾选「需核实」，审核结果中将明确提示需人工确认。
        </p>
        <div className="mt-4 flex justify-end gap-2 border-t border-slate-100 pt-4">
          <button className="btn-secondary" onClick={closeModal}>取消</button>
          <button className="btn-primary" onClick={submit} disabled={saving}>
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
      </Modal>
    </div>
  );
};

export default RulesCenter;
