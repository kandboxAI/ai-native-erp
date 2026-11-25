<script setup lang="ts">
import { match } from "pinyin-pro";
import { ElDialog } from "element-plus";
import { useI18n } from "vue-i18n";
import { getConfig } from "@/config";
import { useRouter } from "vue-router";
import SearchResult from "./SearchResult.vue";
import SearchFooter from "./SearchFooter.vue";
import { useNav } from "@/layout/hooks/useNav";
import { transformI18n } from "@/plugins/i18n";
import SearchHistory from "./SearchHistory.vue";
import type { optionsItem, dragItem } from "../types";
import {
  onBeforeUnmount,
  onMounted,
  ref,
  computed,
  shallowRef,
  watch
} from "vue";
import { onClickOutside, useDebounceFn } from "@vueuse/core";
import { usePermissionStoreHook } from "@/store/modules/permission";
import { cloneDeep, isAllEmpty, storageLocal } from "@pureadmin/utils";
import SearchIcon from "~icons/ri/search-line";
import {
  askDesktopAssistant,
  continueDesktopAssistant
} from "@/utils/desktopAssistant";

interface Props {
  /** 弹窗显隐 */
  value: boolean;
  /** 总览大搜索框内嵌展示，共用菜单、历史和收藏逻辑。 */
  inline?: boolean;
}

interface Emits {
  (e: "update:value", val: boolean): void;
  (e: "ask", message: string): void;
}

const { device } = useNav();
const emit = defineEmits<Emits>();
const props = withDefaults(defineProps<Props>(), { inline: false });

const router = useRouter();
const { t, locale } = useI18n();

const HISTORY_TYPE = "history";
const COLLECT_TYPE = "collect";
const LOCALEHISTORYKEY = "menu-search-history";
const LOCALECOLLECTKEY = "menu-search-collect";

const keyword = defineModel<string>("keyword", { default: "" });
const rootRef = ref<HTMLElement>();
const resultRef = ref();
const historyRef = ref();
const scrollbarRef = ref();
const activePath = ref("");
const historyPath = ref("");
const resultOptions = shallowRef([]);
const historyOptions = shallowRef([]);
const handleSearch = useDebounceFn(search, 300);
const historyNum = getConfig().MenuSearchHistory;
const inputRef = ref<HTMLInputElement | null>(null);
const isErpDesktop = Boolean(window.erpDesktop);

/** 菜单树形结构 */
const menusData = computed(() => {
  return cloneDeep(usePermissionStoreHook().wholeMenus);
});

const show = computed({
  get() {
    return props.value;
  },
  set(val: boolean) {
    emit("update:value", val);
  }
});

const dialogProps = computed(() =>
  props.inline
    ? {}
    : {
        modelValue: show.value,
        alignCenter: true,
        showClose: false,
        width: device.value === "mobile" ? "88vw" : "640px",
        beforeClose: handleClose,
        style: { borderRadius: "6px" },
        appendToBody: true
      }
);

watch(keyword, handleSearch);
watch(menusData, () => {
  search();
  getHistory();
});
onClickOutside(rootRef, () => {
  if (props.inline) show.value = false;
});

function openSearch() {
  show.value = true;
  getHistory();
  search();
}

function setKeyword(value: string) {
  keyword.value = value;
  show.value = true;
}

watch(
  () => props.value,
  newValue => {
    if (!newValue) return;
    getHistory();
    if (isErpDesktop && !props.inline)
      void window.erpDesktop?.setAssistantObscured(true);
  },
  { immediate: true, flush: "sync" }
);

const showSearchResult = computed(() => {
  return keyword.value.trim() && resultOptions.value.length > 0;
});

const showSearchHistory = computed(() => {
  return !keyword.value.trim() && historyOptions.value.length > 0;
});

const showAskAi = computed(() => {
  return (
    isErpDesktop &&
    keyword.value.trim().length > 0 &&
    resultOptions.value.length === 0
  );
});

const showEmpty = computed(() => {
  return (
    (!keyword.value && historyOptions.value.length === 0) ||
    (keyword.value && resultOptions.value.length === 0 && !showAskAi.value)
  );
});

function getStorageItem(key) {
  return storageLocal().getItem<optionsItem[]>(key) || [];
}

function setStorageItem(key, value) {
  storageLocal().setItem(key, value);
}

/** 将菜单树形结构扁平化为一维数组，用于菜单查询 */
function flatTree(arr) {
  const res = [];
  function deep(arr, parentIcon?) {
    arr.forEach(item => {
      if (!item.children || item.children.length === 0) {
        const menuItem =
          !item.meta?.icon && parentIcon
            ? { ...item, meta: { ...item.meta, icon: parentIcon } }
            : item;
        res.push(menuItem);
      } else {
        deep(item.children, item.meta?.icon);
      }
    });
  }
  deep(arr);
  return res;
}

/** 查询 */
function search() {
  const query = keyword.value.trim().toLocaleLowerCase();
  const flatMenusData = flatTree(menusData.value);
  resultOptions.value = flatMenusData.filter(menu =>
    query
      ? transformI18n(menu.meta?.title).toLocaleLowerCase().includes(query) ||
        (locale.value === "zh" &&
          !isAllEmpty(
            match(transformI18n(menu.meta?.title).toLocaleLowerCase(), query)
          ))
      : false
  );
  // 提交时重新匹配，但保留方向键或鼠标已经选中的菜单。
  if (!resultOptions.value.some(item => item.path === activePath.value)) {
    activePath.value = resultOptions.value[0]?.path ?? "";
  }
}

function handleClose() {
  show.value = false;
  if (props.inline) return;
  /** 延时处理防止用户看到某些操作 */
  setTimeout(() => {
    resultOptions.value = [];
    historyPath.value = "";
    keyword.value = "";
  }, 200);
}

function handleDialogClosed() {
  inputRef.value?.blur();
  if (isErpDesktop && !props.inline && !show.value)
    void window.erpDesktop?.setAssistantObscured(false);
}

function scrollTo(index) {
  const ref = resultOptions.value.length ? resultRef.value : historyRef.value;
  const scrollTop = ref.handleScroll(
    index,
    scrollbarRef.value.wrapRef?.clientHeight
  );
  scrollbarRef.value.setScrollTop(scrollTop);
}

/** 获取当前选项和路径 */
function getCurrentOptionsAndPath() {
  const isResultOptions = resultOptions.value.length > 0;
  const options = isResultOptions ? resultOptions.value : historyOptions.value;
  const currentPath = isResultOptions ? activePath.value : historyPath.value;
  return { options, currentPath, isResultOptions };
}

/** 更新路径并滚动到指定项 */
function updatePathAndScroll(newIndex, isResultOptions) {
  if (isResultOptions) {
    activePath.value = resultOptions.value[newIndex].path;
  } else {
    historyPath.value = historyOptions.value[newIndex].path;
  }
  scrollTo(newIndex);
}

/** key up */
function handleUp() {
  if (!show.value) {
    openSearch();
    return;
  }
  search();
  if (keyword.value.trim() && !resultOptions.value.length) return;
  const { options, currentPath, isResultOptions } = getCurrentOptionsAndPath();
  if (options.length === 0) return;
  const index = options.findIndex(item => item.path === currentPath);
  const prevIndex = (index - 1 + options.length) % options.length;
  updatePathAndScroll(prevIndex, isResultOptions);
}

/** key down */
function handleDown() {
  if (!show.value) {
    openSearch();
    return;
  }
  search();
  if (keyword.value.trim() && !resultOptions.value.length) return;
  const { options, currentPath, isResultOptions } = getCurrentOptionsAndPath();
  if (options.length === 0) return;
  const index = options.findIndex(item => item.path === currentPath);
  const nextIndex = (index + 1) % options.length;
  updatePathAndScroll(nextIndex, isResultOptions);
}

/** key enter */
function handleEnter() {
  search();
  if (showAskAi.value) {
    openAiAgent();
    return;
  }
  const { options, currentPath, isResultOptions } = getCurrentOptionsAndPath();
  if (options.length === 0 || currentPath === "") {
    return;
  }
  const index = options.findIndex(item => item.path === currentPath);
  if (index === -1) return;
  if (isResultOptions) {
    saveHistory();
  } else {
    updateHistory();
  }
  router.push(options[index].path);
  handleClose();
}

async function openAiAgent() {
  search();
  if (!showAskAi.value) return;
  const message = keyword.value.trim();
  if (!message) return;
  if (props.inline) {
    emit("ask", message);
    handleClose();
    return;
  }
  if (!isErpDesktop) return;
  await askDesktopAssistant(router, message);
  handleClose();
}

async function openRecentSession() {
  await continueDesktopAssistant(router);
  handleClose();
}

function handleCommandShortcut(event: KeyboardEvent) {
  if (event.key === "Escape" && show.value) {
    event.preventDefault();
    event.stopPropagation();
    handleClose();
    return;
  }

  const isCommandK =
    (event.ctrlKey || event.metaKey) &&
    (event.code === "KeyK" || event.key.toLowerCase() === "k");

  if (!isCommandK) return;

  event.preventDefault();
  event.stopPropagation();
  // 总览优先使用大框，其他页面仍打开顶部命令面板。
  const overviewInput = document.querySelector<HTMLInputElement>(
    ".overview-content [data-menu-search-input]"
  );
  if (!show.value && overviewInput) {
    overviewInput.focus();
    overviewInput.click();
    return;
  }
  show.value = true;
}

/** 删除历史记录 */
function handleDelete(item) {
  const key = item.type === HISTORY_TYPE ? LOCALEHISTORYKEY : LOCALECOLLECTKEY;
  let list = getStorageItem(key);
  list = list.filter(listItem => listItem.path !== item.path);
  setStorageItem(key, list);
  getHistory();
}

/** 收藏历史记录 */
function handleCollect(item) {
  let searchHistoryList = getStorageItem(LOCALEHISTORYKEY);
  let searchCollectList = getStorageItem(LOCALECOLLECTKEY);
  searchHistoryList = searchHistoryList.filter(
    historyItem => historyItem.path !== item.path
  );
  setStorageItem(LOCALEHISTORYKEY, searchHistoryList);
  if (!searchCollectList.some(collectItem => collectItem.path === item.path)) {
    searchCollectList.unshift({ ...item, type: COLLECT_TYPE });
    setStorageItem(LOCALECOLLECTKEY, searchCollectList);
  }
  getHistory();
}

/** 存储搜索记录 */
function saveHistory() {
  const { path, meta } = resultOptions.value.find(
    item => item.path === activePath.value
  );
  const searchHistoryList = getStorageItem(LOCALEHISTORYKEY);
  const searchCollectList = getStorageItem(LOCALECOLLECTKEY);
  const isCollected = searchCollectList.some(item => item.path === path);
  const existingIndex = searchHistoryList.findIndex(item => item.path === path);
  if (!isCollected) {
    if (existingIndex !== -1) searchHistoryList.splice(existingIndex, 1);
    if (searchHistoryList.length >= historyNum) searchHistoryList.pop();
    searchHistoryList.unshift({ path, meta, type: HISTORY_TYPE });
    storageLocal().setItem(LOCALEHISTORYKEY, searchHistoryList);
  }
}

/** 更新存储的搜索记录 */
function updateHistory() {
  let searchHistoryList = getStorageItem(LOCALEHISTORYKEY);
  const historyIndex = searchHistoryList.findIndex(
    item => item.path === historyPath.value
  );
  if (historyIndex !== -1) {
    const [historyItem] = searchHistoryList.splice(historyIndex, 1);
    searchHistoryList.unshift(historyItem);
    setStorageItem(LOCALEHISTORYKEY, searchHistoryList);
  }
}

/** 获取本地历史记录 */
function getHistory() {
  const searchHistoryList = getStorageItem(LOCALEHISTORYKEY);
  const searchCollectList = getStorageItem(LOCALECOLLECTKEY);
  const authorizedMenus = new Map(
    flatTree(menusData.value).map(item => [item.path, item])
  );
  // 本地记录可能来自旧授权；仅展示当前仍可访问的菜单及其最新名称。
  historyOptions.value = [...searchHistoryList, ...searchCollectList].flatMap(
    item => {
      const menu = authorizedMenus.get(item.path);
      return menu ? [{ ...item, meta: menu.meta }] : [];
    }
  );
  historyPath.value = historyOptions.value[0]?.path;
}

/** 拖拽改变收藏顺序 */
function handleDrag(item: dragItem) {
  const searchCollectList = historyOptions.value.filter(
    option => option.type === COLLECT_TYPE
  );
  const visiblePaths = new Set(searchCollectList.map(option => option.path));
  const [reorderedItem] = searchCollectList.splice(item.oldIndex, 1);
  searchCollectList.splice(item.newIndex, 0, reorderedItem);
  setStorageItem(LOCALECOLLECTKEY, [
    ...searchCollectList,
    ...getStorageItem(LOCALECOLLECTKEY).filter(
      option => !visiblePaths.has(option.path)
    )
  ]);
  getHistory();
  historyPath.value = reorderedItem.path;
}

onMounted(() => {
  if (!props.inline)
    window.addEventListener("keydown", handleCommandShortcut, true);
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleCommandShortcut, true);
  if (isErpDesktop && !props.inline)
    void window.erpDesktop?.setAssistantObscured(false);
});
</script>

<template>
  <component
    :is="inline ? 'div' : ElDialog"
    ref="rootRef"
    :class="inline ? 'inline-menu-search' : 'pure-search-dialog'"
    v-bind="dialogProps"
    @update:model-value="show = $event"
    @opened="inputRef?.focus()"
    @closed="handleDialogClosed"
  >
    <template #header>
      <div class="command-dialog-header">
        <span>{{ isErpDesktop ? "搜索菜单或询问 AI" : "搜索菜单" }}</span>
        <kbd>Esc</kbd>
      </div>
    </template>
    <slot
      name="entry"
      v-bind="{
        keyword,
        setKeyword,
        openSearch,
        handleEnter,
        handleUp,
        handleDown,
        handleClose
      }"
    >
      <el-input
        ref="inputRef"
        v-model="keyword"
        size="large"
        clearable
        :placeholder="
          isErpDesktop
            ? t('search.commandPlaceholder')
            : '搜索菜单（支持拼音搜索）'
        "
        @keydown.down.prevent="handleDown"
        @keydown.up.prevent="handleUp"
        @keydown.enter.prevent="handleEnter"
        @keydown.esc.prevent="handleClose"
      >
        <template #prefix>
          <IconifyIconOffline :icon="SearchIcon" class="text-primary size-6" />
        </template>
      </el-input>
    </slot>
    <div v-if="!inline || show" class="search-content">
      <el-scrollbar
        ref="scrollbarRef"
        :max-height="inline ? 'min(400px, 50vh)' : 'calc(90vh - 140px)'"
      >
        <el-empty v-if="showEmpty" :description="t('search.pureEmpty')" />
        <SearchHistory
          v-if="showSearchHistory"
          ref="historyRef"
          v-model:value="historyPath"
          :options="historyOptions"
          @enter="handleEnter"
          @delete="handleDelete"
          @collect="handleCollect"
          @drag="handleDrag"
        />
        <SearchResult
          v-if="showSearchResult"
          ref="resultRef"
          v-model:value="activePath"
          :options="resultOptions"
          @enter="handleEnter"
        />
        <button
          v-if="showAskAi"
          type="button"
          class="command-ai-result"
          @click="openAiAgent"
        >
          <span class="command-ai-result__title">{{ t("search.askAi") }}</span>
          <span class="command-ai-result__query">{{ keyword.trim() }}</span>
          <span class="command-ai-result__tag">AI</span>
        </button>
      </el-scrollbar>
      <SearchFooter v-if="inline" :total="resultOptions.length" />
    </div>
    <template #footer>
      <div class="command-dialog-footer">
        <SearchFooter :total="resultOptions.length" />
        <button
          v-if="isErpDesktop && !keyword.trim()"
          type="button"
          class="command-recent-session"
          @click="openRecentSession"
        >
          <IconifyIconOnline icon="ri:history-line" />
          继续最近会话
          <IconifyIconOnline icon="ri:arrow-right-s-line" />
        </button>
      </div>
    </template>
  </component>
</template>

<style lang="scss" scoped>
.inline-menu-search {
  position: relative;

  > .search-content {
    position: absolute;
    top: 100%;
    z-index: 10;
    width: 100%;
    padding: 16px;
    background: var(--el-bg-color);
    border: 1px solid var(--el-border-color-light);
    border-radius: 8px;
    box-shadow: var(--el-box-shadow-light);
  }
}

.search-content {
  margin-top: 12px;
}

.command-dialog-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}

.command-recent-session {
  display: inline-flex;
  gap: 7px;
  align-items: center;
  padding: 7px 10px;
  margin-left: auto;
  font: inherit;
  font-size: 12px;
  color: var(--el-color-primary);
  cursor: pointer;
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 7px;
}

.command-recent-session:hover,
.command-recent-session:focus-visible {
  background: var(--el-color-primary-light-8);
}

.command-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-right: 4px;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);

  kbd {
    padding: 2px 7px;
    font-family: inherit;
    font-size: 11px;
    font-weight: 400;
    color: var(--el-text-color-secondary);
    background: var(--el-fill-color-light);
    border: 1px solid var(--el-border-color);
    border-radius: 4px;
  }
}

.command-ai-result {
  display: flex;
  gap: 10px;
  align-items: center;
  width: 100%;
  padding: 14px;
  margin-top: 8px;
  color: var(--el-color-primary);
  text-align: left;
  cursor: pointer;
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 6px;

  &:hover,
  &:focus-visible {
    outline: none;
    background: var(--el-color-primary-light-8);
  }

  &__title {
    font-weight: 600;
  }

  &__query {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--el-text-color-secondary);
    white-space: nowrap;
  }

  &__tag {
    padding: 2px 6px;
    font-size: 11px;
    background: var(--el-color-primary-light-7);
    border-radius: 4px;
  }
}
</style>
