<script setup lang="ts">
import { computed, ref } from "vue";
import { brandingAssetUrl } from "@/utils/branding";
import NavbarActions from "./NavbarActions.vue";

const branding = __PRODUCT_BRANDING__;
const headerLogoFailed = ref(false);
const logoFailed = ref(false);
const fallbackLogoFailed = ref(false);
const showHeaderLogo = computed(
  () => Boolean(branding.header_logo) && !headerLogoFailed.value
);
const logo = computed(() =>
  brandingAssetUrl(
    logoFailed.value
      ? branding.fallback_logo
      : branding.logo || branding.fallback_logo
  )
);

function onLogoError() {
  if (
    logoFailed.value ||
    !branding.logo ||
    branding.logo === branding.fallback_logo
  ) {
    fallbackLogoFailed.value = true;
  } else {
    logoFailed.value = true;
  }
}
</script>

<template>
  <header class="portal-header">
    <div class="portal-brand" :aria-label="branding.login.school_name">
      <img
        v-if="showHeaderLogo"
        class="portal-school-image"
        :src="brandingAssetUrl(branding.header_logo)"
        :alt="branding.login.school_name"
        @error="headerLogoFailed = true"
      />
      <div v-else class="portal-school">
        <img
          v-if="logo && !fallbackLogoFailed"
          class="portal-logo"
          :src="logo"
          alt=""
          @error="onLogoError"
        />
        <div class="portal-school-name">
          <p>{{ branding.login.school_name }}</p>
          <small>{{ branding.login.english_name }}</small>
        </div>
      </div>
      <p class="portal-product">{{ branding.login.subtitle }}</p>
    </div>
    <div class="portal-actions">
      <NavbarActions />
    </div>
  </header>
</template>

<style scoped>
.portal-header {
  display: flex;
  gap: 24px;
  align-items: center;
  justify-content: space-between;
  height: var(--portal-header-height);
  padding-inline: clamp(16px, 3.6vw, 16px) 16px;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.portal-brand,
.portal-school,
.portal-actions {
  display: flex;
  gap: 16px;
  align-items: center;
  min-width: 0;
}

.portal-school-image {
  display: block;
  flex-shrink: 1;
  width: clamp(260px, 34vw, 440px);
  min-width: 0;
  max-height: 64px;
  object-fit: contain;
}

.portal-logo {
  flex: none;
  width: 56px;
  height: 56px;
  object-fit: contain;
}

.portal-school-name {
  min-width: 0;
}

.portal-school-name p {
  margin: 0;
  font-family: STKaiti, KaiTi, serif;
  font-size: clamp(18px, 2vw, 28px);
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.portal-school-name small {
  display: block;
  margin-top: 4px;
  font-size: 10px;
  color: var(--el-text-color-secondary);
}

.portal-product {
  flex: none;
  padding-left: 18px;
  margin: 0;
  font-size: clamp(16px, 1.6vw, 22px);
  font-weight: 700;
  color: #2b1c70;
  border-left: 1px solid #a3a5be;
}

.portal-actions {
  flex: none;
  gap: 12px;
}

@media (width <= 1000px) {
  .portal-product {
    display: none;
  }
}

@media (width <= 760px) {
  .portal-header {
    flex-wrap: wrap;
    gap: 0;
    padding: 8px 12px 0;
  }

  .portal-brand {
    width: 100%;
    height: 56px;
  }

  .portal-school-image {
    width: min(360px, 100%);
    max-height: 52px;
    object-position: left center;
  }

  .portal-logo {
    width: 40px;
    height: 40px;
  }

  .portal-actions {
    justify-content: flex-end;
    width: 100%;
  }

  .portal-actions :deep(.navbar-actions) {
    min-width: 0;
  }
}

:global(.dark) .portal-product {
  color: var(--el-text-color-primary);
}
</style>
