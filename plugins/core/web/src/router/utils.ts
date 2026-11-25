import {
  type RouterHistory,
  type RouteRecordRaw,
  type RouteComponent,
  createWebHistory,
  createWebHashHistory
} from "vue-router";
import { router } from "./index";
import { isProxy, toRaw } from "vue";
import { useTimeoutFn } from "@vueuse/core";
import {
  isString,
  cloneDeep,
  isAllEmpty,
  intersection,
  storageLocal,
  isIncludeAllChildren
} from "@pureadmin/utils";
import { getConfig } from "@/config";
import { buildHierarchyTree } from "@/utils/tree";
import { asyncRoutesKey, userKey, type DataInfo } from "@/utils/auth";
import { type menuType, routerArrays } from "@/layout/types";
import { useMultiTagsStoreHook } from "@/store/modules/multiTags";
import { usePermissionStoreHook } from "@/store/modules/permission";
import { useUserStoreHook } from "@/store/modules/user";
import modulesRoutes from "virtual:deployed-views";
const IFrame = () => import("@/layout/frame.vue");

// 动态路由
import { getAsyncRoutes } from "@/api/routes";

const PAGE_NOT_FOUND_ROUTE_NAME = "PageNotFound" as const;

function handRank(routeInfo: any) {
  const { name, path, parentId, meta } = routeInfo;
  return isAllEmpty(parentId)
    ? isAllEmpty(meta?.rank) ||
      (meta?.rank === 0 && name !== "Home" && path !== "/")
      ? true
      : false
    : false;
}

/** 按照路由中meta下的rank等级升序来排序路由 */
function ascending(arr: any[]) {
  arr.forEach((v, index) => {
    // 当rank不存在时，根据顺序自动创建，首页路由永远在第一位
    if (handRank(v)) v.meta.rank = index + 2;
  });
  return arr.sort(
    (a: { meta: { rank: number } }, b: { meta: { rank: number } }) => {
      return a?.meta.rank - b?.meta.rank;
    }
  );
}

/** 过滤meta中showLink为false的菜单 */
function filterTree(data: RouteComponent[]) {
  const newTree = cloneDeep(data).filter(
    (v: { meta: { showLink: boolean } }) => v.meta?.showLink !== false
  );
  newTree.forEach((v: any) => {
    if (!v.children) return;
    v.children = filterTree(v.children);
    // 列表页的隐藏详情子路由移除后，列表本身仍是可见页面。
    if (!v.children.length && v.component) delete v.children;
  });
  return newTree;
}

/** 过滤children长度为0的的目录，当目录下没有菜单时，会过滤此目录，目录没有赋予roles权限，当目录下只要有一个菜单有显示权限，那么此目录就会显示 */
function filterChildrenTree(data: RouteComponent[]) {
  const newTree = cloneDeep(data).filter((v: any) => v?.children?.length !== 0);
  newTree.forEach(
    (v: { children }) => v.children && (v.children = filterTree(v.children))
  );
  return newTree;
}

/** 判断两个数组彼此是否存在相同值 */
function isOneOfArray(a: Array<string>, b: Array<string>) {
  return Array.isArray(a) && Array.isArray(b)
    ? intersection(a, b).length > 0
      ? true
      : false
    : true;
}

/**
 * 按权限过滤菜单：路由 meta.permissions 为权限标识列表，用户拥有其中任意一个即可见；
 * 未声明 meta.permissions 的路由对所有登录用户可见。不按角色判断（角色由租户配置）。
 */
function filterNoPermissionTree(data: RouteComponent[]) {
  const currentPermissions =
    storageLocal().getItem<DataInfo<number>>(userKey)?.permissions ?? [];
  const newTree = cloneDeep(data).filter((v: any) =>
    isOneOfArray(v.meta?.permissions, currentPermissions)
  );
  newTree.forEach(
    (v: any) => v.children && (v.children = filterNoPermissionTree(v.children))
  );
  return filterChildrenTree(newTree);
}

/** 通过指定 `key` 获取父级路径集合，默认 `key` 为 `path` */
function getParentPaths(value: string, routes: RouteRecordRaw[], key = "path") {
  // 深度遍历查找
  function dfs(routes: RouteRecordRaw[], value: string, parents: string[]) {
    for (let i = 0; i < routes.length; i++) {
      const item = routes[i];
      // 返回父级path
      if (item[key] === value) return parents;
      // children不存在或为空则不递归
      if (!item.children || !item.children.length) continue;
      // 往下查找时将当前path入栈
      parents.push(item.path);

      if (dfs(item.children, value, parents).length) return parents;
      // 深度遍历查找未找到时当前path 出栈
      parents.pop();
    }
    // 未找到时返回空数组
    return [];
  }

  return dfs(routes, value, []);
}

/** 查找对应 `path` 的路由信息 */
function findRouteByPath(path: string, routes: RouteRecordRaw[]) {
  let res = routes.find((item: { path: string }) => item.path == path);
  if (res) {
    return isProxy(res) ? toRaw(res) : res;
  } else {
    for (let i = 0; i < routes.length; i++) {
      if (
        routes[i].children instanceof Array &&
        routes[i].children.length > 0
      ) {
        res = findRouteByPath(path, routes[i].children);
        if (res) {
          return isProxy(res) ? toRaw(res) : res;
        }
      }
    }
    return null;
  }
}

/** 动态路由注册完成后，再添加全屏404（页面不存在）页面，避免刷新动态路由页面时误跳转到404页面 */
function addPathMatch() {
  if (router.hasRoute(PAGE_NOT_FOUND_ROUTE_NAME)) return;
  router.addRoute({
    path: "/:pathMatch(.*)*",
    name: PAGE_NOT_FOUND_ROUTE_NAME,
    component: () => import("@/views/error/404.vue"),
    meta: {
      title: "menus.purePageNotFound",
      showLink: false
    }
  });
}

/** 处理动态路由（后端返回的路由） */
function handleAsyncRoutes(routeList) {
  if (routeList.length === 0) {
    usePermissionStoreHook().handleWholeMenus(routeList);
  } else {
    formatFlatteningRoutes(addAsyncRoutes(routeList)).map(
      (v: RouteRecordRaw) => {
        // 防止重复添加路由
        if (
          router.options.routes[0].children.findIndex(
            value => value.path === v.path
          ) !== -1
        ) {
          return;
        } else {
          const { children: _children, ...flatRoute } = v;
          // 切记将路由push到routes后还需要使用addRoute，这样路由才能正常跳转
          router.options.routes[0].children.push(flatRoute as RouteRecordRaw);
          // 最终路由进行升序
          ascending(router.options.routes[0].children);
          if (!router.hasRoute(flatRoute?.name))
            router.addRoute(flatRoute as RouteRecordRaw);
          const flattenRouters: any = router
            .getRoutes()
            .find(n => n.path === "/");
          // 保持router.options.routes[0].children与path为"/"的children一致，防止数据不一致导致异常
          flattenRouters.children = router.options.routes[0].children;
          router.addRoute(flattenRouters);
        }
      }
    );
    usePermissionStoreHook().handleWholeMenus(routeList);
  }
  // 固定入口以当前定义为准，升级时也刷新旧缓存中的名称与顺序。
  const fixedTags = [
    ...routerArrays,
    ...usePermissionStoreHook().flatteningRoutes.filter(v => v?.meta?.fixedTag)
  ];
  const workspacePaths = new Set(["/welcome", "/workbench", "/assistant"]);
  const cachedTags = useMultiTagsStoreHook().getMultiTagsCache
    ? useMultiTagsStoreHook().multiTags || []
    : [];
  const singleTagPaths = new Set(
    router
      .getRoutes()
      .filter(route => route.meta.dynamicLevel === 1)
      .map(route => route.path)
  );
  const latestCachedTag = new Map(cachedTags.map(tag => [tag.path, tag]));
  useMultiTagsStoreHook().handleTags("equal", [
    ...fixedTags,
    ...cachedTags.filter(
      tag =>
        !workspacePaths.has(tag.path) &&
        !fixedTags.some(fixed => fixed.path === tag.path) &&
        (!singleTagPaths.has(tag.path) || latestCachedTag.get(tag.path) === tag)
    )
  ]);
  addPathMatch();
}

/** 初始化路由（`new Promise` 写法防止在异步请求中造成无限循环）*/
async function initRouter() {
  // 菜单与页面操作权限都使用当前租户的服务端授权；不沿用旧登录缓存。
  // 请求失败时 store 已清空操作权限，菜单仍按现有降级流程处理。
  await useUserStoreHook()
    .refreshCurrentUser()
    .catch(() => undefined);
  if (getConfig()?.CachingAsyncRoutes) {
    // 开启动态路由缓存本地localStorage
    const key = asyncRoutesKey;
    const asyncRouteList = storageLocal().getItem(key) as any;
    if (asyncRouteList && asyncRouteList?.length > 0) {
      return new Promise(resolve => {
        handleAsyncRoutes(asyncRouteList);
        resolve(router);
      });
    } else {
      return new Promise(resolve => {
        getAsyncRoutes().then(({ code, data }) => {
          if (code === 0) {
            handleAsyncRoutes(cloneDeep(data));
            storageLocal().setItem(key, data);
            resolve(router);
          } else {
            resolve(router);
          }
        });
      });
    }
  } else {
    return new Promise(resolve => {
      getAsyncRoutes()
        .then(({ code, data }) => {
          handleAsyncRoutes(code === 0 ? cloneDeep(data) : []);
        })
        // 菜单接口失败时仍要初始化静态路由的固定页签（首页、工作台）
        .catch(() => handleAsyncRoutes([]))
        .finally(() => resolve(router));
    });
  }
}

/**
 * 将多级嵌套路由处理成一维数组
 * @param routesList 传入路由
 * @returns 返回处理后的一维路由
 */
function formatFlatteningRoutes(routesList: RouteRecordRaw[]) {
  if (routesList.length === 0) return routesList;
  let hierarchyList = buildHierarchyTree(routesList);
  for (let i = 0; i < hierarchyList.length; i++) {
    if (hierarchyList[i].children) {
      hierarchyList = hierarchyList
        .slice(0, i + 1)
        .concat(hierarchyList[i].children, hierarchyList.slice(i + 1));
    }
  }
  return hierarchyList;
}

/**
 * 一维数组处理成多级嵌套数组（三级及以上的路由全部拍成二级，keep-alive 只支持到二级缓存）
 * https://github.com/pure-admin/vue-pure-admin/issues/67
 * @param routesList 处理后的一维路由菜单数组
 * @returns 返回将一维数组重新处理成规定路由的格式
 */
function formatTwoStageRoutes(routesList: RouteRecordRaw[]) {
  if (routesList.length === 0) return routesList;
  const newRoutesList: RouteRecordRaw[] = [];
  routesList.forEach((v: RouteRecordRaw) => {
    if (v.path === "/") {
      newRoutesList.push({
        component: v.component,
        name: v.name,
        path: v.path,
        redirect: v.redirect,
        meta: v.meta,
        children: []
      });
    } else {
      // 菜单树仍保留 children；注册到 router 时必须拍平，
      // 否则带 redirect 的父级会把 /daily/* 等绝对路径子路由一起吞掉。
      const { children: _children, ...flatRoute } = v;
      newRoutesList[0]?.children.push(flatRoute as RouteRecordRaw);
    }
  });
  return newRoutesList;
}

/** 处理缓存路由（添加、删除、刷新） */
function handleAliveRoute({ name }: ToRouteType, mode?: string) {
  switch (mode) {
    case "add":
      usePermissionStoreHook().cacheOperate({
        mode: "add",
        name
      });
      break;
    case "delete":
      usePermissionStoreHook().cacheOperate({
        mode: "delete",
        name
      });
      break;
    case "refresh":
      usePermissionStoreHook().cacheOperate({
        mode: "refresh",
        name
      });
      break;
    default:
      usePermissionStoreHook().cacheOperate({
        mode: "delete",
        name
      });
      useTimeoutFn(() => {
        usePermissionStoreHook().cacheOperate({
          mode: "add",
          name
        });
      }, 100);
  }
}

function resolveAsyncView(route: RouteRecordRaw, modulesRoutesKeys: string[]) {
  const candidates: string[] = [];
  if (typeof route.component === "string" && route.component) {
    const spec = String(route.component)
      .replace(/^\/+/, "")
      .replace(/\.vue$/i, "");
    candidates.push(`/src/views/${spec}.vue`, `/src/views/${spec}/index.vue`);
  }
  if (route.path && route.path !== "/") {
    const cleaned = route.path.replace(/\/$/, "");
    candidates.push(
      `/src/views${cleaned}.vue`,
      `/src/views${cleaned}/index.vue`
    );
  }
  const matchedKey = modulesRoutesKeys.find(key =>
    candidates.some(candidate => key === candidate || key.endsWith(candidate))
  );
  return matchedKey ? modulesRoutes[matchedKey] : undefined;
}

/** 过滤后端传来的动态路由 重新生成规范路由 */
function addAsyncRoutes(arrRoutes: Array<RouteRecordRaw>) {
  if (!arrRoutes || !arrRoutes.length) return;
  const modulesRoutesKeys = Object.keys(modulesRoutes);
  for (let index = arrRoutes.length - 1; index >= 0; index -= 1) {
    const v = arrRoutes[index];
    // 将backstage属性加入meta，标识此路由为后端返回路由
    v.meta.backstage = true;
    if (v?.children && v.children.length) {
      addAsyncRoutes(v.children);
    }
    // 只有目录才需要默认跳转；列表页下的隐藏详情路由不能成为列表的跳转目标。
    if (v?.children && v.children.length && !v.redirect && !v.component)
      v.redirect = v.children.find(
        child => child.meta?.showLink !== false && !child.path.includes("/:")
      )?.path;
    // 父级的name属性取值：如果子级存在且父级的name属性不存在，默认取第一个子级的name；如果子级存在且父级的name属性存在，取存在的name属性，会覆盖默认值（注意：测试中发现父级的name不能和子级name重复，如果重复会造成重定向无效（跳转404），所以这里给父级的name起名的时候后面会自动加上`Parent`，避免重复）
    if (v?.children && v.children.length && !v.name)
      v.name = (v.children[0].name as string) + "Parent";
    if (v.meta?.frameSrc) {
      v.component = IFrame;
    } else if (typeof v.component !== "function") {
      // 必须精确匹配页面文件。includes(path) 会把 /daily 误打到
      // views/daily/affairs，导致所有 /daily/* 都渲染事务页。
      v.component = resolveAsyncView(v, modulesRoutesKeys);
    }
    // 页面文件已删除时，库里残留的菜单不再注册，避免点进空白页。
    if (
      !v.children?.length &&
      !v.component &&
      !v.meta?.frameSrc &&
      !v.redirect
    ) {
      arrRoutes.splice(index, 1);
    }
  }
  return arrRoutes;
}

/** 获取路由历史模式 https://next.router.vuejs.org/zh/guide/essentials/history-mode.html */
function getHistoryMode(routerHistory): RouterHistory {
  // len为1 代表只有历史模式 为2 代表历史模式中存在base参数 https://next.router.vuejs.org/zh/api/#%E5%8F%82%E6%95%B0-1
  const historyMode = routerHistory.split(",");
  const leftMode = historyMode[0];
  const rightMode = historyMode[1];
  // no param
  if (historyMode.length === 1) {
    if (leftMode === "hash") {
      return createWebHashHistory("");
    } else if (leftMode === "h5") {
      return createWebHistory("");
    }
  } //has param
  else if (historyMode.length === 2) {
    if (leftMode === "hash") {
      return createWebHashHistory(rightMode);
    } else if (leftMode === "h5") {
      return createWebHistory(rightMode);
    }
  }
}

/** 获取当前页面按钮级别的权限 */
function getAuths(): Array<string> {
  return router.currentRoute.value.meta.auths as Array<string>;
}

/** 是否有按钮级别的权限（根据路由`meta`中的`auths`字段进行判断）*/
function hasAuth(value: string | Array<string>): boolean {
  if (!value) return false;
  /** 从当前路由的`meta`字段里获取按钮级别的所有自定义`code`值 */
  const metaAuths = getAuths();
  if (!metaAuths) return false;
  const isAuths = isString(value)
    ? metaAuths.includes(value)
    : isIncludeAllChildren(value, metaAuths);
  return isAuths ? true : false;
}

function handleTopMenu(route) {
  if (!route?.children?.length) return route;
  // 授权树既可从页面开始，也可从多层目录开始，不假设首项必有子菜单。
  const child = route.children.find(cur => cur.path === route.redirect);
  return handleTopMenu(child || route.children[0]);
}

/** 获取所有菜单中的第一个菜单（顶级菜单）*/
function getTopMenu(tag = false): menuType {
  const topMenu = handleTopMenu(usePermissionStoreHook().wholeMenus[0]);
  if (tag && topMenu) useMultiTagsStoreHook().handleTags("push", topMenu);
  return topMenu;
}

export {
  hasAuth,
  getAuths,
  ascending,
  filterTree,
  initRouter,
  getTopMenu,
  addPathMatch,
  isOneOfArray,
  getHistoryMode,
  addAsyncRoutes,
  getParentPaths,
  findRouteByPath,
  handleAliveRoute,
  formatTwoStageRoutes,
  formatFlatteningRoutes,
  filterNoPermissionTree
};
