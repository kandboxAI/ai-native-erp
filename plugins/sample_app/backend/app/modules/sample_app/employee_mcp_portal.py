"""员工门户入口，组合页面结构、交互及原件完整性算法。"""
from .employee_portal_view import HTML
from .employee_portal_styles import CSS
from .employee_portal_script import BOOTSTRAP, HANDLERS

JAVASCRIPT = BOOTSTRAP + r'''
// MD5 与 web/src/utils/md5.ts 使用同一 RFC 1321 算法，原件不经过业务后端。
/**
 * MD5（RFC 1321），用于文件直传时的 Content-MD5 请求头。
 * 浏览器的 WebCrypto 不提供 MD5，这里自带一个无依赖实现；结果为 Base64 编码的 16 字节摘要。
 */

const SHIFTS = [
  7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 5, 9, 14, 20, 5,
  9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20, 4, 11, 16, 23, 4, 11, 16, 23, 4, 11,
  16, 23, 4, 11, 16, 23, 6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15,
  21
];
const CONSTANTS = Array.from(
  { length: 64 },
  (_, i) => Math.floor(Math.abs(Math.sin(i + 1)) * 2 ** 32) >>> 0
);

function md5(bytes) {
  const length = bytes.length;
  const padded = new Uint8Array((((length + 8) >>> 6) + 1) * 64);
  padded.set(bytes);
  padded[length] = 0x80;
  const view = new DataView(padded.buffer);
  view.setUint32(padded.length - 8, (length * 8) >>> 0, true);
  view.setUint32(padded.length - 4, Math.floor(length / 0x20000000), true);

  let a0 = 0x67452301;
  let b0 = 0xefcdab89;
  let c0 = 0x98badcfe;
  let d0 = 0x10325476;
  const words = new Uint32Array(16);
  for (let offset = 0; offset < padded.length; offset += 64) {
    for (let i = 0; i < 16; i++)
      words[i] = view.getUint32(offset + i * 4, true);
    let a = a0;
    let b = b0;
    let c = c0;
    let d = d0;
    for (let i = 0; i < 64; i++) {
      let f;
      let g;
      if (i < 16) {
        f = (b & c) | (~b & d);
        g = i;
      } else if (i < 32) {
        f = (d & b) | (~d & c);
        g = (5 * i + 1) % 16;
      } else if (i < 48) {
        f = b ^ c ^ d;
        g = (3 * i + 5) % 16;
      } else {
        f = c ^ (b | ~d);
        g = (7 * i) % 16;
      }
      const temp = d;
      d = c;
      c = b;
      const sum = (a + f + CONSTANTS[i] + words[g]) >>> 0;
      b = (b + ((sum << SHIFTS[i]) | (sum >>> (32 - SHIFTS[i])))) >>> 0;
      a = temp;
    }
    a0 = (a0 + a) >>> 0;
    b0 = (b0 + b) >>> 0;
    c0 = (c0 + c) >>> 0;
    d0 = (d0 + d) >>> 0;
  }
  const digest = new Uint8Array(16);
  const out = new DataView(digest.buffer);
  [a0, b0, c0, d0].forEach((value, i) => out.setUint32(i * 4, value, true));
  return digest;
}

const BASE64 =
  "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

function toBase64(bytes) {
  let result = "";
  for (let i = 0; i < bytes.length; i += 3) {
    const n =
      (bytes[i] << 16) | ((bytes[i + 1] ?? 0) << 8) | (bytes[i + 2] ?? 0);
    result +=
      BASE64[(n >> 18) & 63] +
      BASE64[(n >> 12) & 63] +
      (i + 1 < bytes.length ? BASE64[(n >> 6) & 63] : "=") +
      (i + 2 < bytes.length ? BASE64[n & 63] : "=");
  }
  return result;
}

/** Content-MD5 请求头的值：MD5 摘要的 Base64。 */
function md5base64(bytes) { return toBase64(md5(new Uint8Array(bytes))); }


''' + HANDLERS
