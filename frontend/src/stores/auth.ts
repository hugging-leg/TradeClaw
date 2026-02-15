/**
 * Auth Store (Zustand)
 *
 * 管理 JWT token 和鉴权状态。
 * - token 存储在 localStorage，刷新后自动恢复
 * - authRequired 由后端 /api/auth/status 决定
 */

import { create } from 'zustand';

const TOKEN_KEY = 'agent_trader_token';

interface AuthState {
  token: string | null;
  /** 后端是否启用了鉴权（null = 尚未查询） */
  authRequired: boolean | null;

  setToken: (token: string) => void;
  clearToken: () => void;
  setAuthRequired: (required: boolean) => void;

  /** 是否已认证（鉴权关闭时视为已认证） */
  isAuthenticated: () => boolean;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: localStorage.getItem(TOKEN_KEY),
  authRequired: null,

  setToken: (token: string) => {
    localStorage.setItem(TOKEN_KEY, token);
    set({ token });
  },

  clearToken: () => {
    localStorage.removeItem(TOKEN_KEY);
    set({ token: null });
  },

  setAuthRequired: (required: boolean) => {
    set({ authRequired: required });
  },

  isAuthenticated: () => {
    const { authRequired, token } = get();
    // 鉴权关闭 → 视为已认证
    if (authRequired === false) return true;
    // 鉴权开启 → 需要 token
    return !!token;
  },
}));
