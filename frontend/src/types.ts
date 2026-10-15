/** 与后端 schemas.py 对应的 TypeScript 类型。 */

export interface ProductParam {
  id: number;
  group: string;
  key: string;
  value: string;
  unit: string;
  verified: boolean;
  source: string;
}

export interface ProductImage {
  id: number;
  kind: string;
  filename: string;
  mime: string;
  size: number;
  width: number;
  height: number;
  url: string;
  created_at: string;
}

export interface Product {
  id: number;
  sku: string;
  name: string;
  brand: string;
  model: string;
  category: string;
  source_text: string;
  status: string;
  is_demo: boolean;
  params: ProductParam[];
  images: ProductImage[];
  created_at: string;
  updated_at: string;
}

export interface ProductBrief {
  id: number;
  sku: string;
  name: string;
  brand: string;
  category: string;
  image_count: number;
  is_demo: boolean;
  created_at: string;
}

export interface ImportResult {
  imported: number;
  skipped: number;
  errors: string[];
  product_ids: number[];
}

export interface ListingField {
  field: string;
  content: unknown;
}

export interface ListingVersion {
  id: number;
  product_id: number;
  platform: string;
  market: string;
  language: string;
  version: number;
  is_current: boolean;
  is_simulated: boolean;
  source: string;
  localization_note: string;
  risk_note: string;
  fields: ListingField[];
  created_at: string;
}

export interface ListingTask {
  id: number;
  product_id: number;
  product_sku: string;
  platform: string;
  market: string;
  language: string;
  status: string;
  is_simulated: boolean;
  model_name: string;
  error: string;
  cost_usd: number | null; // null = 费用未知（模型不在价格表）
  duration_ms: number;
  epoch: number; // 任务版本号（提交/重试递增）
  created_at: string;
  updated_at: string;
  version: ListingVersion | null;
}

export interface SeoKeyword {
  id: number;
  keyword: string;
  kw_type: string;
  source: string;
  must_include: boolean;
  banned: boolean;
  note: string;
  market: string;
  language: string;
}

export interface TitleCandidate {
  id: number;
  title: string;
  scores: Record<string, number>;
  is_selected: boolean;
  market: string;
  language: string;
  platform: string;
}

export interface GeneratedImage {
  id: number;
  task_id: number;
  product_id: number;
  image_type: string;
  market: string;
  language: string;
  filename: string;
  url: string;
  width: number;
  height: number;
  is_simulated: boolean;
  version: number;
  review_status: string;
  created_at: string;
}

export interface ImageTask {
  id: number;
  product_id: number;
  product_sku: string;
  image_type: string;
  platform: string;
  market: string;
  language: string;
  aspect_ratio: string;
  count: number;
  status: string;
  is_simulated: boolean;
  model_name: string;
  error: string;
  cost_usd: number | null; // null = 费用未知（模型不在价格表）
  duration_ms: number;
  epoch: number; // 任务版本号（提交/重试递增）
  created_at: string;
  updated_at: string;
  images: GeneratedImage[];
}

export interface ReviewItem {
  id: number;
  target_type: string;
  target_id: number;
  product_id: number;
  rule_code: string;
  level: string;
  reason: string;
  location: string;
  suggestion: string;
  needs_manual: boolean;
  status: string;
  created_at: string;
}

export interface Rule {
  id: number;
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
  updated_at: string;
}

export interface ExportTask {
  id: number;
  type: string;
  params: Record<string, unknown>;
  status: string;
  file_name: string;
  file_size: number;
  error: string;
  created_at: string;
  finished_at: string | null;
  download_url: string;
}

export interface Dashboard {
  products: number;
  demo_products: number;
  listing_tasks: TaskStatus;
  image_tasks: TaskStatus;
  generated_images: number;
  simulated_images: number;
  open_reviews_high: number;
  open_reviews_total: number;
  text_configured: boolean;
  image_configured: boolean;
  today_cost_usd: number;
  daily_budget_usd: number;
}

export interface TaskOverview {
  listing_tasks: TaskStatus;
  image_tasks: TaskStatus;
  today_spend_usd: number;
  today_unknown_cost_calls: number;
}

export interface TaskStatus {
  pending: number;
  processing: number;
  completed: number;
  failed: number;
  partial: number;
}

export interface ModelSettings {
  text_configured: boolean;
  image_configured: boolean;
  text_api_base: string;
  text_api_key_masked: string;
  text_model: string;
  image_api_base: string;
  image_api_key_masked: string;
  image_model: string;
  daily_budget_usd: number;
  per_task_budget_usd: number;
  max_skus_per_task: number;
  max_upload_mb: number;
}

export interface MarketMeta {
  language: string;
  label: string;
  rtl: boolean;
}

export interface Meta {
  markets: Record<string, MarketMeta>;
  platforms: string[];
  image_types: Record<string, string>;
  aspect_ratios: string[];
}
