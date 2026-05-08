const BASE = import.meta.env.VITE_API_BASE || '';

export class ApiError extends Error {
  code: string;
  status: number;
  detail: unknown;
  constructor(opts: { code: string; message: string; status: number; detail?: unknown }) {
    super(opts.message);
    this.code = opts.code;
    this.status = opts.status;
    this.detail = opts.detail;
  }
}

function validationMessage(detail: unknown): string | null {
  if (!Array.isArray(detail)) return null;
  const first = detail[0];
  if (!first || typeof first !== 'object') return null;
  const ctx = 'ctx' in first && first.ctx && typeof first.ctx === 'object' ? first.ctx : null;
  const limit = ctx && 'max_length' in ctx ? Number(ctx.max_length) : null;
  const loc = Array.isArray(first.loc) ? first.loc.join('.') : '';
  if (loc.includes('article_ids') && limit) {
    return `一次最多可分享 ${limit} 篇文章，请减少选择数量后重试`;
  }
  return typeof first.msg === 'string' ? first.msg : null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers || {});
  const isFormData = typeof FormData !== 'undefined' && init?.body instanceof FormData;
  if (!isFormData && init?.body != null && !headers.has('content-type')) {
    headers.set('content-type', 'application/json');
  }
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers,
  });
  if (!res.ok) {
    let code = 'unknown_error';
    let message = `${res.status} ${res.statusText}`;
    let detail: unknown;
    try {
      const body = await res.json();
      if (body?.error) {
        code = body.error.code ?? code;
        message = body.error.message ?? message;
        detail = body.error.detail;
      } else if (body?.detail) {
        detail = body.detail;
        message = validationMessage(detail) ?? message;
      }
    } catch {
      /* ignore */
    }
    throw new ApiError({ code, message, status: res.status, detail });
  }
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) return (await res.json()) as T;
  return (await res.text()) as unknown as T;
}

export function apiUrl(path: string): string {
  if (!path) return BASE;
  if (/^https?:\/\//.test(path)) return path;
  return `${BASE}${path}`;
}

export const api = {
  get: <T>(path: string, init?: RequestInit) => request<T>(path, init),
  post: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>(path, {
      ...init,
      method: 'POST',
      body: body == null ? undefined : JSON.stringify(body),
    }),
  postForm: <T>(path: string, form: FormData, init?: RequestInit) =>
    request<T>(path, { ...init, method: 'POST', body: form }),
  patch: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>(path, {
      ...init,
      method: 'PATCH',
      body: body == null ? undefined : JSON.stringify(body),
    }),
  del: <T>(path: string, init?: RequestInit) => request<T>(path, { ...init, method: 'DELETE' }),
};
