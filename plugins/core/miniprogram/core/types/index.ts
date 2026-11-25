export interface AccountSession {
  tenantId?: string;
  userId: string;
  email: string;
  displayName: string;
  avatarUrl?: string;
  roleNames?: string[];
  roles: string[];
  permissions: string[];
  accessToken: string;
  refreshToken: string;
  expiresAt: number;
  role: string;
  department: string;
}
