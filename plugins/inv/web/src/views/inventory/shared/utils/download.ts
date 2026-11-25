/** 触发浏览器下载 public 目录或同源静态资源 */
export function downloadStaticFile(url: string, filename: string) {
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

/** 下载内存中的 CSV 文本（UTF-8 BOM，Excel 友好） */
export function downloadCsvText(filename: string, content: string) {
  const blob = new Blob(["\ufeff" + content], {
    type: "text/csv;charset=utf-8;"
  });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}
