import type { InboxTodoPage } from "@/config/pluginServices";

/** 各来源须按时间倒序；每个来源取到当前页末尾，再合并分页，避免新待办被来源分组压后。 */
export async function paginateTodos(
  sources: Array<(page: number, size: number) => Promise<InboxTodoPage>>,
  page: number,
  pageSize: number,
): Promise<InboxTodoPage> {
  const end = page * pageSize;
  const size = Math.min(end, 50);
  const results = await Promise.allSettled(sources.map(async load => {
    const first = await load(1, size);
    const items = [...first.items];
    for (let next = 2; (next - 1) * size < Math.min(end, first.total); next++) {
      items.push(...(await load(next, size)).items);
    }
    return { items, total: first.total };
  }));
  const items: InboxTodoPage["items"] = [];
  let total = 0;
  for (const result of results) {
    if (result.status !== "fulfilled") continue;
    items.push(...result.value.items);
    total += result.value.total;
  }
  const timestamp = (value: string | null) => value ? Date.parse(value.replace(" ", "T")) || 0 : 0;
  items.sort((a, b) => timestamp(b.arrived_at) - timestamp(a.arrived_at));
  return { items: items.slice(end - pageSize, end), total, page, page_size: pageSize };
}
