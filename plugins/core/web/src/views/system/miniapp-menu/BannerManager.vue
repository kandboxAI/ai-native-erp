<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox, type UploadFile } from "element-plus";
import { UploadFilled } from "@element-plus/icons-vue";
import { hasPerms } from "@/utils/auth";
import { discardFile, uploadFile, type FileItem } from "@/api/systemFile";
import {
  deleteMiniappBanner,
  listMiniappBanners,
  saveMiniappBanner,
  type MiniappBanner
} from "@/api/miniappBanner";
import { apiErrorMessage } from "@/views/system/role-management/utils";

const rows = ref<MiniappBanner[]>([]);
const loading = ref(false);
const saving = ref(false);
const editing = ref(false);
const editingId = ref<string | null>(null);
const draft = reactive({ sort_no: 0, is_active: true, file_id: "" });
const preview = ref("");
let localPreview = "";
let selectedFile: File | null = null;
let uploaded: FileItem | null = null;
const canSave = computed(() =>
  hasPerms(editingId.value ? "miniapp_menu:update" : "miniapp_menu:create")
);

async function load() {
  loading.value = true;
  try {
    rows.value = (await listMiniappBanners()).data.items;
  } catch (error) {
    ElMessage.error(apiErrorMessage(error));
  } finally {
    loading.value = false;
  }
}

function clearSelection() {
  if (localPreview) URL.revokeObjectURL(localPreview);
  localPreview = "";
  selectedFile = null;
  if (uploaded) void discardFile(uploaded.id).catch(() => undefined);
  uploaded = null;
}

function open(row?: MiniappBanner) {
  clearSelection();
  editingId.value = row?.id || null;
  Object.assign(draft, {
    sort_no: row?.sort_no || 0,
    is_active: row?.is_active ?? true,
    file_id: row?.image?.id || ""
  });
  preview.value = row?.image?.url || "";
  editing.value = true;
}

function selectImage(file: UploadFile) {
  const raw = file.raw;
  if (
    !raw ||
    !["image/jpeg", "image/png", "image/webp"].includes(raw.type) ||
    raw.size > 2 * 1024 * 1024
  ) {
    ElMessage.warning(
      "请选择不超过 2MB 的 JPG、PNG 或 WebP 图片，超出请先压缩"
    );
    return;
  }
  clearSelection();
  selectedFile = raw;
  localPreview = URL.createObjectURL(raw);
  preview.value = localPreview;
}

async function save() {
  if (saving.value || !canSave.value) return;
  if (!selectedFile && !draft.file_id) {
    ElMessage.warning("请选择轮播图片");
    return;
  }
  saving.value = true;
  try {
    if (selectedFile && !uploaded)
      uploaded = await uploadFile(selectedFile, "miniapp_banner");
    await saveMiniappBanner(editingId.value, {
      ...draft,
      file_id: uploaded?.id || draft.file_id
    });
    // 已提交的图片由业务记录管理，不再作为待提交文件清理。
    uploaded = null;
    clearSelection();
    editing.value = false;
    ElMessage.success("轮播图已保存");
    await load();
  } catch (error) {
    ElMessage.error(apiErrorMessage(error));
  } finally {
    saving.value = false;
  }
}

async function remove(row: MiniappBanner) {
  try {
    await ElMessageBox.confirm("确认删除这张轮播图？", "删除轮播图", {
      confirmButtonClass: "app-button-danger",
      type: "warning"
    });
  } catch {
    return;
  }
  try {
    await deleteMiniappBanner(row.id);
    ElMessage.success("已删除");
    await load();
  } catch (error) {
    ElMessage.error(apiErrorMessage(error));
  }
}

onMounted(load);
onBeforeUnmount(clearSelection);
</script>

<template>
  <div class="list-page">
    <div class="banner-toolbar">
      <p>
        图片按排序号从小到大展示，首页轮播最多展示前 10
        张已启用图片。图片归属创建账号的当前组织，展示给该组织及其下级组织。
      </p>
    </div>
    <ReListTable
      list-key="BannerManager-0"
      list-local
      :list-refresh="load"
      v-loading="loading"
      :data="rows"
      row-key="id"
      empty-text="尚未配置轮播图片"
    >
      <el-table-column label="图片" width="180">
        <template #default="{ row }"
          ><el-image
            v-if="row.image"
            class="banner-thumbnail"
            :src="row.image.url"
            fit="cover"
            :preview-src-list="[row.image.url]"
            preview-teleported
        /></template>
      </el-table-column>
      <el-table-column prop="sort_no" label="排序" width="90" />
      <el-table-column prop="is_active" label="状态" width="90"
        ><template #default="{ row }"
          ><el-tag :type="row.is_active ? 'success' : 'info'">{{
            row.is_active ? "启用" : "停用"
          }}</el-tag></template
        ></el-table-column
      >
      <el-table-column label="操作" width="150"
        ><template #default="{ row }">
          <el-button
            data-list-action="edit"
            v-if="hasPerms('miniapp_menu:update')"
            link
            type="primary"
            @click="open(row as MiniappBanner)"
            >编辑</el-button
          >
          <el-button
            data-list-action="delete"
            v-if="hasPerms('miniapp_menu:delete')"
            link
            type="danger"
            @click="remove(row as MiniappBanner)"
            >删除</el-button
          >
        </template></el-table-column
      >

      <template #list-actions
        ><el-button
          data-list-action="create"
          v-if="hasPerms('miniapp_menu:create')"
          type="primary"
          @click="open()"
          >新增轮播图</el-button
        ></template
      >
    </ReListTable>
    <el-dialog
      v-model="editing"
      :title="editingId ? '编辑轮播图' : '新增轮播图'"
      width="600px"
      class="banner-editor"
      align-center
      append-to-body
      :close-on-click-modal="!saving"
      :close-on-press-escape="!saving"
      :show-close="!saving"
      @closed="clearSelection"
    >
      <el-form :model="draft" label-position="top" :disabled="saving">
        <el-form-item label="轮播图片" required>
          <div class="banner-image-field">
            <el-upload
              class="banner-upload"
              drag
              accept="image/jpeg,image/png,image/webp"
              :auto-upload="false"
              :show-file-list="false"
              :on-change="selectImage"
              :disabled="saving"
            >
              <div v-if="preview" class="banner-preview-wrap">
                <el-image
                  :src="preview"
                  class="banner-preview"
                  fit="cover"
                  alt="轮播图片预览"
                />
                <span class="banner-replace">点击或拖拽更换图片</span>
              </div>
              <div v-else class="banner-upload-placeholder">
                <el-icon class="banner-upload-icon"><UploadFilled /></el-icon>
                <span class="banner-upload-title"
                  >点击选择图片，或拖拽到此处</span
                >
                <span class="banner-upload-description"
                  >建议使用宽高比约 2.1:1 的横向图片</span
                >
              </div>
            </el-upload>
            <div class="banner-tip">
              <p>支持 JPG / PNG / WebP，单张不超过 2MB，超出请先压缩。</p>
              <p>为保证展示效果，请避免将重要内容放在图片边缘。</p>
            </div>
          </div>
        </el-form-item>
        <div class="banner-settings">
          <el-form-item label="排序">
            <el-input-number v-model="draft.sort_no" :min="0" :max="999999" />
            <p class="banner-tip">数值越小，展示越靠前</p>
          </el-form-item>
          <el-form-item label="状态">
            <div class="banner-status">
              <el-switch v-model="draft.is_active" aria-label="启用轮播图" />
              <span>{{ draft.is_active ? "已启用" : "已停用" }}</span>
            </div>
            <p class="banner-tip">
              {{
                draft.is_active
                  ? "保存后参与首页轮播展示"
                  : "保存后不在首页展示"
              }}
            </p>
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button
          data-action="neutral"
          :disabled="saving"
          @click="editing = false"
          >取消</el-button
        >
        <el-button
          data-action="primary"
          type="primary"
          :loading="saving"
          :disabled="!canSave"
          @click="save"
          >保存</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.banner-toolbar {
  display: flex;
  gap: 20px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.banner-toolbar p,
.banner-tip {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}
.banner-thumbnail {
  width: 150px;
  height: 56px;
  border-radius: 8px;
}
.banner-image-field {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: 10px;
}
.banner-tip {
  width: 100%;
  margin: 0;
}
.banner-tip p {
  margin: 0;
}
.banner-upload,
.banner-upload :deep(.el-upload) {
  width: 100%;
}
.banner-upload :deep(.el-upload-dragger) {
  padding: 0;
  overflow: hidden;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
}
.banner-upload-placeholder,
.banner-preview-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 2.1 / 1;
}
.banner-upload-placeholder {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  justify-content: center;
  padding: 16px;
  line-height: 1.6;
}
.banner-upload-icon {
  margin-bottom: 4px;
  color: var(--el-color-primary);
  font-size: 36px;
}
.banner-upload-title {
  color: var(--el-text-color-primary);
  font-weight: 500;
}
.banner-upload-description {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.banner-preview {
  display: block;
  width: 100%;
  height: 100%;
}
.banner-replace {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  padding: 8px 12px;
  color: #fff;
  font-size: 13px;
  line-height: 1.6;
  text-align: center;
  background: rgb(0 0 0 / 45%);
}
.banner-settings {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px 24px;
  padding-top: 20px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.banner-settings :deep(.el-form-item) {
  min-width: 0;
  margin-bottom: 0;
}
.banner-settings :deep(.el-input-number) {
  width: 100%;
}
.banner-settings .banner-tip {
  margin-top: 8px;
  font-size: 12px;
}
.banner-status {
  display: flex;
  min-height: 32px;
  gap: 10px;
  align-items: center;
}
@media (width <= 480px) {
  .banner-settings {
    grid-template-columns: 1fr;
  }
  .banner-upload-title {
    font-size: 13px;
  }
}
</style>

<style>
.banner-editor.el-dialog {
  max-width: calc(100vw - 32px);
  padding: 0;
  overflow: hidden;
  border-radius: 12px;
}
.banner-editor .el-dialog__header {
  padding: 20px 24px 16px;
  margin: 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.banner-editor .el-dialog__header.show-close {
  padding-right: 48px;
}
.banner-editor .el-dialog__headerbtn {
  top: 14px;
  right: 16px;
  width: 32px;
  height: 32px;
}
.banner-editor .el-dialog__body {
  max-height: min(65vh, calc(100dvh - 180px));
  padding: 20px 24px 24px;
  overflow-y: auto;
}
.banner-editor .el-dialog__footer {
  padding: 16px 24px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.banner-editor .el-dialog__footer .el-button {
  min-width: 80px;
}
</style>
