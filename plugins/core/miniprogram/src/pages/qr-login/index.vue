<script setup lang="ts">
import { onLoad } from "@dcloudio/uni-app";
import { ref } from "vue";
import { confirmPcWechatLogin } from "@/api/qrLogin";

const scene = ref("");
const loading = ref(true);
const submitting = ref(false);
const requiresPhone = ref(false);
const confirmed = ref(false);
const error = ref("");

function decode(value: unknown) {
  try { return decodeURIComponent(String(value || "").trim()); } catch { return String(value || "").trim(); }
}
function resolveScene(options: Record<string, any>) {
  const direct = decode(options.scene || options.token);
  if (direct) return direct;
  const launch = uni.getLaunchOptionsSync();
  const query = (launch.query || {}) as Record<string, any>;
  const fromLaunch = decode(query.scene || query.token);
  if (fromLaunch) return fromLaunch;
  const raw = decode((options.q || query.q) as string);
  return raw ? decode(raw.split("/").filter(Boolean).pop()) : "";
}
function wechatCode(): Promise<string> {
  return new Promise((resolve, reject) => {
    uni.login({ provider: "weixin", success: res => res.code ? resolve(res.code) : reject(new Error("微信登录凭证无效")), fail: reject });
  });
}
async function request(confirm: boolean, phoneCode?: string) {
  const code = await wechatCode();
  return confirmPcWechatLogin(scene.value, { code, phoneCode, confirm });
}
async function inspect() {
  try {
    const result = await request(false);
    requiresPhone.value = result.requires_phone;
  } catch (err) {
    error.value = (err as Error)?.message || "读取登录请求失败";
  } finally {
    loading.value = false;
  }
}
async function confirmBound() {
  submitting.value = true;
  try {
    await request(true);
    confirmed.value = true;
  } catch (err) {
    error.value = (err as Error)?.message || "确认登录失败";
  } finally { submitting.value = false; }
}
async function confirmWithPhone(event: any) {
  const phoneCode = event?.detail?.code;
  if (!phoneCode) {
    uni.showToast({ title: "需要授权手机号匹配已有账号", icon: "none" });
    return;
  }
  submitting.value = true;
  try {
    await request(true, phoneCode);
    confirmed.value = true;
    requiresPhone.value = false;
  } catch (err) {
    error.value = (err as Error)?.message || "确认登录失败";
  } finally { submitting.value = false; }
}
onLoad((options = {}) => {
  scene.value = resolveScene(options);
  if (!scene.value) {
    loading.value = false;
    error.value = "二维码参数缺失，请在电脑端刷新";
    return;
  }
  void inspect();
});
</script>

<template>
  <view class="page">
    <view class="card">
      <text class="title">PC 端微信登录</text>
      <text v-if="loading" class="hint">正在读取登录请求…</text>
      <template v-else-if="confirmed">
        <text class="success">登录已确认</text>
        <text class="hint">请返回电脑继续使用</text>
      </template>
      <template v-else-if="error">
        <text class="error">{{ error }}</text>
      </template>
      <template v-else>
        <text class="hint">确认后，电脑端将登录当前微信匹配的系统账号</text>
        <button v-if="requiresPhone" class="confirm" open-type="getPhoneNumber" :loading="submitting" @getphonenumber="confirmWithPhone">授权手机号并确认登录</button>
        <button v-else class="confirm" :loading="submitting" @tap="confirmBound">确认登录</button>
        <text class="notice">仅匹配管理员已创建的账号，不会自动注册或修改手机号</text>
      </template>
    </view>
  </view>
</template>

<style scoped>
.page { min-height: 100vh; padding: 120rpx 36rpx; box-sizing: border-box; background: #f4f7fb; }
.card { padding: 56rpx 40rpx; border-radius: 24rpx; background: #fff; box-shadow: 0 12rpx 40rpx rgba(15, 23, 42, .08); text-align: center; }
.title { display: block; margin-bottom: 32rpx; color: #0f172a; font-size: 40rpx; font-weight: 700; }
.hint, .notice { display: block; color: #64748b; font-size: 26rpx; line-height: 1.7; }
.confirm { margin-top: 44rpx; color: #fff; background: #16a34a; border-radius: 14rpx; }
.notice { margin-top: 28rpx; font-size: 22rpx; }
.success { display: block; margin-bottom: 16rpx; color: #16a34a; font-size: 36rpx; font-weight: 700; }
.error { color: #dc2626; font-size: 28rpx; line-height: 1.7; }
</style>

