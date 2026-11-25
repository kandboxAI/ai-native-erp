import { appStore } from "@/store/app";
import {
  ApiError,
  apiBaseUrl,
  refreshApiSession,
  redirectToLogin,
} from "./client";

export interface StreamEvent {
  event: string;
  data: Record<string, unknown>;
}

/** 微信运行时不依赖 TextDecoder；保留跨网络分块的 UTF-8 字节。 */
export class Utf8ChunkDecoder {
  private pending = new Uint8Array();
  decode(buffer: ArrayBuffer): string {
    const incoming = new Uint8Array(buffer);
    const bytes = new Uint8Array(this.pending.length + incoming.length);
    bytes.set(this.pending);
    bytes.set(incoming, this.pending.length);
    let index = 0,
      text = "";
    while (index < bytes.length) {
      const first = bytes[index]!;
      const size =
        first < 0x80
          ? 1
          : first >= 0xc2 && first <= 0xdf
            ? 2
            : first >= 0xe0 && first <= 0xef
              ? 3
              : first >= 0xf0 && first <= 0xf4
                ? 4
                : 0;
      if (!size) throw new ApiError("回答数据编码异常，请重试");
      if (index + size > bytes.length) break;
      let point =
        first &
        (size === 1 ? 0x7f : size === 2 ? 0x1f : size === 3 ? 0x0f : 0x07);
      for (let offset = 1; offset < size; offset++) {
        const byte = bytes[index + offset]!;
        if ((byte & 0xc0) !== 0x80)
          throw new ApiError("回答数据编码异常，请重试");
        point = (point << 6) | (byte & 0x3f);
      }
      if (
        (size === 2 && point < 0x80) ||
        (size === 3 && point < 0x800) ||
        (size === 4 && point < 0x10000) ||
        point > 0x10ffff ||
        (point >= 0xd800 && point <= 0xdfff)
      ) {
        throw new ApiError("回答数据编码异常，请重试");
      }
      text += String.fromCodePoint(point);
      index += size;
    }
    this.pending = bytes.slice(index);
    return text;
  }
  finish() {
    if (this.pending.length) throw new ApiError("回答数据未完整接收，请重试");
  }
}

/** SSE 帧与 UTF-8 字符可以跨任意网络分块；快照替换避免重试后的重复文字。 */
export class EventStreamReader {
  private pending = "";
  private decoder = new Utf8ChunkDecoder();
  done = false;
  constructor(private receive: (event: StreamEvent) => void) {}
  feed(buffer: ArrayBuffer) {
    this.feedText(this.decoder.decode(buffer));
  }
  feedText(text: string) {
    this.pending += text;
    if (this.pending.length > 2 * 1024 * 1024)
      throw new ApiError("回答片段过大，请缩小问题范围");
    let match: RegExpMatchArray | null;
    while ((match = this.pending.match(/\r?\n\r?\n/))) {
      const frame = this.pending.slice(0, match.index);
      this.pending = this.pending.slice((match.index || 0) + match[0].length);
      let event = "message";
      const data: string[] = [];
      for (const line of frame.split(/\r?\n/)) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:"))
          data.push(line.slice(5).replace(/^ /, ""));
      }
      if (!data.length) continue;
      let payload: Record<string, unknown>;
      try {
        payload = JSON.parse(data.join("\n"));
      } catch {
        throw new ApiError("回答数据格式异常，请重试");
      }
      if (!payload || typeof payload !== "object" || Array.isArray(payload))
        throw new ApiError("回答数据格式异常，请重试");
      if (event === "error") {
        const code = typeof payload.code === "number" ? payload.code : 0;
        throw new ApiError(
          String(payload.message || "本轮未完成，请重试"),
          code,
        );
      }
      this.receive({ event, data: payload });
      if (event === "done") this.done = true;
    }
  }
  finish() {
    this.decoder.finish();
    if (!this.done) throw new ApiError("回答连接已中断，请重新发送问题");
  }
}

interface ChunkedRequestTask extends UniApp.RequestTask {
  onChunkReceived?: (callback: (result: { data: ArrayBuffer }) => void) => void;
}

export function requestEventStream(
  path: string,
  receive: (event: StreamEvent) => void,
) {
  let cancelled = false;
  let stop: (() => void) | undefined;
  let rejectCancelled: ((reason: Error) => void) | undefined;
  let useFetch = false;
  // #ifdef H5
  useFetch = true;
  // #endif

  async function once(token: string) {
    const parser = new EventStreamReader(receive);
    if (useFetch) {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 240000);
      stop = () => controller.abort();
      try {
        const response = await fetch(`${apiBaseUrl}${path}`, {
          headers: {
            Authorization: `Bearer ${token}`,
            Accept: "text/event-stream",
          },
          signal: controller.signal,
        });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new ApiError(
            body.message || body.detail || "智能体连接失败",
            response.status,
          );
        }
        if (!response.body) throw new ApiError("当前浏览器不支持流式接收");
        const reader = response.body.getReader();
        try {
          while (!cancelled) {
            const part = await reader.read();
            if (part.done) break;
            parser.feed(
              part.value.buffer.slice(
                part.value.byteOffset,
                part.value.byteOffset + part.value.byteLength,
              ) as ArrayBuffer,
            );
          }
          if (!cancelled) parser.finish();
        } finally {
          await reader.cancel().catch(() => undefined);
          reader.releaseLock();
        }
      } finally {
        clearTimeout(timeout);
      }
      return;
    }
    await new Promise<void>((resolve, reject) => {
      rejectCancelled = reject;
      let status = 0,
        failed = false;
      let task: ChunkedRequestTask;
      const fail = (error: Error) => {
        if (failed) return;
        failed = true;
        reject(error);
        task?.abort();
      };
      task = uni.request({
        url: `${apiBaseUrl}${path}`,
        method: "GET",
        enableChunked: true,
        header: {
          Authorization: `Bearer ${token}`,
          Accept: "text/event-stream",
        },
        timeout: 240000,
        dataType: "text",
        responseType: "arraybuffer",
        success: (result) => {
          if (failed) return;
          if (result.statusCode < 200 || result.statusCode >= 300) {
            reject(new ApiError("智能体连接失败，请重试", result.statusCode));
            return;
          }
          try {
            parser.finish();
            resolve();
          } catch (error) {
            reject(error);
          }
        },
        fail: () =>
          fail(
            new ApiError(cancelled ? "已停止接收回答" : "回答连接中断，请重试"),
          ),
      });
      stop = () => task.abort();
      task.onHeadersReceived((result) => {
        status = result.statusCode || 0;
      });
      if (!task.onChunkReceived) {
        fail(new ApiError("当前微信版本不支持流式接收，请升级微信"));
        return;
      }
      task.onChunkReceived((result) => {
        if (failed || cancelled || status >= 400) return;
        try {
          parser.feed(result.data);
        } catch (error) {
          fail(error instanceof Error ? error : new ApiError("回答数据异常"));
        }
      });
    });
  }
  const promise = (async () => {
    const owner = appStore.state.account?.userId;
    try {
      if ((appStore.state.account?.expiresAt || 0) <= Date.now() + 30000)
        await refreshApiSession();
      if (cancelled) return;
      try {
        await once(appStore.state.account?.accessToken || "");
      } catch (error) {
        if (
          !(error instanceof ApiError) ||
          error.statusCode !== 401 ||
          cancelled
        )
          throw error;
        await refreshApiSession();
        if (cancelled || appStore.state.account?.userId !== owner) return;
        await once(appStore.state.account?.accessToken || "");
      }
    } catch (error) {
      if (!cancelled && error instanceof ApiError && error.statusCode === 401)
        redirectToLogin();
      if (!cancelled) throw error;
    }
  })();
  return {
    promise,
    abort() {
      cancelled = true;
      stop?.();
      rejectCancelled?.(new ApiError("已停止接收回答"));
    },
  };
}
