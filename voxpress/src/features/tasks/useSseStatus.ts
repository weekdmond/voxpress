import { useEffect, useState } from 'react';
import type { SseReadyState } from '@/lib/sse';

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';

export function useSseStatus(): SseReadyState {
  const [status, setStatus] = useState<SseReadyState>(USE_MOCK ? 'open' : 'connecting');
  useEffect(() => {
    if (USE_MOCK) {
      setStatus('open');
      return;
    }
    const base = import.meta.env.VITE_SSE_BASE || '';
    const es = new EventSource(`${base}/api/tasks/stream`);
    const onOpen = () => setStatus('open');
    const onError = () => setStatus(es.readyState === EventSource.CONNECTING ? 'connecting' : 'closed');
    es.addEventListener('open', onOpen);
    es.addEventListener('error', onError);
    return () => {
      es.removeEventListener('open', onOpen);
      es.removeEventListener('error', onError);
      es.close();
    };
  }, []);
  return status;
}
