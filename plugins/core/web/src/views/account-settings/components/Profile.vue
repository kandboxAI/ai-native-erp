<script setup lang="ts">
import { onMounted, ref } from "vue";
import { getMine, saveMyAvatar, type UserInfo } from "@/api/user";
import { discardFile, uploadFile } from "@/api/systemFile";
import ActionButton from "@/components/ActionButton/index.vue";
import { getHttpErrorMessage } from "@/utils/http";
import { useUserStoreHook } from "@/store/modules/user";
import { ElMessage } from "element-plus";

const emit = defineEmits<{ "avatar-changed": [url: string] }>();
const profile = ref<UserInfo | null>(null);
const error = ref("");
const avatarInput = ref<HTMLInputElement>();
const savingAvatar = ref(false);
const userStore = useUserStoreHook();
const avatarTypes = ["image/jpeg", "image/png", "image/webp"];

async function changeAvatar(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file || !profile.value || savingAvatar.value) return;
  if (!avatarTypes.includes(file.type) || file.size > 2 * 1024 * 1024) {
    ElMessage.warning("请选择 2 MB 以内的 JPG、PNG 或 WebP 图片");
    return;
  }
  savingAvatar.value = true;
  let fileId: string | undefined;
  try {
    fileId = (await uploadFile(file, "user_avatar")).id;
    const result = await saveMyAvatar(fileId);
    if (result.code !== 0) throw new Error(result.message || "头像保存失败");
    fileId = undefined;
    const url = result.data.avatar_url;
    profile.value.avatar_url = url;
    userStore.SET_AVATAR(url);
    emit("avatar-changed", url);
    ElMessage.success("头像已更新");
  } catch (error) {
    if (fileId) await discardFile(fileId).catch(() => undefined);
    ElMessage.error(getHttpErrorMessage(error, "头像更新失败，请重试"));
  } finally {
    savingAvatar.value = false;
  }
}
onMounted(async () => {
  try {
    const response = await getMine();
    if (response.code === 0) profile.value = response.data;
    else error.value = response.message || "个人信息加载失败";
  } catch {
    error.value = "个人信息加载失败";
  }
});
</script>
<template>
  <section class="p-6">
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-descriptions v-else-if="profile" title="个人信息" :column="1" border>
      <el-descriptions-item label="显示名称">{{
        profile.display_name
      }}</el-descriptions-item>
      <el-descriptions-item label="姓名">{{
        profile.full_name
      }}</el-descriptions-item>
      <el-descriptions-item label="邮箱">{{
        profile.email
      }}</el-descriptions-item>
      <el-descriptions-item label="手机号">{{
        profile.mobile
      }}</el-descriptions-item>
      <el-descriptions-item label="当前租户">{{
        profile.tenant_name
      }}</el-descriptions-item>
    </el-descriptions>
    <section v-if="profile" class="avatar-settings">
      <h2>更换头像</h2>
      <div class="avatar-settings-content">
        <el-avatar :size="64" :src="profile.avatar_url">
          {{ profile.display_name?.slice(0, 1) || "用" }}
        </el-avatar>
        <div>
          <input ref="avatarInput" type="file" accept="image/jpeg,image/png,image/webp" hidden @change="changeAvatar" />
          <ActionButton intent="upload" :loading="savingAvatar" :disabled="savingAvatar" @click="avatarInput?.click()">
            上传头像
          </ActionButton>
          <p>支持 JPG、PNG、WebP，最大 2 MB。</p>
        </div>
      </div>
    </section>
  </section>
</template>

<style scoped>
.avatar-settings {
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid var(--el-border-color-light);
}
.avatar-settings h2 {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 600;
}
.avatar-settings-content {
  display: flex;
  align-items: center;
  gap: 16px;
}
.avatar-settings-content p {
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
