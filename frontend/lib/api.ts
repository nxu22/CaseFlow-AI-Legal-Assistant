/**
 * 前端的 API 封装层。
 *
 * 职责（面试可复述）：
 * 跟后端的 service 层一个思路 —— 把所有跟后端打交道的细节关在一个文件里。
 * 页面组件只调这里的函数（login / getCases / ...），不直接写 axios 调用。
 *
 * 两个核心机制：
 * 1. 请求拦截器：每次请求自动带上 JWT（从 localStorage 读），不用每个页面手动加。
 * 2. 响应拦截器：碰到 401（token 过期/无效）自动清掉 token + 跳回登录页。
 */
import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Token 管理（存 localStorage）──────────────────────────────
const TOKEN_KEY = "caseflow_token";

export const getToken = (): string | null => {
  if (typeof window === "undefined") return null; // SSR 阶段没有 window
  return localStorage.getItem(TOKEN_KEY);
};
export const setToken = (token: string): void =>
  localStorage.setItem(TOKEN_KEY, token);
export const removeToken = (): void => localStorage.removeItem(TOKEN_KEY);

// ── Axios 实例 + 拦截器 ────────────────────────────────────────
const api = axios.create({ baseURL: API_URL });

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      removeToken();
      if (typeof window !== "undefined") window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

// ── 类型（对应后端的 schema）──────────────────────────────────
export type CaseStatus =
  | "OPEN"
  | "IN_PROGRESS"
  | "CLOSED_WON"
  | "CLOSED_LOST"
  | "CLOSED_DISMISSED";

export type DocumentType =
  | "ticket"
  | "court_notice"
  | "evidence"
  | "defense_letter"
  | "other";

export interface Case {
  id: string;
  case_number: string;
  client_id: string;
  assigned_lawyer_id: string | null;
  status: CaseStatus;
  violation_type: string;
  violation_date: string | null;
  fine_amount: string | null;
  court_date: string | null;
  description: string | null;
  ai_summary: string | null;
  created_at: string;
}

export interface Document {
  id: string;
  case_id: string;
  filename: string;
  s3_key: string;
  file_size: number;
  mime_type: string;
  document_type: DocumentType;
  ai_summary: string | null;
  uploaded_by_id: string | null;
  created_at: string;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: "LAWYER" | "PARALEGAL";
  firm_id: string;
  firm_name: string;
}

// ── Auth ───────────────────────────────────────────────────────
// FastAPI 的 OAuth2PasswordRequestForm 要的是表单格式(username/password)，
// 不是 JSON。所以这里用 URLSearchParams + form-urlencoded。
export const login = async (email: string, password: string) => {
  const body = new URLSearchParams({ username: email, password });
  const res = await api.post<{ access_token: string; token_type: string }>(
    "/auth/login",
    body,
    { headers: { "Content-Type": "application/x-www-form-urlencoded" } }
  );
  return res.data;
};

export const getMe = async (): Promise<User> => {
  const res = await api.get<User>("/auth/me");
  return res.data;
};

// ── Cases ──────────────────────────────────────────────────────
export const getCases = async (): Promise<Case[]> => {
  const res = await api.get<Case[]>("/cases");
  return res.data;
};
export const getCase = async (id: string): Promise<Case> => {
  const res = await api.get<Case>(`/cases/${id}`);
  return res.data;
};

// ── Documents ──────────────────────────────────────────────────
export const getDocuments = async (caseId: string): Promise<Document[]> => {
  const res = await api.get<Document[]>(`/cases/${caseId}/documents`);
  return res.data;
};
export const uploadDocument = async (
  caseId: string,
  file: File,
  documentType: DocumentType = "other"
): Promise<Document> => {
  const form = new FormData();
  form.append("file", file);
  form.append("document_type", documentType);
  const res = await api.post<Document>(`/cases/${caseId}/documents`, form);
  return res.data;
};
export const summarizeDocument = async (
  caseId: string,
  documentId: string
): Promise<Document> => {
  const res = await api.post<Document>(
    `/cases/${caseId}/documents/${documentId}/summarize`
  );
  return res.data;
};
export const getDownloadUrl = async (
  caseId: string,
  documentId: string
): Promise<{ filename: string; download_url: string; expires_in: number }> => {
  const res = await api.get(`/cases/${caseId}/documents/${documentId}/download`);
  return res.data;
};

// ── Intake ─────────────────────────────────────────────────────
export interface HtaMatch {
  section: string;
  description: string;
  fine_category: string | null;
  fine_amount: number | null;
  notes: string | null;
}

export interface IntakeResult {
  thread_id: string;
  status: string;
  draft: string;
  hta_match: HtaMatch | null;
}

export interface IntakeDecisionResult {
  status: string;
  case_id: string;
  hta_section: string | null;
}

export const startIntake = async (caseId: string): Promise<IntakeResult> => {
  const res = await api.post<IntakeResult>(`/cases/${caseId}/intake`);
  return res.data;
};

export const decideIntake = async (
  caseId: string,
  threadId: string,
  decision: "approve" | "reject",
  editedDraft?: string
): Promise<IntakeDecisionResult> => {
  const res = await api.post<IntakeDecisionResult>(
    `/cases/${caseId}/intake/${threadId}/decision`,
    { decision, ...(editedDraft !== undefined && { edited_draft: editedDraft }) }
  );
  return res.data;
};

// ── Public Demo ────────────────────────────────────────────────────────────────
export interface DemoChatResponse {
  reply: string;
  tool_calls_made: number;
}

export const demoChat = async (message: string): Promise<DemoChatResponse> => {
  const res = await axios.post<DemoChatResponse>(
    `${API_URL}/demo/chat`,
    { message }
  );
  return res.data;
};

export default api;
