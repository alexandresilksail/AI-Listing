import axios from "axios";

const TOKEN_KEY = "pl_api_token";

/** 获取 API 访问令牌：优先 localStorage（运行时输入），其次构建时环境变量。 */
export function getApiToken(): string {
  return (
    localStorage.getItem(TOKEN_KEY) ||
    (import.meta.env.VITE_API_TOKEN as string | undefined) ||
    ""
  );
}

export function setApiToken(token: string): void {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

const client = axios.create({ baseURL: "/api", timeout: 60000 });

// 请求拦截：携带 API 令牌（生产模式后端默认拒绝未授权请求）
client.interceptors.request.use((config) => {
  const token = getApiToken();
  if (token) {
    config.headers["X-API-Token"] = token;
  }
  return config;
});

client.interceptors.response.use(
  (r) => r,
  (err) => {
    // 401：提示输入访问令牌并存入 localStorage，刷新后生效
    if (err?.response?.status === 401 && !getApiToken()) {
      const token = window.prompt(
        "后端要求访问令牌（PL_API_TOKEN）。请输入令牌（将保存在本浏览器 localStorage）：",
      );
      if (token && token.trim()) {
        setApiToken(token.trim());
        window.location.reload();
        return new Promise(() => {}); // 等待刷新，不再继续本次请求
      }
    }
    const msg = err?.response?.data?.detail || err?.message || "请求失败";
    return Promise.reject(new Error(typeof msg === "string" ? msg : JSON.stringify(msg)));
  }
);

export default client;

// ---------------- 商品 ----------------
export const productsApi = {
  list: (q = "") => client.get("/products", { params: { q } }).then((r) => r.data),
  get: (id: number) => client.get(`/products/${id}`).then((r) => r.data),
  create: (data: unknown) => client.post("/products", data).then((r) => r.data),
  update: (id: number, data: unknown) => client.patch(`/products/${id}`, data).then((r) => r.data),
  remove: (id: number) => client.delete(`/products/${id}`).then((r) => r.data),
  addParams: (id: number, params: unknown[]) =>
    client.post(`/products/${id}/params`, params).then((r) => r.data),
  deleteParam: (id: number, paramId: number) =>
    client.delete(`/products/${id}/params/${paramId}`).then((r) => r.data),
  extractParams: (id: number) =>
    client.post(`/products/${id}/extract-params`).then((r) => r.data),
  uploadImage: (id: number, file: File, kind: string) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("kind", kind);
    return client.post(`/products/${id}/images`, fd).then((r) => r.data);
  },
  deleteImage: (id: number, imageId: number) =>
    client.delete(`/products/${id}/images/${imageId}`).then((r) => r.data),
  import: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return client.post("/products/import", fd).then((r) => r.data);
  },
};

// ---------------- Listing ----------------
export const listingsApi = {
  createTasks: (data: unknown) => client.post("/listings/tasks", data).then((r) => r.data),
  listTasks: (productId?: number, status?: string) =>
    client.get("/listings/tasks", { params: { product_id: productId, status } }).then((r) => r.data),
  retry: (taskId: number) =>
    client.post(`/listings/tasks/${taskId}/retry`).then((r) => r.data),
  listVersions: (productId: number) =>
    client.get("/listings/versions", { params: { product_id: productId } }).then((r) => r.data),
  edit: (versionId: number, data: unknown) =>
    client.post(`/listings/versions/${versionId}/edit`, data).then((r) => r.data),
  regenerate: (versionId: number, field: string) =>
    client.post(`/listings/versions/${versionId}/regenerate`, null, { params: { field } }).then((r) => r.data),
  review: (versionId: number) =>
    client.post(`/listings/versions/${versionId}/review`).then((r) => r.data),
  diff: (oldId: number, newId: number) =>
    client.get(`/listings/diff/${oldId}/${newId}`).then((r) => r.data),
};

// ---------------- SEO ----------------
export const seoApi = {
  generate: (productId: number, market: string) =>
    client.post("/seo/generate", { product_id: productId, market }).then((r) => r.data),
  keywords: (productId: number, market?: string) =>
    client.get("/seo/keywords", { params: { product_id: productId, market } }).then((r) => r.data),
  addKeyword: (productId: number, kw: unknown, market: string) =>
    client.post("/seo/keywords", kw, { params: { market } }).then((r) => r.data),
  updateKeyword: (id: number, data: { must_include?: boolean; banned?: boolean }) =>
    client.patch(`/seo/keywords/${id}`, null, { params: data }).then((r) => r.data),
  deleteKeyword: (id: number) => client.delete(`/seo/keywords/${id}`).then((r) => r.data),
  titles: (productId: number, market?: string) =>
    client.get("/seo/titles", { params: { product_id: productId, market } }).then((r) => r.data),
  selectTitle: (id: number) => client.post(`/seo/titles/${id}/select`).then((r) => r.data),
  coverage: (versionId: number) =>
    client.get(`/seo/coverage/${versionId}`).then((r) => r.data),
};

// ---------------- 图片 ----------------
export const imagesApi = {
  createTask: (data: unknown) => client.post("/images/tasks", data).then((r) => r.data),
  listTasks: (productId?: number, status?: string) =>
    client.get("/images/tasks", { params: { product_id: productId, status } }).then((r) => r.data),
  retry: (taskId: number) => client.post(`/images/tasks/${taskId}/retry`).then((r) => r.data),
  listGenerated: (productId?: number, market?: string, imageType?: string) =>
    client.get("/images/generated", {
      params: { product_id: productId, market: market, image_type: imageType },
    }).then((r) => r.data),
  review: (imageId: number, reviewStatus: string) =>
    client.patch(`/images/generated/${imageId}`, { review_status: reviewStatus }).then((r) => r.data),
  recheck: (imageId: number) => client.post(`/images/generated/${imageId}/recheck`).then((r) => r.data),
};

// ---------------- 审核 ----------------
export const reviewsApi = {
  list: (params: { target_type?: string; product_id?: number; level?: string; status?: string }) =>
    client.get("/reviews", { params }).then((r) => r.data),
  patch: (id: number, status: string) =>
    client.patch(`/reviews/${id}`, { status }).then((r) => r.data),
  summary: () => client.get("/reviews/summary").then((r) => r.data),
};

// ---------------- 任务 ----------------
export const tasksApi = {
  overview: () => client.get("/tasks/overview").then((r) => r.data),
  retryListing: (id: number) => client.post(`/tasks/listing/${id}/retry`).then((r) => r.data),
  retryImage: (id: number) => client.post(`/tasks/image/${id}/retry`).then((r) => r.data),
};

// ---------------- 导出 ----------------
export const exportsApi = {
  create: (data: unknown) => client.post("/exports", data).then((r) => r.data),
  list: () => client.get("/exports").then((r) => r.data),
  downloadUrl: (id: number) => `/api/files/export/${id}`,
};

// ---------------- 设置 ----------------
export const settingsApi = {
  get: () => client.get("/settings").then((r) => r.data),
  update: (data: unknown) => client.put("/settings", data).then((r) => r.data),
  test: (kind: string) => client.post("/settings/test", null, { params: { kind } }).then((r) => r.data),
  costLogs: () => client.get("/settings/cost-logs").then((r) => r.data),
};

// ---------------- 规则 ----------------
export const rulesApi = {
  list: (ruleType?: string, platform?: string) =>
    client.get("/rules", { params: { rule_type: ruleType, platform: platform } }).then((r) => r.data),
  create: (data: unknown) => client.post("/rules", data).then((r) => r.data),
  update: (id: number, data: unknown) => client.patch(`/rules/${id}`, data).then((r) => r.data),
  remove: (id: number) => client.delete(`/rules/${id}`).then((r) => r.data),
};

// ---------------- 演示 / 元数据 ----------------
export const demoApi = {
  seed: () => client.post("/demo/seed").then((r) => r.data),
};

export const metaApi = {
  get: () => client.get("/meta").then((r) => r.data as import("../types").Meta),
  dashboard: () => client.get("/tasks/overview").then((r) => r.data),
};

export const dashboardApi = {
  get: () => client.get("/reviews/summary").then((r) => r.data),
};
