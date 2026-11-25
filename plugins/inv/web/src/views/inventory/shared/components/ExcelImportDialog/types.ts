export type ExcelImportIssue = {
  sheet: string;
  row: number;
  field?: string | null;
  message: string;
};

export type ExcelImportValidation = {
  valid: boolean;
  summary: object;
  errors: ExcelImportIssue[];
  warnings: ExcelImportIssue[];
};

export type ExcelImportResponse<
  T extends ExcelImportValidation = ExcelImportValidation
> = {
  data: T;
};

export type ExcelImportSummaryItem = {
  label: string;
  key: string;
};
