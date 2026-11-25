export const DISCOUNTS = [
  { value: "1", label: "不打折" },
  { value: "0.95", label: "九五折" },
  { value: "0.9", label: "九折" },
  { value: "0.85", label: "八五折" },
  { value: "0.8", label: "八折" },
  { value: "0.7", label: "七折" },
  { value: "manual", label: "手动定价" },
];

export function discountLabel(value: string | number | null | undefined) {
  return (
    DISCOUNTS.find((option) => option.value === String(Number(value)))?.label ||
    "手动定价"
  );
}

export function discountValue(value: string | number | null | undefined) {
  return value == null ? "manual" : String(Number(value));
}

export function discountPrice(original: number | string, rate: string) {
  // 两位小数原价转为分，用整数倍率计算；底价向上取分，避免低于七折。
  const cents = BigInt(Number(original).toFixed(2).replace(".", ""));
  const minimum = (cents * 70n + 99n) / 100n;
  const discount = BigInt(Math.round(Number(rate) * 100));
  const result = (cents * discount + 50n) / 100n;
  return Number(result < minimum ? minimum : result) / 100;
}

export function applyDiscount(
  row: {
    discount_rate: string;
    unit_price: number;
    adjustment_reason: string;
    is_price_confirmed: boolean;
  },
  original: number | string,
) {
  row.is_price_confirmed = false;
  if (row.discount_rate === "manual") return;
  row.unit_price = discountPrice(original, row.discount_rate);
  if (
    !row.adjustment_reason ||
    row.adjustment_reason.startsWith("订单折扣：")
  ) {
    row.adjustment_reason =
      row.discount_rate === "1"
        ? ""
        : `订单折扣：${discountLabel(row.discount_rate)}`;
  }
}
