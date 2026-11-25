<script setup lang="ts">
import { computed } from "vue";
import { discardFile, uploadPhoto, type ImageUploadItem } from "@/api/systemFile";

const props = withDefaults(
  defineProps<{
    modelValue: ImageUploadItem[];
    scene: string;
    title: string;
    disabled?: boolean;
  }>(),
  { disabled: false },
);

const emit = defineEmits<{
  "update:modelValue": [items: ImageUploadItem[]];
}>();

const MAX_PHOTOS = 9;

const items = computed({
  get: () => props.modelValue,
  set: (value) => emit("update:modelValue", value),
});

function patch(
  index: number,
  changes: Partial<ImageUploadItem> & { status: ImageUploadItem["status"] },
) {
  const next = items.value.slice();
  next[index] = { ...next[index], ...changes };
  items.value = next;
}

function remove(index: number) {
  const item = items.value[index];
  const next = items.value.slice();
  next.splice(index, 1);
  items.value = next;
  if (item?.attachment?.id)
    void discardFile(item.attachment.id).catch(() => undefined);
}

async function upload(localPath: string) {
  const index = items.value.length;
  items.value = [
    ...items.value,
    { status: "uploading", attachment: null, localPath },
  ];
  try {
    const id = await uploadPhoto(localPath, props.scene);
    patch(index, { status: "ready", attachment: { id } });
  } catch (error) {
    patch(index, {
      status: "error",
      error: error instanceof Error ? error.message : "照片上传失败",
    });
  }
}

function choose() {
  if (props.disabled) return;
  const remaining = MAX_PHOTOS - items.value.length;
  if (remaining <= 0)
    return uni.showToast({ title: `最多上传${MAX_PHOTOS}张照片`, icon: "none" });
  uni.chooseImage({
    count: remaining,
    sizeType: ["compressed"],
    sourceType: ["album", "camera"],
    success: (result) => {
      for (const path of result.tempFilePaths as string[]) void upload(path);
    },
  });
}

function preview(index: number) {
  const item = items.value[index];
  if (!item?.localPath) return;
  uni.previewImage({
    current: item.localPath,
    urls: items.value
      .map((entry) => entry.localPath)
      .filter((path): path is string => Boolean(path)),
  });
}
</script>

<template>
  <view class="image-upload">
    <text class="field-label">{{ title }}</text>
    <view class="photo-grid">
      <view
        v-for="(item, index) in items"
        :key="item.localPath || index"
        class="photo-cell"
      >
        <image
          :src="item.localPath"
          class="photo"
          mode="aspectFill"
          @tap="preview(index)"
        />
        <view v-if="item.status === 'uploading'" class="photo-mask">
          <text class="photo-status">上传中…</text>
        </view>
        <view v-else-if="item.status === 'error'" class="photo-mask photo-error">
          <text class="photo-status">{{ item.error || "上传失败" }}</text>
        </view>
        <button
          v-if="!disabled"
          class="photo-remove"
          @tap.stop="remove(index)"
        >
          ×
        </button>
      </view>
      <view
        v-if="!disabled && items.length < MAX_PHOTOS"
        class="photo-add"
        @tap="choose"
      >
        <text class="photo-add-icon">＋</text>
        <text class="photo-add-text">添加照片</text>
      </view>
    </view>
  </view>
</template>

<style scoped lang="scss">
.image-upload {
  margin: 24rpx 0 8rpx;
}
.field-label {
  display: block;
  color: #26364a;
  font-size: 27rpx;
  font-weight: 650;
  line-height: 1.6;
}
.photo-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 16rpx;
  margin-top: 16rpx;
}
.photo-cell,
.photo-add {
  position: relative;
  box-sizing: border-box;
  width: 200rpx;
  height: 200rpx;
  border-radius: 14rpx;
  overflow: hidden;
}
.photo-cell {
  background: #f2f5f9;
  border: 1rpx solid #e7ecf3;
}
.photo {
  width: 100%;
  height: 100%;
}
.photo-mask {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8rpx;
  background: rgba(22, 34, 56, 0.55);
}
.photo-mask.photo-error {
  background: rgba(181, 71, 53, 0.72);
}
.photo-status {
  color: #fff;
  font-size: 22rpx;
  line-height: 1.4;
  text-align: center;
  overflow-wrap: anywhere;
}
.photo-remove {
  position: absolute;
  top: 0;
  right: 0;
  box-sizing: border-box;
  width: 48rpx;
  height: 48rpx;
  padding: 0;
  margin: 0;
  color: #fff;
  font-size: 34rpx;
  line-height: 44rpx;
  text-align: center;
  background: rgba(22, 34, 56, 0.65);
  border-radius: 0 14rpx 0 14rpx;
}
.photo-remove::after {
  border: none;
}
.photo-add {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8rpx;
  color: #718096;
  background: #f7f9fc;
  border: 1rpx dashed #b9c6d6;
}
.photo-add-icon {
  color: #1769e0;
  font-size: 56rpx;
  line-height: 1;
}
.photo-add-text {
  font-size: 22rpx;
}
</style>
