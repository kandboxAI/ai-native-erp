<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { ref, reactive, watch, onMounted, onBeforeUnmount, computed } from "vue";
import QRCode from "qrcode";
import type { FormInstance } from "element-plus";
import { message } from "@/utils/message";
import { loginRules } from "./utils/rule";
import { $t, transformI18n } from "@/plugins/i18n";
import { useLayout } from "@/layout/hooks/useLayout";
import {
  createEmployeeQrLoginSession,
  getEmployeeQrLoginStatus,
  getLoginCaptcha,
  type EmployeeQrLoginSession
} from "@/api/user";
import { useUserStoreHook } from "@/store/modules/user";
import { initRouter } from "@/router/utils";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import { useDataThemeChange } from "@/layout/hooks/useDataThemeChange";
import {
  defaultLoginContent,
  loadLoginContent,
  loginAssetUrl
} from "./utils/content";
import Tasks from "~icons/ri/file-list-3-line";
import Brain from "~icons/ri/brain-line";
import Optimize from "~icons/ri/loop-right-line";
import Arrow from "~icons/ri/arrow-right-line";
import Lock from "~icons/ri/lock-2-line";
import User from "~icons/ri/user-3-line";
import Info from "~icons/ri/information-fill";
import Keyhole from "~icons/ri/shield-check-line";
import Refresh from "~icons/ri/refresh-line";
import Wechat from "~icons/ri/wechat-fill";

defineOptions({ name: "Login" });

const captchaId = ref("");
const captchaImage = ref("");
const captchaLoading = ref(false);
const rememberDays = 7;
const router = useRouter();
const loading = ref(false);
const checked = ref(false);
const disabled = ref(false);
const loginMode = ref<"password" | "wechat">("password");
const qrLoading = ref(false);
const qrExchanging = ref(false);
const qrSession = ref<EmployeeQrLoginSession | null>(null);
const qrImageUrl = ref("");
const qrStatus = ref("pending");
const qrExpiresIn = ref(0);
let qrPollTimer: ReturnType<typeof setInterval> | null = null;
const qrStatusText = computed(() => {
  if (qrStatus.value === "scanned") return "已扫码，请在教育小程序确认";
  if (qrStatus.value === "confirmed" || qrExchanging.value) return "已确认，正在登录…";
  if (qrStatus.value === "cancelled") return "已取消本次登录";
  if (qrStatus.value === "expired") return "二维码已过期";
  return "请使用微信扫描二维码";
});
const ruleFormRef = ref<FormInstance>();
const content = ref(defaultLoginContent);
const logoFailed = ref(false);
const fallbackLogoFailed = ref(false);
const displayedLogo = computed(() =>
  (logoFailed.value ? __PRODUCT_BRANDING__.fallback_logo : content.value.logo) ||
  __PRODUCT_BRANDING__.fallback_logo
);
function onLogoError() {
  if (displayedLogo.value === __PRODUCT_BRANDING__.fallback_logo) {
    fallbackLogoFailed.value = true;
  } else {
    logoFailed.value = true;
  }
}
const campusFailed = ref(false);
const stepIcons = [Brain, Tasks, Optimize];
const configuredStepIcons = __LOGIN_STEP_ICONS__;
const { t } = useI18n();
const { initStorage } = useLayout();
initStorage();
const { themeMode, dataThemeChange } = useDataThemeChange();
dataThemeChange(themeMode.value);

const ruleForm = reactive({
  username: "",
  password: "",
  verifyCode: ""
});

const refreshCaptcha = async () => {
  if (captchaLoading.value) return;
  captchaLoading.value = true;
  try {
    const res = await getLoginCaptcha();
    captchaId.value = res.data?.captcha_id ?? "";
    captchaImage.value = res.data?.image ?? "";
    ruleForm.verifyCode = "";
  } catch {
    captchaId.value = "";
    captchaImage.value = "";
    message("验证码加载失败，请点击换一张重试", { type: "error" });
  } finally {
    captchaLoading.value = false;
  }
};

onMounted(() => {
  void refreshCaptcha();
  void loadLoginContent().then(value => {
    content.value = value;
  });
});

const onLogin = async (formEl: FormInstance | undefined) => {
  if (!formEl || loading.value || disabled.value) return;
  await formEl.validate(valid => {
    if (valid) {
      loading.value = true;
      useUserStoreHook()
        .loginByUsername({
          username: ruleForm.username,
          password: ruleForm.password,
          captchaId: captchaId.value,
          captchaCode: ruleForm.verifyCode,
          rememberMe: checked.value,
          rememberDays
        })
        .then(async () => {
          // 获取后端路由
          await initRouter();
          disabled.value = true;
          router.push("/workbench").then(() => {
            message(t("login.pureLoginSuccess"), { type: "success" });
          });
        })
        .catch(_err => {
          message(t("login.pureLoginFail"), { type: "error" });
          void refreshCaptcha();
        })
        .finally(() => {
          disabled.value = false;
          loading.value = false;
        });
    }
  });
};

function stopQrPolling() {
  if (qrPollTimer) clearInterval(qrPollTimer);
  qrPollTimer = null;
}

async function finishQrLogin() {
  if (!qrSession.value || qrExchanging.value) return;
  qrExchanging.value = true;
  stopQrPolling();
  try {
    await useUserStoreHook().loginByEmployeeQr(
      qrSession.value.session_id,
      qrSession.value.browser_secret
    );
    await initRouter();
    await router.push("/workbench");
    message("微信扫码登录成功", { type: "success" });
  } catch (error: any) {
    qrStatus.value = "expired";
    message(error?.response?.data?.message ?? error?.message ?? "扫码登录失败", { type: "error" });
  } finally {
    qrExchanging.value = false;
  }
}

async function pollQrStatus() {
  const current = qrSession.value;
  if (!current || qrExchanging.value) return;
  try {
    const res = await getEmployeeQrLoginStatus(current.session_id, current.browser_secret);
    qrStatus.value = res.data.status;
    qrExpiresIn.value = res.data.expires_in;
    if (res.data.status === "confirmed") await finishQrLogin();
    if (["expired", "cancelled", "consumed"].includes(res.data.status)) stopQrPolling();
  } catch (error: any) {
    stopQrPolling();
    qrStatus.value = "expired";
    message(error?.response?.data?.message ?? "查询扫码状态失败", { type: "error" });
  }
}

async function startQrLogin() {
  stopQrPolling();
  qrLoading.value = true;
  qrStatus.value = "pending";
  qrImageUrl.value = "";
  try {
    const created = await createEmployeeQrLoginSession();
    qrSession.value = created.data;
    qrExpiresIn.value = created.data.expires_in;
    qrImageUrl.value = await QRCode.toDataURL(created.data.qr_url, { width: 220, margin: 1 });
    qrPollTimer = setInterval(pollQrStatus, 1500);
  } catch (error: any) {
    qrStatus.value = "expired";
    message(error?.response?.data?.message ?? error?.message ?? "生成登录二维码失败", { type: "error" });
  } finally {
    qrLoading.value = false;
  }
}

function switchLoginMode(mode: "password" | "wechat") {
  loginMode.value = mode;
  if (mode === "wechat") void startQrLogin();
  else stopQrPolling();
}

watch(checked, bool => {
  useUserStoreHook().SET_ISREMEMBERED(bool);
});

onBeforeUnmount(stopQrPolling);
</script>

<template>
  <main class="login-viewport">
    <div class="login-page">
      <aside class="login-artwork" :aria-label="content.schoolName">
        <div class="login-introduction">
          <div class="school-brand">
            <img
              v-if="!fallbackLogoFailed"
              class="school-logo"
              :src="loginAssetUrl(displayedLogo)"
              :alt="`${content.schoolName}标识`"
              @error="onLogoError"
            />
            <div>
              <p class="school-name">{{ content.schoolName }}</p>
              <p class="school-english">{{ content.englishName }}</p>
            </div>
          </div>
          <div class="login-promise">
            <p>&nbsp; &nbsp; {{ content.tagline }}</p>
          </div>
          <ol class="login-steps">
            <li v-for="(step, index) in content.steps" :key="index">
              <span class="step-icon"
                ><IconifyIconOffline
                  :icon="step.icon ? configuredStepIcons[step.icon] : stepIcons[Math.min(index, stepIcons.length - 1)]"
              /></span>
              <h3>{{ step.title }}</h3>
              <p>
                <span
                  v-for="(line, lineIndex) in step.lines"
                  :key="lineIndex"
                  >{{ line }}</span
                >
              </p>
              <IconifyIconOffline
                v-if="index < content.steps.length - 1"
                :icon="Arrow"
                class="step-arrow"
                aria-hidden="true"
              />
            </li>
          </ol>
        </div>
        <div class="login-campus">
          <img
            v-if="content.campusImage && !campusFailed"
            :src="loginAssetUrl(content.campusImage)"
            :alt="content.campusAlt"
            fetchpriority="high"
            @error="campusFailed = true"
          />
        </div>
      </aside>
      <section class="login-panel" aria-labelledby="login-title">
        <div class="login-form">
          <header class="login-heading">
            <h1 id="login-title">{{ content.welcomeTitle }}</h1>
            <p>{{ content.loginSubtitle }}</p>
          </header>
          <el-form
            v-if="loginMode === 'password'"
            ref="ruleFormRef"
            :model="ruleForm"
            :rules="loginRules"
            label-position="top"
            hide-required-asterisk
            size="large"
            @submit.prevent="onLogin(ruleFormRef)"
          >
            <el-form-item
              label="账号"
              prop="username"
              :rules="[
                {
                  required: true,
                  message: transformI18n($t('login.pureUsernameReg')),
                  trigger: 'blur'
                }
              ]"
            >
              <el-input
                v-model="ruleForm.username"
                name="username"
                autocomplete="username"
                clearable
                placeholder="请输入账号"
                :prefix-icon="useRenderIcon(User)"
              />
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input
                v-model="ruleForm.password"
                name="password"
                autocomplete="current-password"
                type="password"
                show-password
                placeholder="请输入密码"
                :prefix-icon="useRenderIcon(Lock)"
              />
            </el-form-item>
            <el-form-item
              label="验证码"
              prop="verifyCode"
              class="captcha-field"
            >
              <div class="captcha-row">
                <el-input
                  v-model="ruleForm.verifyCode"
                  name="captcha"
                  autocomplete="off"
                  clearable
                  placeholder="请输入验证码"
                  :prefix-icon="useRenderIcon(Keyhole)"
                />
                <button
                  class="captcha-image"
                  type="button"
                  aria-label="刷新验证码"
                  :disabled="captchaLoading"
                  @click="refreshCaptcha"
                >
                  <img
                    v-if="captchaImage"
                    :src="captchaImage"
                    alt="图形验证码"
                  />
                  <span v-else>{{
                    captchaLoading ? "加载中…" : "点击重试"
                  }}</span>
                </button>
                <el-button
                  data-action="neutral"
                  class="captcha-refresh"
                  link
                  type="primary"
                  :disabled="captchaLoading"
                  :aria-busy="captchaLoading"
                  @click="refreshCaptcha"
                >
                  <IconifyIconOffline :icon="Refresh" />
                  <span>换一张</span>
                </el-button>
              </div>
            </el-form-item>
            <div class="login-remember">
              <el-checkbox v-model="checked">在此设备保持登录</el-checkbox>
              <span class="login-remember-days">7 天</span>
            </div>
            <el-button
              data-action="primary"
              class="login-submit"
              type="primary"
              native-type="submit"
              :loading="loading"
              :disabled="disabled"
              >登录</el-button
            >
          </el-form>
          <div v-else class="qr-login-panel">
            <div class="qr-image-box">
              <img v-if="qrImageUrl" :src="qrImageUrl" class="qr-login-image" alt="微信扫码登录" />
              <div v-else class="qr-placeholder">{{ qrLoading ? "正在生成二维码…" : "二维码加载失败" }}</div>
              <button v-if="['expired', 'cancelled'].includes(qrStatus) && !qrLoading" class="qr-refresh-mask" type="button" @click="startQrLogin">点击刷新</button>
            </div>
            <div class="qr-status" :class="qrStatus">{{ qrStatusText }}</div>
            <div v-if="qrExpiresIn > 0 && !['confirmed', 'consumed'].includes(qrStatus)" class="qr-countdown">{{ qrExpiresIn }} 秒后失效</div>
            <p>仅匹配管理员已创建的账号，不会自动注册或修改手机号</p>
          </div>
          <div class="login-mode-switch">
            <button
              v-if="loginMode === 'password'"
              type="button"
              title="微信扫码登录"
              aria-label="微信扫码登录"
              @click="switchLoginMode('wechat')"
            >
              <IconifyIconOffline :icon="Wechat" />
            </button>
            <button
              v-else
              type="button"
              title="返回账号登录"
              aria-label="返回账号登录"
              @click="switchLoginMode('password')"
            >
              <IconifyIconOffline :icon="User" />
            </button>
            <span>{{ loginMode === "password" ? "微信扫码" : "账号登录" }}</span>
          </div>
          <div class="login-help" role="note">
            <IconifyIconOffline :icon="Info" />
            <p>
              <span v-for="(line, index) in content.helpLines" :key="index">{{
                line
              }}</span>
            </p>
          </div>
          <footer class="login-footer">
            <div class="login-ai-note">
              <span class="ai-mark" aria-hidden="true">AI</span>
              <p>{{ content.aiNote }}</p>
            </div>
          </footer>
        </div>
      </section>
    </div>
  </main>
</template>

<style scoped>
@import url("@/style/login.css");
</style>
