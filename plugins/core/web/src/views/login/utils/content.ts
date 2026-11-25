import { brandingAssetUrl } from "@/utils/branding";

/** 登录与站内共用解析后的品牌，不再用全局静态文件覆盖所选客户。 */
export interface LoginContent {
  schoolName: string;
  englishName: string;
  logo: string;
  tagline: string;
  steps: typeof __PRODUCT_BRANDING__.login.steps;
  campusImage: string;
  campusAlt: string;
  welcomeTitle: string;
  loginSubtitle: string;
  helpLines: string[];
  aiNote: string;
}

export const defaultLoginContent: LoginContent = {
  schoolName: __PRODUCT_BRANDING__.login.school_name,
  englishName: __PRODUCT_BRANDING__.login.english_name,
  logo: __PRODUCT_BRANDING__.logo,
  tagline: __PRODUCT_BRANDING__.login.tagline,
  steps: __PRODUCT_BRANDING__.login.steps,
  campusImage: __PRODUCT_BRANDING__.login.background,
  campusAlt: __PRODUCT_BRANDING__.login.background_alt,
  welcomeTitle: __PRODUCT_BRANDING__.login.welcome_title,
  loginSubtitle: __PRODUCT_BRANDING__.login.subtitle,
  helpLines: __PRODUCT_BRANDING__.login.help_lines,
  aiNote: __PRODUCT_BRANDING__.login.ai_note
};

export const loginAssetUrl = brandingAssetUrl;

export async function loadLoginContent(): Promise<LoginContent> {
  return defaultLoginContent;
}
