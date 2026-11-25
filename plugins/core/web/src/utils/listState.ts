/** 列表展示状态；只保存列设置，不保存业务记录、查询内容或登录凭据。 */
export type ColumnPreference = {
  key: string;
  hidden?: boolean;
  fixed?: false | "left" | "right";
};
export type ListPreference = {
  version: 1;
  columns: ColumnPreference[];
  size?: "large" | "default" | "small";
};
export type ListQuery = {
  key: string;
  fields: string[];
  aliases?: Record<string, string>;
};
export const listQuerySymbol = Symbol("list-query");
const querySorts = new Map<string, { field: string; order: "asc" | "desc" }>();
const recentQueries = new Map<string, { query: ListQuery; ids: Set<string> }>();
const explicitSorts = new Map<string, string>();
let getScope = () => "anonymous";
let getRoute = () => "";

export function configureListState(scope: () => string, route: () => string) {
  getScope = scope;
  getRoute = route;
}

export function preferenceKey(table: string) {
  return `list-layout:v1:${getScope()}:${table}`;
}

/** 同一个字段可有多个展示列，用标签区分，避免列设置覆盖或丢列。 */
export function columnKeys(
  columns: { prop?: any; slot?: any; type?: any; label?: any }[]
): string[] {
  const bases = columns.map((column, index) =>
    String(
      column.prop ||
        column.slot ||
        column.type ||
        column.label ||
        `column-${index}`
    )
  );
  const counts = new Map<string, number>();
  for (const key of bases) counts.set(key, (counts.get(key) || 0) + 1);
  const seen = new Map<string, number>();
  return columns.map((column, index) => {
    const key =
      counts.get(bases[index]) > 1
        ? `${bases[index]}:${String(column.label || "")}`
        : bases[index];
    const occurrence = seen.get(key) || 0;
    seen.set(key, occurrence + 1);
    return occurrence ? `${key}:${occurrence}` : key;
  });
}

export function readListPreference(table: string): ListPreference | undefined {
  try {
    const value = JSON.parse(
      localStorage.getItem(preferenceKey(table)) || "null"
    );
    if (value?.version !== 1 || !Array.isArray(value.columns)) return;
    if (
      !value.columns.every(
        column =>
          column &&
          typeof column.key === "string" &&
          (column.hidden == null || typeof column.hidden === "boolean") &&
          (column.fixed == null ||
            [false, "left", "right"].includes(column.fixed))
      ) ||
      (value.size != null && !["large", "default", "small"].includes(value.size))
    )
      return;
    return value;
  } catch {
    return;
  }
}

export function saveListPreference(table: string, preference: ListPreference) {
  try {
    localStorage.setItem(preferenceKey(table), JSON.stringify(preference));
  } catch {
    /* 禁用存储时仍可临时设置。 */
  }
}

export function clearListPreference(table: string) {
  try {
    localStorage.removeItem(preferenceKey(table));
  } catch {
    /* 仅恢复本次显示。 */
  }
}

export function mergeColumnPreferences<
  T extends { key: string; locked?: boolean; hidden?: boolean; fixed?: unknown }
>(columns: T[], saved: ColumnPreference[] = []): T[] {
  const byKey = new Map(columns.map(column => [column.key, column]));
  const ordered = [
    ...saved.map(column => column.key),
    ...columns.map(column => column.key)
  ];
  const seen = new Set<string>();
  const result = ordered.flatMap(key => {
    if (seen.has(key) || !byKey.has(key)) return [];
    seen.add(key);
    const column = byKey.get(key)!;
    const preference = saved.find(item => item.key === key);
    return [
      {
        ...column,
        ...(preference && !column.locked
          ? {
              hidden: !!preference.hidden,
              fixed: preference.fixed ?? column.fixed
            }
          : {})
      }
    ];
  });
  columns.forEach((column, index) => {
    if (!column.locked) return;
    const from = result.findIndex(item => item.key === column.key);
    if (from >= 0) result.splice(index, 0, result.splice(from, 1)[0]);
  });
  return result;
}

function queryKey(config: {
  method?: string;
  url?: string;
  params?: any;
  data?: any;
}) {
  const values = {
    ...config.params,
    ...(config.data &&
    typeof config.data === "object" &&
    !(config.data instanceof FormData)
      ? config.data
      : {})
  };
  const discriminator = ["entity", "kind", "reviewed", "mine"]
    .map(key => `${key}=${String(values[key] ?? "")}`)
    .join("&");
  return `${getScope()}:${getRoute()}:${config.method}:${config.url}:${discriminator}`;
}

export function prepareListRequest(config: {
  method?: string;
  url?: string;
  params?: any;
  data?: any;
  headers?: any;
  [key: string]: any;
}) {
  const key = queryKey(config);
  config.__listQueryKey = key;
  const explicit = config.params?.sort_by
    ? `${config.params.sort_by}:${config.params.sort_order || "asc"}`
    : "";
  if (explicitSorts.has(key) && explicitSorts.get(key) !== explicit)
    querySorts.delete(key);
  explicitSorts.set(key, explicit);
  const sort = querySorts.get(key);
  if (sort) {
    config.headers = {
      ...config.headers,
      "X-List-Sort-By": sort.field,
      "X-List-Sort-Order": sort.order
    };
  }
}

export function recordListResponse(response: {
  headers?: any;
  config: any;
  data: any;
}) {
  const fields = String(response.headers?.["x-list-sort-fields"] ?? "")
    .split(",")
    .filter(Boolean);
  if (!fields.length || !response.config.__listQueryKey) return;
  const descriptor: ListQuery = { key: response.config.__listQueryKey, fields };
  const body = response.data?.data;
  const rows = Array.isArray(body) ? body : (body?.items ?? body?.list);
  if (!Array.isArray(rows)) return;
  recentQueries.set(descriptor.key, {
    query: descriptor,
    ids: new Set(rows.filter(row => row?.id != null).map(row => String(row.id)))
  });
  if (recentQueries.size > 128)
    recentQueries.delete(recentQueries.keys().next().value);
  Object.defineProperty(rows, listQuerySymbol, {
    value: descriptor,
    configurable: true
  });
  for (const row of rows) {
    if (row && typeof row === "object") {
      // symbol 随 {...row} 适配保留，JSON 序列化不会携带它。
      Object.defineProperty(row, listQuerySymbol, {
        value: descriptor,
        enumerable: true,
        configurable: true
      });
    }
  }
}

export function getListQuery(rows: any[]): ListQuery | undefined {
  let query: ListQuery =
    (rows as any)?.[listQuerySymbol] ??
    rows?.find(row => row?.[listQuerySymbol])?.[listQuerySymbol];
  if (!query && rows?.length) {
    // 兼容已有 toRow 适配器重建对象的页面。只记录临时 ID 集合，匹配不唯一就拒绝猜测。
    const ids = rows
      .slice(0, 5)
      .map(row => row?.id)
      .filter(id => id != null)
      .map(String);
    const prefix = `${getScope()}:${getRoute()}:`;
    const candidates = ids.length
      ? [...recentQueries.values()].filter(
          item =>
            item.query.key.startsWith(prefix) &&
            ids.every(id => item.ids.has(id))
        )
      : [];
    if (candidates.length === 1) query = candidates[0].query;
  }
  if (!query) return;
  const aliases: Record<string, string> = {};
  for (const field of query.fields) {
    const camel = field.replace(/_([a-z])/g, (_, letter) =>
      letter.toUpperCase()
    );
    if (camel !== field && rows?.some(row => camel in row))
      aliases[camel] = field;
  }
  return {
    ...query,
    fields: [...query.fields, ...Object.keys(aliases)],
    aliases
  };
}

/** 已完整取得的列表先排序再切片，不为排序额外拉取服务端分页。 */
export function applyLocalListQuery<T extends object>(
  config: { method: string; url: string; data?: any },
  rows: T[],
  fields: string[]
): T[] {
  prepareListRequest(config);
  const sort = querySorts.get((config as any).__listQueryKey);
  const sorted = sortListRows(rows, sort?.field, sort?.order);
  recordListResponse({
    config,
    headers: { "x-list-sort-fields": fields.join(",") },
    data: { data: { items: sorted } }
  });
  return sorted;
}

export function setListSort(query: ListQuery, field?: string, order?: string) {
  if (!field || !order) {
    querySorts.delete(query.key);
    return;
  }
  if (!query.fields.includes(field)) throw new Error("该列不支持排序");
  querySorts.set(query.key, {
    field: query.aliases?.[field] || field,
    order: order === "descending" || order === "desc" ? "desc" : "asc"
  });
}

export function sortListRows<T>(
  rows: T[],
  field?: string,
  order?: string
): T[] {
  if (!field || !order) return rows;
  const direction = order === "descending" || order === "desc" ? -1 : 1;
  const collator = new Intl.Collator("zh-CN", {
    numeric: true,
    sensitivity: "base"
  });
  return rows
    .map((row, index) => ({ row, index }))
    .sort((a, b) => {
      const left = a.row[field],
        right = b.row[field];
      if (left == null || left === "")
        return right == null || right === "" ? a.index - b.index : 1;
      if (right == null || right === "") return -1;
      let comparison: number;
      if (typeof left === "number" && typeof right === "number")
        comparison = left - right;
      else if (
        /^-?\d+(?:\.\d+)?$/.test(String(left)) &&
        /^-?\d+(?:\.\d+)?$/.test(String(right))
      ) {
        const precision = Math.max(
          (String(left).split(".")[1] || "").length,
          (String(right).split(".")[1] || "").length
        );
        const scaled = (value: unknown) => {
          const text = String(value),
            [whole, fraction = ""] = text.replace(/^-/, "").split(".");
          return (
            BigInt(whole + fraction.padEnd(precision, "0")) *
            (text.startsWith("-") ? -1n : 1n)
          );
        };
        const aValue = scaled(left),
          bValue = scaled(right);
        comparison = aValue < bValue ? -1 : aValue > bValue ? 1 : 0;
      } else comparison = collator.compare(String(left), String(right));
      return direction * comparison || a.index - b.index;
    })
    .map(item => item.row);
}

export function sortListTree<T>(
  rows: T[],
  field?: string,
  order?: string,
  children = "children"
): T[] {
  if (!field || !order) return rows;
  return sortListRows(rows, field, order).map(row =>
    Array.isArray(row[children])
      ? {
          ...row,
          [children]: sortListTree(row[children], field, order, children)
        }
      : row
  );
}
