"use client"; // 用了 useState/useEffect/表单事件 → 必须是客户端组件

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Scale, AlertCircle, Loader2 } from "lucide-react";
import { login, setToken, getToken } from "@/lib/api";

const schema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(1, "Password is required"),
});
type FormData = z.infer<typeof schema>;

export default function LoginPage() {
  const router = useRouter();

  useEffect(() => {
    if (getToken()) router.replace("/cases");
  }, [router]);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      email: "lawyer@caseflow.mb",
      password: "Demo1234!",
    },
  });

  const onSubmit = async (data: FormData) => {
    try {
      const res = await login(data.email, data.password);
      setToken(res.access_token);
      router.push("/cases");
    } catch {
      setError("root", { message: "Invalid email or password" });
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-6">

      {/* Title — centered at top */}
      <div className="flex items-center gap-3 mb-10">
        <div className="p-2 bg-blue-600 rounded-lg">
          <Scale className="h-5 w-5 text-white" />
        </div>
        <h1 className="text-3xl font-semibold text-slate-900 whitespace-nowrap">
          CaseFlow <span className="text-blue-600">MB</span> — AI-Powered Legal Case Assistant
        </h1>
      </div>

      {/* Two equal columns */}
      <div className="w-full max-w-5xl flex gap-12 items-start">

        {/* Left — value proposition */}
        <div className="flex-1 hidden md:flex flex-col gap-6">
          <h2 className="text-lg font-bold text-slate-800">Why Choose Us</h2>

          <p className="text-sm text-slate-500 leading-relaxed">
            This is not just a case management website — it&apos;s an AI agent system. The most time-consuming work in a law firm (case intake, legal section lookup, document preparation) is handled automatically by AI. Lawyers focus on judgment, not repetitive tasks.
          </p>

          <p className="text-sm text-slate-500 leading-relaxed">
            Upload a ticket screenshot and the AI automatically extracts case details, matches the real Manitoba HTA section, finds similar past cases, and drafts a complete intake memo. 30 minutes of work done in 30 seconds. The lawyer only needs to click Approve.
          </p>
        </div>

        {/* Right — login card */}
        <div className="flex-1 flex flex-col items-center">
          <div className="w-full max-w-sm">
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8">
              <h2 className="text-2xl font-semibold text-slate-900 mb-1">Sign in</h2>
              <p className="text-sm text-slate-500 mb-4">
                Access your case management portal
              </p>
              <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 mb-6">
                <p className="text-xs font-semibold text-blue-700 mb-1">Demo account</p>
                <p className="text-xs text-blue-600">Email: lawyer@caseflow.mb</p>
                <p className="text-xs text-blue-600">Password: Demo1234!</p>
              </div>

              <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1.5">
                    Email
                  </label>
                  <input
                    {...register("email")}
                    type="email"
                    autoComplete="email"
                    placeholder="lawyer@caseflow.mb"
                    className="w-full px-3 py-2.5 rounded-lg border border-slate-300 text-slate-900 text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
                  />
                  {errors.email && (
                    <p className="mt-1 text-xs text-red-500">{errors.email.message}</p>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1.5">
                    Password
                  </label>
                  <input
                    {...register("password")}
                    type="password"
                    autoComplete="current-password"
                    placeholder="••••••••"
                    className="w-full px-3 py-2.5 rounded-lg border border-slate-300 text-slate-900 text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
                  />
                  {errors.password && (
                    <p className="mt-1 text-xs text-red-500">{errors.password.message}</p>
                  )}
                </div>

                {errors.root && (
                  <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2.5">
                    <AlertCircle className="h-4 w-4 flex-shrink-0" />
                    {errors.root.message}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm font-medium rounded-lg transition flex items-center justify-center gap-2"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Signing in…
                    </>
                  ) : (
                    "Sign in"
                  )}
                </button>
              </form>
            </div>

            <p className="text-center text-xs text-slate-400 mt-6">
              CaseFlow MB · Secure Case Management
            </p>
          </div>
        </div>

      </div>
    </div>
  );
}
