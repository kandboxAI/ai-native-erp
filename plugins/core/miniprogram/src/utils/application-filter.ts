/** Filters operate only on the already authorized menu collection. */
interface Application {
  title: string;
  desc: string;
  groupKey: string | null;
  groupName: string | null;
}
export function applicationGroupId(item: Application): string {
  return JSON.stringify([item.groupKey || null, item.groupName || null]);
}
export function applicationCategories(items: Application[]) {
  const groups = new Map<string, string>();
  for (const item of items) {
    const id = applicationGroupId(item);
    if (!groups.has(id)) groups.set(id, item.groupName || "其他应用");
  }
  return [
    { id: "", name: "全部" },
    ...Array.from(groups, ([id, name]) => ({ id, name })),
  ];
}
export function filterApplications<T extends Application>(
  items: T[],
  keyword: string,
  groupId = "",
): T[] {
  const query = keyword.trim().toLocaleLowerCase();
  return items.filter(
    (item) =>
      (!groupId || applicationGroupId(item) === groupId) &&
      (!query ||
        [item.title, item.desc, item.groupName].some((value) =>
          value?.toLocaleLowerCase().includes(query),
        )),
  );
}
