import type { Task } from '@/types/api';

export type TaskStreamEvent =
  | { type: 'update'; task: Task }
  | { type: 'create'; task: Task }
  | { type: 'remove'; task: { id: string } };

const SSE_BASE = import.meta.env.VITE_SSE_BASE || '';
const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';

export function subscribeTasks(onEvent: (e: TaskStreamEvent) => void): () => void {
  if (USE_MOCK) return subscribeTasksMock(onEvent);
  const es = new EventSource(`${SSE_BASE}/api/tasks/stream`);
  const mk = (type: 'update' | 'create' | 'remove') => (ev: MessageEvent) => {
    try {
      onEvent({ type, task: JSON.parse(ev.data) } as TaskStreamEvent);
    } catch {
      /* ignore */
    }
  };
  es.addEventListener('task.update', mk('update') as EventListener);
  es.addEventListener('task.create', mk('create') as EventListener);
  es.addEventListener('task.remove', mk('remove') as EventListener);
  return () => es.close();
}

// Mock SSE driver: advances tasks progress every 800ms.
import { mockStore } from '@/mocks/store';

function subscribeTasksMock(onEvent: (e: TaskStreamEvent) => void): () => void {
  const unsub = mockStore.subscribe(onEvent);
  // Send initial snapshot
  mockStore.getLiveTasks().forEach((task) => onEvent({ type: 'update', task }));
  return unsub;
}

export type SseReadyState = 'connecting' | 'open' | 'closed';
