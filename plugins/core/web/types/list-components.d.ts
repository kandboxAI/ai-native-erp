export {};
declare module "vue" {
  export interface GlobalComponents {
    ReListTable: (typeof import("../src/components/ReListTable/index"))["default"];
    ReListPagination: (typeof import("../src/components/ReListPagination/index"))["default"];
    ReListHeading: (typeof import("../src/components/ReListHeading/index"))["default"];
    ReListPresentation: (typeof import("../src/components/ReListPresentation/index.vue"))["default"];
    ReListIdentity: (typeof import("../src/components/ReListIdentity/index.vue"))["default"];
    ReListMoreFilters: (typeof import("../src/components/ReListMoreFilters/index.vue"))["default"];
    ReMenuViews: (typeof import("../src/components/ReMenuViews/index"))["default"];
  }
}
