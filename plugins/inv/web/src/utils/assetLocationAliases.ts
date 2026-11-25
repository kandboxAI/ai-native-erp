type LocationOption = {
  id: string;
  physical_location_id?: string;
  asset_location_ids?: string[];
};

export function findAssetLocation<T extends LocationOption>(
  items: T[],
  id?: string | null,
): T | undefined {
  return id
    ? items.find(
        (item) =>
          item.id === id ||
          item.physical_location_id === id ||
          item.asset_location_ids?.includes(id),
      )
    : undefined;
}

/** 每个物理位置只展示一次，同时保留表单原有的历史地点 ID。 */
export function assetLocationOptions<T extends LocationOption>(
  items: T[],
  selected?: string | null,
): T[] {
  const match = findAssetLocation(items, selected);
  return match && selected && match.id !== selected
    ? items.map((item) => (item === match ? { ...item, id: selected } : item))
    : items;
}
