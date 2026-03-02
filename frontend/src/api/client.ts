/**
 * HTTP Client
 *
 * 封装 fetch，统一错误处理、base URL 管理和 JWT 鉴权。
 * - 自动注入 Authorization header（如果 token 存在）
 * - 401 响应自动清除 token 并跳转到登录页
 */

import { useAuthStore } from '@/stores/auth';

// 开发模式通过 Vite proxy (/api → http://localhost:8000/api)
// 生产模式可通过 VITE_API_BASE_URL 覆盖
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function getAuthHeaders(): Record<string, string> {
  const token = useAuthStore.getState().token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
      ...options?.headers,
    },
    ...options,
  });

  if (res.status === 401) {
    // Token 过期或无效 → 清除并让路由守卫处理跳转
    useAuthStore.getState().clearToken();
    throw new ApiError(401, 'Unauthorized');
  }

  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new ApiError(res.status, body || `HTTP ${res.status}`);
  }

  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),

  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),

  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),

  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined }),

  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
};

export { ApiError };
