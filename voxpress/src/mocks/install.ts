import { ApiError } from '@/lib/api';
import { handleRequest, type Method } from './handlers';

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';
const BASE = import.meta.env.VITE_API_BASE || '';

export function installMockFetch() {
  if (!USE_MOCK) return;
  const original = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
    const rel = url.startsWith(BASE) ? url.slice(BASE.length) : url;
    if (!rel.startsWith('/api/')) {
      return original(input, init);
    }
    const method = ((init?.method ?? 'GET').toUpperCase()) as Method;
    let body: unknown;
    if (init?.body) {
      try {
        body = typeof init.body === 'string' ? JSON.parse(init.body) : init.body;
      } catch {
        body = init.body;
      }
    }
    try {
      const data = await handleRequest(method, rel, body);
      return new Response(JSON.stringify(data), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    } catch (err) {
      const e = err as { code?: string; status?: number; message?: string };
      const payload = {
        error: {
          code: e.code ?? 'unknown_error',
          message: e.message ?? 'Mock error',
        },
      };
      return new Response(JSON.stringify(payload), {
        status: e.status ?? 500,
        headers: { 'content-type': 'application/json' },
      });
    }
  };
  // re-export so tree-shake doesn't drop ApiError import if unused
  void ApiError;
}
