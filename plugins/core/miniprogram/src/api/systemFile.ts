import { ApiError, apiBaseUrl, requestApi } from "@/api/client";
import { contentMd5 } from "@/utils/md5";

/**
 * 文件与附件（/api/files）：所有模块的照片、附件统一使用。
 * 上传流程：申请上传（签发直传 URL）→ 直传对象存储 → 完成上传；业务接口只提交文件 ID。
 * 见 docs/foundation-platform/file-attachment-design.md。
 *
 * **H5 兼容**：微信小程序 `chooseImage` 返回本地临时路径 + `getFileSystemManager` 读字节；
 * H5 返回 `blob:` 临时地址且**没有** `getFileSystemManager`（直接调用会
 * `uni.getFileSystemManager is not a function`）。因此读取与上传都按运行环境分两条路径：
 * - 小程序：`uni.getFileSystemManager().readFile` + `uni.request({ method: "PUT" })`；
 * - H5：`fetch(blob 地址).arrayBuffer()` + `fetch(url, { method: "PUT", body })`。
 */

export type FileItem = {
  id: string;
  file_name: string;
  name: string;
  content_type: string;
  file_kind: "image" | "document" | "video" | "other";
  file_size: number;
  width?: number | null;
  height?: number | null;
  /** 临时签名下载链接，有效期约 10 分钟 */
  url: string;
};

/** 图片选择/上传组件的单项状态；`attachment` 上传完成后为文件 ID。 */
export type ImageUploadItem = {
  status: "uploading" | "ready" | "error";
  attachment?: { id: string } | null;
  /** 本地预览地址（临时文件或 blob），仅组件内使用 */
  localPath?: string;
  error?: string;
};

type UploadTicket = {
  id: string;
  upload: { method: string; url: string; headers: Record<string, string> };
  expires_in: number;
};

const PHOTO_MAX_BYTES = 2 * 1024 * 1024;
const DOCUMENT_MAX_BYTES = 20 * 1024 * 1024;

/** 开发环境的本地存储返回相对地址，补全为后端地址；OSS 签名地址原样返回。 */
export const fileUrl = (url: string) =>
  url.startsWith("/") ? `${apiBaseUrl}${url}` : url;

export const withFileUrls = (items: FileItem[] = []) =>
  items.map((item) => ({ ...item, url: fileUrl(item.url) }));

/** 只有微信小程序提供文件系统 API；H5 走 fetch。 */
const hasFileSystem = () =>
  typeof (uni as any).getFileSystemManager === "function";

/** H5 下选择的临时地址（`blob:` 或 data 地址）取不到文件名，回退到扩展名拼装。 */
function guessFileName(path: string, contentType: string) {
  const base = path.split("/").pop() || "";
  if (base && !base.startsWith("blob") && base.includes(".")) return base;
  const ext = contentType.split("/")[1] || "bin";
  return `upload.${ext === "jpeg" ? "jpg" : ext}`;
}

async function readBytes(path: string): Promise<ArrayBuffer> {
  if (hasFileSystem()) {
    return new Promise((resolve, reject) => {
      (uni as any).getFileSystemManager().readFile({
        filePath: path,
        success: (result: any) => resolve(result.data as ArrayBuffer),
        fail: () => reject(new Error("文件读取失败，请重新选择")),
      });
    });
  }
  const blob = await fetch(path).then((response) => {
    if (!response.ok) throw new Error("文件读取失败，请重新选择");
    return response.blob();
  });
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = () => reject(new Error("文件读取失败，请重新选择"));
    reader.readAsArrayBuffer(blob);
  });
}

function imageType(bytes: Uint8Array) {
  if (bytes[0] === 0xff && bytes[1] === 0xd8) return "image/jpeg";
  if (bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e)
    return "image/png";
  if (
    String.fromCharCode(...bytes.slice(0, 4)) === "RIFF" &&
    String.fromCharCode(...bytes.slice(8, 12)) === "WEBP"
  )
    return "image/webp";
  return "";
}

async function put(
  url: string,
  headers: Record<string, string>,
  data: ArrayBuffer,
) {
  const failureMessage = (statusCode: number, body?: unknown) => {
    const payload = body && typeof body === "object"
      ? body as { message?: string; detail?: string }
      : undefined;
    return payload?.message || payload?.detail || `文件上传失败（HTTP ${statusCode}）`;
  };
  if (hasFileSystem()) {
    const uploadUrl = fileUrl(url);
    return new Promise<void>((resolve, reject) => {
      uni.request({
        url: uploadUrl,
        method: "PUT",
        header: headers,
        data,
        timeout: 60000,
        success: (response: any) =>
          response.statusCode >= 200 && response.statusCode < 300
            ? resolve()
            : reject(new ApiError(
                failureMessage(response.statusCode, response.data),
                response.statusCode,
              )),
        fail: (error: any) => {
          const message = String(error?.errMsg || "");
          const origin = uploadUrl.match(/^https?:\/\/[^/?#]+/i)?.[0];
          reject(new ApiError(/url not in domain list/i.test(message) && origin
            ? `上传域名 ${origin} 未加入微信小程序的 request 合法域名`
            : message || "文件上传失败，请检查网络"));
        },
      });
    });
  }
  // H5：`uni.request` 会把二进制体序列化成字符串，必须用原生 fetch 直传
  const response = await fetch(fileUrl(url), {
    method: "PUT",
    headers,
    body: data,
  });
  if (!response.ok) {
    let body: unknown;
    try { body = await response.clone().json(); } catch { /* OSS 等非 JSON 响应只显示状态码。 */ }
    throw new ApiError(failureMessage(response.status, body), response.status);
  }
}

/**
 * 上传任意类型的文件（作业附件等），返回文件 ID。
 * 与 `uploadPhoto` 的区别：不做图片魔数识别，contentType 由调用方给出（选择器会带回）。
 */
export async function uploadAnyFile(
  path: string,
  scene: string,
  contentType: string,
  maxBytes: number = DOCUMENT_MAX_BYTES,
  fileName?: string,
): Promise<string> {
  const buffer = await readBytes(path);
  const bytes = new Uint8Array(buffer);
  if (bytes.length > maxBytes)
    throw new Error(`文件不能超过 ${Math.floor(maxBytes / 1024 / 1024)}MB`);
  return uploadBytes(
    scene,
    contentType,
    buffer,
    bytes,
    fileName || guessFileName(path, contentType),
  );
}

/**
 * 上传一张照片（JPEG、PNG、WebP），返回文件 ID。
 * 默认沿用公共照片 2MB 上限；有独立服务端场景约束的业务可显式传入更大的上限。
 */
export async function uploadPhoto(
  path: string,
  scene: string,
  fileName?: string,
  maxBytes: number = PHOTO_MAX_BYTES,
): Promise<string> {
  const buffer = await readBytes(path);
  const bytes = new Uint8Array(buffer);
  const contentType = imageType(bytes);
  if (!contentType) throw new Error("照片只支持 JPEG、PNG、WebP");
  if (bytes.length > maxBytes)
    throw new Error(`每张照片不能超过 ${Math.floor(maxBytes / 1024 / 1024)}MB`);
  return uploadBytes(
    scene,
    contentType,
    buffer,
    bytes,
    fileName || guessFileName(path, contentType),
  );
}

async function uploadBytes(
  scene: string,
  contentType: string,
  buffer: ArrayBuffer,
  bytes: Uint8Array,
  fileName: string,
): Promise<string> {
  const ticket = await requestApi<UploadTicket>({
    method: "POST",
    path: "/api/files/upload-tickets",
    data: {
      scene,
      file_name: fileName,
      content_type: contentType,
      file_size: bytes.length,
      content_md5: contentMd5(bytes),
    },
  });
  try {
    await put(ticket.upload.url, ticket.upload.headers, buffer);
    await requestApi<FileItem>({
      method: "POST",
      path: `/api/files/${ticket.id}/complete`,
      timeout: 30000,
    });
  } catch (error) {
    await discardFile(ticket.id).catch(() => undefined);
    throw error;
  }
  return ticket.id;
}

/** 依次上传多张照片，返回文件 ID（顺序与选择一致）。 */
export async function uploadPhotos(paths: string[], scene: string) {
  const ids: string[] = [];
  for (const path of paths) ids.push(await uploadPhoto(path, scene));
  return ids;
}

/** 删除自己上传、尚未提交的文件。 */
export const discardFile = (id: string) =>
  requestApi<{ id: string; deleted: boolean }>({
    method: "DELETE",
    path: `/api/files/${encodeURIComponent(id)}`,
  });
