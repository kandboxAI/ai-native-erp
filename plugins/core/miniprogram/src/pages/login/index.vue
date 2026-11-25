<script setup lang="ts">
import { onLoad } from "@dcloudio/uni-app";
import { ref } from "vue";
import { getLoginCaptcha, loginWithAccount, loginWithWechatMiniapp } from "@/api/auth";
import { ApiError } from "@/api/client";
import { appStore, bootstrapStore } from "@/store/app";
import { takeTodoEntry } from "@/utils/todoEntry";

const account = ref("");
const password = ref("");
const captchaId = ref("");
const captchaCode = ref("");
const captchaImage = ref("");
const captchaLoading = ref(false);
const loggingIn = ref(false);
const wechatLoggingIn = ref(false);
const needsWechatPhone = ref(false);
const showPassword = ref(false);
const branding = __PRODUCT_BRANDING__;
const logoFailed = ref(false);

function enterDefaultPage() {
  const todoTarget = takeTodoEntry();
  if (todoTarget) {
    uni.reLaunch({ url: todoTarget });
    return;
  }
  uni.switchTab({ url: "/pages/messages/index" });
}

async function loadCaptcha() {
  if (captchaLoading.value) return;
  captchaLoading.value = true;
  try {
    const result = await getLoginCaptcha();
    captchaId.value = result.captchaId;
    captchaImage.value = result.image;
  } catch (error) {
    captchaId.value = "";
    captchaImage.value = "";
    uni.showToast({
      title: (error as Error)?.message || "验证码加载失败",
      icon: "none",
    });
  } finally {
    captchaLoading.value = false;
  }
}

async function handleLogin() {
  const loginAccount = account.value.trim();
  if (!loginAccount || !password.value || !captchaCode.value.trim()) {
    uni.showToast({ title: "请完整填写账号、密码和验证码", icon: "none" });
    return;
  }
  if (!captchaId.value) {
    uni.showToast({ title: "请先获取验证码", icon: "none" });
    await loadCaptcha();
    return;
  }

  loggingIn.value = true;
  try {
    const session = await loginWithAccount({
      account: loginAccount,
      password: password.value,
      captchaId: captchaId.value,
      captchaCode: captchaCode.value.trim(),
    });
    appStore.loginAccount(session);
    uni.showToast({ title: "登录成功", icon: "success" });
    setTimeout(enterDefaultPage, 300);
  } catch (error) {
    uni.showToast({
      title: (error as Error)?.message || "登录失败，请稍后重试",
      icon: "none",
    });
    captchaCode.value = "";
    await loadCaptcha();
  } finally {
    loggingIn.value = false;
  }
}

function getWechatLoginCode(): Promise<string> {
  return new Promise((resolve, reject) => {
    uni.login({
      provider: "weixin",
      success: (result) => {
        if (result.code) resolve(result.code);
        else reject(new Error("微信登录未返回有效凭证"));
      },
      fail: () => reject(new Error("微信登录授权失败，请稍后重试")),
    });
  });
}

function finishWechatLogin(session: Awaited<ReturnType<typeof loginWithWechatMiniapp>>) {
  appStore.loginAccount(session);
  uni.showToast({ title: "登录成功", icon: "success" });
  setTimeout(enterDefaultPage, 300);
}

async function handleWechatLogin() {
  if (wechatLoggingIn.value) return;
  wechatLoggingIn.value = true;
  try {
    const code = await getWechatLoginCode();
    finishWechatLogin(await loginWithWechatMiniapp({ code }));
  } catch (error) {
    if (error instanceof ApiError && error.statusCode === 428) {
      needsWechatPhone.value = true;
      uni.showToast({ title: "首次登录请授权手机号", icon: "none" });
    } else {
      uni.showToast({
        title: (error as Error)?.message || "微信登录失败，请稍后重试",
        icon: "none",
      });
    }
  } finally {
    wechatLoggingIn.value = false;
  }
}

async function handleWechatPhone(event: any) {
  const phoneCode = String(event?.detail?.code || "").trim();
  if (!phoneCode) {
    uni.showToast({ title: "需要授权手机号才能匹配系统账号", icon: "none" });
    return;
  }
  if (wechatLoggingIn.value) return;
  wechatLoggingIn.value = true;
  try {
    const code = await getWechatLoginCode();
    finishWechatLogin(await loginWithWechatMiniapp({ code, phoneCode }));
  } catch (error) {
    uni.showToast({
      title: (error as Error)?.message || "微信登录失败，请稍后重试",
      icon: "none",
    });
  } finally {
    wechatLoggingIn.value = false;
  }
}

onLoad(() => {
  bootstrapStore();
  if (appStore.state.loggedIn && appStore.state.account) {
    enterDefaultPage();
    return;
  }
  loadCaptcha();
});
</script>

<template>
  <view class="login-page">
    <view class="brand-panel">
      <image v-if="branding.miniapp_logo && !logoFailed" :src="branding.miniapp_logo"
        class="brand-mark" mode="aspectFit" @error="logoFailed = true" />
      <view v-else class="brand-mark">{{ branding.mark }}</view>
      <view class="brand-copy">
        <text class="brand-name">{{ branding.title }}</text>
        <text class="brand-slogan">{{ branding.subtitle }}</text>
      </view>
    </view>

    <view class="login-card">
      <view class="card-heading">
        <text class="card-title">账号登录</text>
        <text class="card-tip">使用 PC 管理端已创建的账号登录</text>
      </view>

      <view class="field">
        <text class="field-label">账号</text>
        <input
          v-model="account"
          class="field-input"
          type="text"
          placeholder="请输入用户名、邮箱或手机号"
          confirm-type="next"
        />
      </view>

      <view class="field">
        <text class="field-label">密码</text>
        <view class="password-row">
          <input
            v-model="password"
            class="field-input password-input"
            :password="!showPassword"
            placeholder="请输入密码"
            confirm-type="next"
          />
          <text class="password-toggle" @click="showPassword = !showPassword">
            {{ showPassword ? "隐藏" : "显示" }}
          </text>
        </view>
      </view>

      <view class="field">
        <text class="field-label">验证码</text>
        <view class="captcha-row">
          <input
            v-model="captchaCode"
            class="field-input captcha-input"
            type="text"
            maxlength="4"
            placeholder="请输入验证码"
            confirm-type="done"
            @confirm="handleLogin"
          />
          <view class="captcha-box" @click="loadCaptcha">
            <image
              v-if="captchaImage"
              class="captcha-image"
              :src="captchaImage"
              mode="aspectFit"
            />
            <text v-else class="captcha-placeholder">
              {{ captchaLoading ? "加载中" : "点击刷新" }}
            </text>
          </view>
        </view>
      </view>

      <button
        class="login-button"
        :loading="loggingIn"
        :disabled="loggingIn"
        @click="handleLogin"
      >
        登录
      </button>

      <!-- #ifdef MP-WEIXIN -->
      <view class="login-divider"><text>或</text></view>
      <button
        v-if="!needsWechatPhone"
        class="wechat-login-button"
        :loading="wechatLoggingIn"
        :disabled="wechatLoggingIn"
        @click="handleWechatLogin"
      >
        微信登录
      </button>
      <button
        v-else
        class="wechat-login-button"
        open-type="getPhoneNumber"
        :loading="wechatLoggingIn"
        :disabled="wechatLoggingIn"
        @getphonenumber="handleWechatPhone"
      >
        授权手机号并登录
      </button>
      <text class="wechat-login-tip">仅用于匹配管理员已创建的系统账号，不会自动注册或修改手机号</text>
      <!-- #endif -->
    </view>

    <view class="login-note">
      <text>账号、角色与权限由 PC 管理端统一维护</text>
      <text>首次登录如缺少教师或班级信息，请联系管理员完成档案绑定</text>
    </view>
  </view>
</template>

<style lang="scss" scoped>
.login-page {
  box-sizing: border-box;
  min-height: 100vh;
  padding: calc(env(safe-area-inset-top) + 72rpx) 36rpx 48rpx;
  color: #183153;
  background:
    radial-gradient(circle at 85% 8%, rgba(52, 179, 165, 0.2), transparent 28%),
    linear-gradient(155deg, #eef8ff 0%, #f6f8fc 50%, #effaf6 100%);
}

.brand-panel {
  display: flex;
  align-items: center;
  width: 100%;
  max-width: 720rpx;
  margin: 0 auto 56rpx;
}

.brand-mark {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 96rpx;
  height: 96rpx;
  margin-right: 24rpx;
  font-size: 44rpx;
  font-weight: 800;
  color: #fff;
  background: linear-gradient(145deg, #176de5, #20a99b);
  border-radius: 30rpx;
  box-shadow: 0 18rpx 38rpx rgba(23, 109, 229, 0.2);
}

.brand-copy,
.card-heading,
.login-note {
  display: flex;
  flex-direction: column;
}

.brand-name {
  font-size: 48rpx;
  font-weight: 800;
  letter-spacing: 2rpx;
}

.brand-slogan {
  margin-top: 10rpx;
  font-size: 24rpx;
  color: #7890aa;
}

.login-card {
  box-sizing: border-box;
  width: 100%;
  max-width: 720rpx;
  padding: 44rpx 36rpx 38rpx;
  margin: 0 auto;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(207, 222, 237, 0.85);
  border-radius: 32rpx;
  box-shadow: 0 26rpx 70rpx rgba(62, 91, 124, 0.12);
}

.login-divider {
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 28rpx 0 22rpx;
  font-size: 22rpx;
  color: #9aa9ba;
}

.login-divider::before,
.login-divider::after {
  width: 180rpx;
  height: 1px;
  margin: 0 18rpx;
  content: "";
  background: #e2e8f0;
}

.wechat-login-button {
  color: #fff;
  background: #07c160;
  border: 0;
  border-radius: 18rpx;
}

.wechat-login-button::after {
  border: 0;
}

.wechat-login-tip {
  display: block;
  margin-top: 18rpx;
  font-size: 21rpx;
  line-height: 1.55;
  color: #8a9caf;
  text-align: center;
}

.card-heading {
  margin-bottom: 38rpx;
}

.card-title {
  font-size: 40rpx;
  font-weight: 800;
}

.card-tip {
  margin-top: 10rpx;
  font-size: 24rpx;
  color: #8194aa;
}

.field {
  margin-bottom: 28rpx;
}

.field-label {
  display: block;
  margin-bottom: 12rpx;
  font-size: 25rpx;
  font-weight: 700;
  color: #415b76;
}

.field-input {
  box-sizing: border-box;
  width: 100%;
  height: 88rpx;
  padding: 0 26rpx;
  font-size: 28rpx;
  color: #183153;
  background: #f5f8fb;
  border: 1px solid #dfe8f1;
  border-radius: 20rpx;
}

.password-row,
.captcha-row {
  display: flex;
  align-items: center;
}

.password-row {
  position: relative;
}

.password-input {
  padding-right: 100rpx;
}

.password-toggle {
  position: absolute;
  right: 26rpx;
  font-size: 24rpx;
  color: #176de5;
}

.captcha-input {
  flex: 1;
  min-width: 0;
}

.captcha-box {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 224rpx;
  height: 88rpx;
  margin-left: 18rpx;
  overflow: hidden;
  background: #f5f8fb;
  border: 1px solid #dfe8f1;
  border-radius: 20rpx;
}

.captcha-image {
  width: 100%;
  height: 100%;
}

.captcha-placeholder {
  font-size: 24rpx;
  color: #7f93a8;
}

.login-button {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 92rpx;
  margin: 36rpx 0 0;
  font-size: 30rpx;
  font-weight: 700;
  line-height: 92rpx;
  border-radius: 22rpx;
}

.login-button {
  color: #fff;
  background: linear-gradient(100deg, #176de5, #178fb3);
  box-shadow: 0 15rpx 28rpx rgba(23, 109, 229, 0.22);
}

.login-button[disabled] {
  color: rgba(255, 255, 255, 0.78);
  opacity: 0.72;
}

.login-button::after {
  border: 0;
}

.login-note {
  align-items: center;
  margin: 34rpx auto 0;
  font-size: 22rpx;
  line-height: 1.8;
  color: #8a9caf;
  text-align: center;
}
</style>
