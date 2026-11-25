/** 地图拾取文本按经度、纬度解析；拒绝空值、无穷及越界，保留七位小数。 */
export function parseCoordinates(value: string): {longitude: number; latitude: number} {
  const parts = value.split(/[,，]/).map(item => item.trim());
  if (parts.length !== 2 || !parts.every(item => /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(item)))
    throw new Error("坐标格式应为：经度,纬度");
  const [longitude, latitude] = parts.map(Number);
  if (!Number.isFinite(longitude) || !Number.isFinite(latitude) || Math.abs(longitude) > 180 || Math.abs(latitude) > 90)
    throw new Error("经度须在 -180～180，纬度须在 -90～90，请核对顺序");
  return {longitude: Number(longitude.toFixed(7)), latitude: Number(latitude.toFixed(7))};
}
