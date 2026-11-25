// Vite resolves the standard ESM entry; browser/CJS bundles require global atob.
import MarkdownIt, { type Token } from "markdown-it";

export interface MarkdownPart {
  kind: "text" | "table";
  html: string;
  width?: number;
}

// 模型文字不作为 HTML 执行；图片与链接仅展示说明，不发起外部资源请求。
const markdown = new MarkdownIt({ html: false, breaks: true, linkify: false });

export interface KnowledgeSource {
  document_id: string;
  source_hash_snapshot: string;
  chunk_no: string;
}

export function parseKnowledgeCitation(
  address: string,
): KnowledgeSource | null {
  const match =
    /^dsh-resource:\/\/knowledge\/([0-9a-f-]{36})\/([0-9a-f]{64})\/([a-zA-Z0-9_-]{1,128})$/.exec(
      address,
    );
  return match
    ? {
        document_id: match[1]!,
        source_hash_snapshot: match[2]!,
        chunk_no: match[3]!,
      }
    : null;
}

/** rich-text 不接管自定义协议；从真实 Markdown 链接提取原生来源按钮。 */
export function extractAssistantCitations(content: string) {
  const sources: { address: string; label: string }[] = [];
  const seen = new Set<string>();
  for (const block of markdown.parse(content, {})) {
    const children = block.children || [];
    for (let index = 0; index < children.length; index++) {
      const token = children[index]!;
      if (token.type !== "link_open") continue;
      const address = String(token.attrGet("href") || "");
      if (!parseKnowledgeCitation(address) || seen.has(address)) continue;
      let label = "";
      for (
        let next = index + 1;
        next < children.length && children[next]!.type !== "link_close";
        next++
      ) {
        label += children[next]!.content;
      }
      sources.push({
        address,
        label: String(
          token.attrGet("title") || `来源 ${label || sources.length + 1}`,
        ),
      });
      seen.add(address);
    }
  }
  return sources;
}
const styles: Record<string, string> = {
  p: "margin:0 0 10px;line-height:1.75;word-break:break-word;",
  h1: "margin:14px 0 10px;font-size:19px;font-weight:700;line-height:1.5;",
  h2: "margin:14px 0 9px;font-size:16px;font-weight:700;line-height:1.5;",
  h3: "margin:12px 0 8px;font-size:14px;font-weight:700;line-height:1.5;",
  h4: "margin:10px 0 7px;font-size:13px;font-weight:700;",
  h5: "margin:10px 0 7px;font-size:12px;font-weight:700;",
  h6: "margin:10px 0 7px;font-size:12px;font-weight:700;",
  strong: "font-weight:700;",
  em: "font-style:italic;",
  s: "text-decoration:line-through;",
  ul: "margin:6px 0 10px;padding-left:20px;list-style-type:disc;",
  ol: "margin:6px 0 10px;padding-left:20px;list-style-type:decimal;",
  li: "margin:4px 0;line-height:1.75;",
  blockquote:
    "margin:8px 0;padding:6px 10px;border-left:3px solid #9ebde8;background:#f4f7fc;",
  hr: "margin:14px 0;border:0;border-top:1px solid #e2e8f0;",
  table: "width:100%;border-collapse:collapse;font-size:12px;line-height:1.6;",
  th: "padding:8px 10px;border:1px solid #dbe4ee;background:#edf3fb;font-weight:700;word-break:break-word;",
  td: "padding:8px 10px;border:1px solid #dbe4ee;word-break:break-word;",
};

function decorate(tokens: Token[]) {
  for (const token of tokens) {
    if (token.nesting === 1 || token.type === "hr") {
      if (styles[token.tag]) token.attrJoin("style", styles[token.tag]!);
    }
    if (token.children) decorate(token.children);
  }
}

markdown.renderer.rules.link_open = () =>
  '<span style="color:#2467ba;text-decoration:underline;">';
markdown.renderer.rules.link_close = () => "</span>";
markdown.renderer.rules.image = (tokens, index) =>
  markdown.utils.escapeHtml(tokens[index]?.content || "图片");
markdown.renderer.rules.code_inline = (tokens, index) =>
  `<code style="padding:1px 4px;background:#edf2f8;border-radius:3px;font-family:monospace;word-break:break-all;">${markdown.utils.escapeHtml(tokens[index]?.content || "")}</code>`;
const codeBlock = (tokens: Token[], index: number) =>
  `<pre style="margin:8px 0;padding:10px;background:#f3f6fa;border-radius:6px;white-space:pre-wrap;word-break:break-all;font-family:monospace;line-height:1.6;">${markdown.utils.escapeHtml(tokens[index]?.content || "")}</pre>`;
markdown.renderer.rules.fence = codeBlock;
markdown.renderer.rules.code_block = codeBlock;

/** 独立表格交给 scroll-view，正文保持手机宽度，不随宽表格拉长。 */
export function renderAssistantMarkdown(content: string): MarkdownPart[] {
  if (!content) return [];
  const environment = {};
  const tokens = markdown.parse(content, environment);
  decorate(tokens);
  const parts: MarkdownPart[] = [];
  let start = 0;
  function prose(end: number) {
    if (end > start) {
      parts.push({
        kind: "text",
        html: markdown.renderer.render(
          tokens.slice(start, end),
          markdown.options,
          environment,
        ),
      });
    }
  }
  for (let index = 0; index < tokens.length; index++) {
    if (tokens[index]?.type !== "table_open" || tokens[index]?.level !== 0)
      continue;
    prose(index);
    let end = index + 1;
    while (end < tokens.length && tokens[end]?.type !== "table_close") end++;
    const table = tokens.slice(index, end + 1);
    const columns = table.filter((token) => token.type === "th_open").length;
    parts.push({
      kind: "table",
      width: Math.max(260, columns * 90),
      html: markdown.renderer.render(table, markdown.options, environment),
    });
    index = end;
    start = end + 1;
  }
  prose(tokens.length);
  return parts;
}
