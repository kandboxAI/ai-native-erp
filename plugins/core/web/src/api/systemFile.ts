import { http } from "@/utils/http/index";
import { contentMd5 } from "@/utils/md5";

/**
 * 文件与附件（/api/files）：所有模块的附件、课件统一使用。
 * 上传流程：申请上传（签发直传 URL）→ 浏览器直传对象存储 → 完成上传；业务表单只提交文件 ID。
 * 见 docs/foundation-platform/file-attachment-design.md。
 */

type DataResult<T> = { code: number; message: string; data: T };

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

type UploadTicket = {
  id: string;
  upload: { method: string; url: string; headers: Record<string, string> };
  expires_in: number;
};

/** 上传场景由后端登记，例如 courseware、physical_exam_attachment。 */
export async function uploadFile(file: File, scene: string): Promise<FileItem> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  const ticket = await http.request<DataResult<UploadTicket>>(
    "post",
    "/api/files/upload-tickets",
    {
      data: {
        scene,
        file_name: file.name,
        content_type: file.type || "application/octet-stream",
        file_size: file.size,
        content_md5: contentMd5(bytes)
      }
    }
  );
  const { id, upload } = ticket.data;
  const response = await fetch(upload.url, {
    method: upload.method,
    headers: upload.headers,
    body: bytes
  });
  if (!response.ok) {
    await discardFile(id).catch(() => undefined);
    throw new Error("文件上传失败，请重试");
  }
  const completed = await http.request<DataResult<FileItem>>(
    "post",
    `/api/files/${id}/complete`
  );
  return completed.data;
}

/** 删除自己上传、尚未提交的文件。 */
export const discardFile = (id: string) =>
  http.request<DataResult<{ id: string; deleted: boolean }>>(
    "delete",
    `/api/files/${id}`
  );

/** 获取文件的临时签名下载链接（后端按业务单据鉴权）。 */
export const getFileUrl = (id: string) =>
  http.request<DataResult<FileItem>>("get", `/api/files/${id}/url`);

type SelectedFile = {
  name: string;
  raw?: File;
  response?: unknown;
};

const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp"];

/**
 * el-upload 的文件列表 → 文件 ID：已保存的文件（response.id，来自后端附件）原样保留，新选的校验后直传。
 * 默认按照片校验（JPEG、PNG、WebP，单张 2MB）；业务表单只提交返回的 ID。
 */
export async function uploadSelectedFiles(
  files: SelectedFile[],
  scene: string,
  { maxBytes = 2 * 1024 * 1024, types = PHOTO_TYPES } = {}
): Promise<string[]> {
  for (const file of files) {
    const saved = (file.response as { id?: string } | undefined)?.id;
    if (
      !saved &&
      (!file.raw || file.raw.size > maxBytes || !types.includes(file.raw.type))
    ) {
      throw new Error(
        `文件“${file.name}”须为 ${types.map(t => t.split("/")[1].toUpperCase()).join("、")}，且不超过 ${Math.round(maxBytes / 1024 / 1024)}MB`
      );
    }
  }
  const ids: string[] = [];
  for (const file of files) {
    const saved = (file.response as { id?: string } | undefined)?.id;
    ids.push(saved || (await uploadFile(file.raw as File, scene)).id);
  }
  return ids;
}

/** 后端返回的附件 → el-upload 文件列表（response.id 记录文件 ID）。 */
export const toUploadFiles = (items: FileItem[] = []) =>
  items.map(item => ({
    name: item.name || item.file_name,
    url: item.url,
    response: { id: item.id }
  }));
