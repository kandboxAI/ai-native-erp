import { defineStore } from "pinia";
import { http } from "@/utils/http";
import { store } from "../utils";
import { getDictionaryOptions } from "@/api/systemDictionary";
import type { OrganizationListRow } from "@/api/organizationStructure";

export type BasicDictOption = {
  value: string;
  label: string;
  remark?: string | null;
};

type ApiResponse<T> = {
  code: number;
  message: string;
  data: T;
};

type PageResult<T> = {
  items: T[];
  total: number;
};

type BasicDataState = {
  organizations: OrganizationListRow[];
  dictOptions: Record<string, BasicDictOption[]>;
  organizationsLoaded: boolean;
  dictLoaded: Record<string, boolean>;
};

const dictRequests = new Map<string, Promise<BasicDictOption[]>>();

async function fetchAllDictionaryOptions(
  dictCode: string
): Promise<BasicDictOption[]> {
  const res = await getDictionaryOptions([dictCode]);
  if (res.code !== 0) throw new Error(res.message || "加载字典失败");
  return (res.data?.[dictCode] ?? []).map(item => ({
    value: item.item_code,
    label: item.item_name
  }));
}

export const useBasicDataStore = defineStore("pure-basic-data", {
  state: (): BasicDataState => ({
    organizations: [],
    dictOptions: {},
    organizationsLoaded: false,
    dictLoaded: {}
  }),
  actions: {
    async loadOrganizations(force = false) {
      if (!force && this.organizationsLoaded) return this.organizations;
      const res = await http.request<
        ApiResponse<PageResult<OrganizationListRow>>
      >("get", "/api/organization/list", {
        params: { page: 1, page_size: 100 }
      });
      if (res.code !== 0) throw new Error(res.message || "加载组织失败");
      this.organizations = res.data?.items ?? [];
      this.organizationsLoaded = true;
      return this.organizations;
    },
    async loadDictOptions(dictType: string, force = false) {
      if (!force && this.dictLoaded[dictType]) {
        return this.dictOptions[dictType] ?? [];
      }
      if (force) dictRequests.delete(dictType);
      if (!dictRequests.has(dictType)) {
        dictRequests.set(dictType, fetchAllDictionaryOptions(dictType));
      }
      try {
        const items = await dictRequests.get(dictType)!;
        this.dictOptions = { ...this.dictOptions, [dictType]: items };
        this.dictLoaded = { ...this.dictLoaded, [dictType]: true };
        return items;
      } catch (error) {
        dictRequests.delete(dictType);
        throw error;
      }
    },
    invalidateDictOptions(dictType?: string) {
      if (dictType) {
        dictRequests.delete(dictType);
        const { [dictType]: _removedOptions, ...dictOptions } =
          this.dictOptions;
        const { [dictType]: _removedLoaded, ...dictLoaded } = this.dictLoaded;
        this.dictOptions = dictOptions;
        this.dictLoaded = dictLoaded;
        return;
      }
      dictRequests.clear();
      this.dictOptions = {};
      this.dictLoaded = {};
    }
  }
});

export function useBasicDataStoreHook() {
  return useBasicDataStore(store);
}
