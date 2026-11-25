import { http } from "@/utils/http";

export type LocationItem = {
  id: string;
  org_id: string;
  location_no: string;
  location_name: string;
  location_type_code: string;
  latitude: string | number;
  longitude: string | number;
  coordinate_system_code: string;
  location_description: string | null;
  sort_no: number;
  is_active: boolean;
  version_no: number;
  remark: string | null;
  is_selectable: boolean;
};
export type LocationBody = {
  org_id: string;
  location_no?: string;
  location_name: string;
  location_type_code: string;
  latitude: number;
  longitude: number;
  coordinate_system_code: string;
  location_description: string | null;
  sort_no: number;
  is_active: boolean;
  remark: string | null;
};
export type LocationOption = Pick<
  LocationItem,
  | "id"
  | "org_id"
  | "location_no"
  | "location_name"
  | "location_type_code"
  | "latitude"
  | "longitude"
  | "coordinate_system_code"
>;
type Response<T> = { code: number; message: string; data: T };
export const listLocations = (org_id?: string) =>
  http.request<Response<{ items: LocationItem[] }>>(
    "get",
    "/api/location/list",
    { params: { org_id: org_id || undefined } },
  );
export const locationOptions = (permission_key: string, org_id?: string) =>
  http.request<Response<{ items: LocationOption[] }>>(
    "get",
    "/api/location/options",
    { params: { permission_key, org_id: org_id || undefined } },
  );
export const locationMeta = () =>
  http.request<
    Response<{
      organizations: Array<{ id: string; org_name: string }>;
      default_org_id: string | null;
      can_change_org: boolean;
      location_types: Array<{ value: string; label: string }>;
      coordinate_systems: Array<{ value: string; label: string }>;
    }>
  >("get", "/api/location/meta");
export const saveLocation = (
  body: LocationBody,
  id?: string,
  expected_version?: number,
) =>
  id
    ? http.request<Response<unknown>>("put", `/api/location/${id}`, {
        data: { ...body, expected_version },
      })
    : http.request<Response<unknown>>("post", "/api/location", { data: body });
export const deleteLocation = (id: string, expected_version: number) =>
  http.request<Response<unknown>>("delete", `/api/location/${id}`, {
    data: { expected_version },
  });
