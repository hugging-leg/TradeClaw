/**
 * AuthGuard — 路由守卫
 *
 * 1. 启动时查询 /api/auth/status 判断后端是否启用鉴权
 * 2. 鉴权关闭 → 直接渲染子路由
 * 3. 鉴权开启且无 token → 重定向到 /login
 * 4. 鉴权开启且有 token → 渲染子路由
 */

import { useEffect, useState } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth';
import { fetchAuthStatus } from '@/api';

export function AuthGuard() {
  const location = useLocation();
  const { authRequired, setAuthRequired, isAuthenticated } = useAuthStore();
  const [checking, setChecking] = useState(authRequired === null);

  useEffect(() => {
    if (authRequired !== null) return;

    fetchAuthStatus()
      .then((res) => setAuthRequired(res.auth_enabled))
      .catch(() => setAuthRequired(false)) // 后端不可达 → 不阻塞
      .finally(() => setChecking(false));
  }, [authRequired, setAuthRequired]);

  if (checking) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      </div>
    );
  }

  if (!isAuthenticated()) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <Outlet />;
}
