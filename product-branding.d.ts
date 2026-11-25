export interface ProductBranding {
  title: string;
  subtitle: string;
  english_name: string;
  mark: string;
  assistant_name: string;
  description: string;
  logo: string;
  header_logo: string;
  fallback_logo: string;
  favicon: string;
  miniapp_logo: string;
  miniapp_assistant_avatar: string;
  login: {
    school_name: string;
    english_name: string;
    welcome_title: string;
    subtitle: string;
    tagline: string;
    background: string;
    background_alt: string;
    ai_note: string;
    help_lines: string[];
    steps: { title: string; lines: string[]; icon?: string }[];
  };
}
