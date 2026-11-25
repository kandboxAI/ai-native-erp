/** Only explicitly declared navigation/filter metadata may accompany a desktop question. */
export type AiFilterValue = string | number | boolean | null;

export interface AiPageSnapshot {
  receipts: string[];
  metric_keys?: Record<string, string[]>;
}

export interface AiPageContext {
  page_key: string;
  title: string;
  path: string;
  filters: Record<string, AiFilterValue>;
  data_source: "demo" | "live" | "unknown";
  snapshot?: AiPageSnapshot;
}

export interface AiQuestionContext extends Omit<AiPageContext, "snapshot"> {
  version: 1;
  subject_key: string;
  subject_title: string;
  question_key: string;
  captured_at: string;
}

export interface AiPresetQuestion {
  key: string;
  label: string;
  prompt: string;
}

/** Keep explicitly supplied filters within the version-1 desktop metadata contract. */
export function safeAiFilters(
  filters: Record<string, AiFilterValue>
): Record<string, AiFilterValue> {
  const result: Record<string, AiFilterValue> = {};
  for (const [key, value] of Object.entries(filters)) {
    if (Object.keys(result).length >= 16) break;
    if (
      key.length > 64 ||
      !/^(?:[a-z][a-z0-9_]*_(?:id|code)|date_from|date_to|period_label)$/.test(
        key
      ) ||
      /password|secret|token|authorization|cookie|phone|email/i.test(key)
    )
      continue;
    if (
      typeof value === "string" &&
      (value.length > 256 || /[\u0000-\u001f\u007f]/.test(value))
    )
      continue;
    if (typeof value === "number" && !Number.isFinite(value)) continue;
    if (
      value !== null &&
      !["string", "number", "boolean"].includes(typeof value)
    )
      continue;
    result[key] = value;
  }
  return result;
}

/** Freeze the explicitly supplied page metadata and receipt list when the question panel opens. */
export function captureAiPage(page: AiPageContext): AiPageContext {
  return {
    ...page,
    filters: { ...page.filters },
    ...(page.snapshot
      ? {
          snapshot: {
            receipts: [...page.snapshot.receipts],
            ...(page.snapshot.metric_keys
              ? {
                  metric_keys: Object.fromEntries(
                    Object.entries(page.snapshot.metric_keys).map(
                      ([section, keys]) => [section, [...keys]]
                    )
                  )
                }
              : {})
          }
        }
      : {})
  };
}

/** Copies metadata before routing away; never reads DOM text, cookies or table rows. */
export function captureAiQuestion(
  page: AiPageContext,
  subjectKey: string,
  subjectTitle: string,
  questionKey: string
): AiQuestionContext {
  return {
    version: 1,
    page_key: page.page_key,
    title: page.title,
    path: page.path,
    filters: safeAiFilters(page.filters),
    data_source: page.data_source,
    subject_key: subjectKey,
    subject_title: subjectTitle,
    question_key: questionKey,
    captured_at: new Date().toISOString()
  };
}
