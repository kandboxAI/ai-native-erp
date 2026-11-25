import { defineStore } from "pinia";
import type { AiPageContext } from "@/utils/aiPageContext";

/** Memory only: page providers own their functions; Pinia holds serializable metadata. */
export const useAiPageContextStore = defineStore("ai-page-context", {
  state: () => ({
    owner: "",
    page: null as AiPageContext | null,
    revision: 0
  }),
  actions: {
    publish(owner: string, page: AiPageContext) {
      this.owner = owner;
      this.page = {
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
    },
    release(owner: string) {
      if (this.owner !== owner) return;
      this.owner = "";
      this.page = null;
    },
    resetContext() {
      this.owner = "";
      this.page = null;
      this.revision++;
    }
  }
});
