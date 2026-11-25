import { defineStore } from "pinia";
import { shallowReactive } from "vue";
import { http } from "@/utils/http";

export type RecordData = Record<string, any>;
const base = "/api/mes/cnc";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: any,
  ) {
    super(
      typeof detail === "string"
        ? detail
        : detail?.message || "请求失败，请重试",
    );
  }
}

/** 复用管理端的令牌刷新和会话失效处理，图片及下载也不把令牌放入 URL。 */
export async function request(path: string, options: RequestInit = {}) {
  try {
    const result = await http.request<any>(
      (options.method || "GET").toLowerCase() as any,
      base + path,
      {
        data:
          options.body instanceof FormData
            ? options.body
            : options.body
              ? JSON.parse(String(options.body))
              : undefined,
        ...(options.body instanceof FormData
          ? { headers: { "Content-Type": undefined } }
          : {}),
        timeout: 120000,
      },
    );
    if (result.code !== 0)
      throw new ApiError(result.code, {
        message: result.message,
        ...result.data,
      });
    return result.data;
  } catch (error: any) {
    if (error instanceof ApiError) throw error;
    const response = error.response;
    throw new ApiError(response?.status || 0, {
      message:
        response?.data?.message ||
        response?.data?.detail ||
        "操作失败，请检查连接后重试",
      ...response?.data?.data,
    });
  }
}

export const jsonOptions = (body: unknown, method = "POST"): RequestInit => ({
  method,
  body: JSON.stringify(body),
});

export function binary(url: string): Promise<Blob> {
  return http.request<Blob>("get", url, {
    responseType: "blob",
    timeout: 120000,
  });
}

const assetUrls = shallowReactive<Record<string, string>>({});
let assetScope = "";
export function releaseAssets() {
  Object.values(assetUrls).forEach(URL.revokeObjectURL);
  Object.keys(assetUrls).forEach((key) => delete assetUrls[key]);
  assetScope = "";
}
export const assetUrl = (name: string) => assetUrls[name] || "";

/** 只有查看当前页识别依据时才读取其图片，不阻塞图纸与核价表单。 */
export async function loadEvidenceAssets(part: RecordData, page: RecordData) {
  const scope = `${part.id}/${part.analysis.artifact_job}`;
  if (assetScope !== scope) {
    releaseAssets();
    assetScope = scope;
  }
  const names = new Set<string>();
  for (const view of page.detail_views || []) names.add(view.image);
  for (const asset of page.ocr_assets || [])
    if (asset.asset) names.add(asset.asset);
  for (const key of ["ocr_markdown_file", "ocr_result_file"])
    if (page[key]) names.add(page[key]);
  await Promise.all(
    Array.from(names)
      .filter((name) => !assetUrls[name])
      .map(async (name) => {
        try {
          const blob = await binary(
            `${base}/parts/${part.id}/assets/${encodeURIComponent(name)}`,
          );
          if (assetScope === scope) assetUrls[name] = URL.createObjectURL(blob);
        } catch {
          /* 产物缺失时由预览区显示读取失败，原件仍可下载。 */
        }
      }),
  );
}

export async function downloadLink(event: MouseEvent) {
  const link = (event.target as HTMLElement).closest("a");
  const url = link?.getAttribute("href");
  if (!url?.startsWith(base)) return;
  event.preventDefault();
  try {
    const blob = await binary(url);
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download =
      link?.dataset.filename || url.split("/").pop() || "download";
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  } catch (error: any) {
    const { ElMessage } = await import("element-plus");
    ElMessage.error(error.message || "下载失败，请重试");
  }
}

export const useWorkbench = defineStore("mes-cnc-workbench", {
  state: () => ({
    parts: [] as RecordData[],
    current: null as RecordData | null,
  }),
  actions: {
    async refreshList(search = "") {
      this.parts = await request("/parts?search=" + encodeURIComponent(search));
    },
    async load(id: string) {
      const part = await request("/parts/" + id);
      if (assetScope !== `${part.id}/${part.analysis.artifact_job}`)
        releaseAssets();
      this.current = part;
    },
  },
});
