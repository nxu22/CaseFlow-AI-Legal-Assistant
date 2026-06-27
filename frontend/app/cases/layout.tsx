"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Scale, LogOut, User as UserIcon } from "lucide-react";
import { getToken, removeToken, getMe, type User } from "@/lib/api";

/**
 * /cases 和 /cases/[id] 共用的布局。
 * 职责：①登录守卫（没 token 就踢回登录页）②顶部导航栏（品牌+用户+登出）。
 * 放在 layout 里 → 两个页面都自动套用，不用各写一遍（DRY）。
 */
export default function CasesLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    // 拿当前用户信息，顺便验证 token 有效
    getMe()
      .then((u) => {
        setUser(u);
        setChecking(false);
      })
      .catch(() => {
        removeToken();
        router.replace("/login");
      });
  }, [router]);

  // 认证确认前先不渲染，避免闪一下未登录内容
  if (checking) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-spin h-6 w-6 border-2 border-blue-600 border-t-transparent rounded-full" />
      </div>
    );
  }

  const handleLogout = () => {
    removeToken();
    router.push("/login");
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <nav className="bg-white border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <Link href="/cases" className="flex items-center gap-2">
            <div className="p-1.5 bg-blue-600 rounded-md">
              <Scale className="h-4 w-4 text-white" />
            </div>
            <span className="font-semibold text-slate-900 text-sm">
              CaseFlow <span className="text-blue-600">MB</span>
            </span>
          </Link>

          <div className="flex items-center gap-4">
            {user && (
              <div className="flex items-center gap-2 text-sm">
                <UserIcon className="h-4 w-4 text-slate-400" />
                <span className="text-slate-700">{user.full_name}</span>
                <span className="text-xs text-slate-400 capitalize">
                  {user.role.toLowerCase()}
                </span>
                <span className="text-xs bg-slate-100 text-slate-500 border border-slate-200 rounded-full px-2 py-0.5">
                  {user.firm_name}
                </span>
              </div>
            )}
            <button
              onClick={handleLogout}
              className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-900 transition"
            >
              <LogOut className="h-4 w-4" />
              Sign out
            </button>
          </div>
        </div>
      </nav>

      <main className="max-w-6xl mx-auto px-4 py-8">{children}</main>
    </div>
  );
}
