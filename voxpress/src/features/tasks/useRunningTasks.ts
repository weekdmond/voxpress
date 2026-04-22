import { useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { Page, Task } from '@/types/api';
import { subscribeTasks } from '@/lib/sse';

export function useRunningTasks() {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ['tasks', 'active'],
    queryFn: async () => {
      const res = await api.get<Page<Task>>('/api/tasks?status=active&limit=50');
      return res.items;
    },
    staleTime: 30_000,
  });
  useEffect(() => {
    return subscribeTasks((e) => {
      qc.setQueryData<Task[]>(['tasks', 'active'], (old = []) => {
        if (e.type === 'remove') return old.filter((t) => t.id !== e.task.id);
        if (e.type === 'create') {
          if (old.some((t) => t.id === e.task.id)) return old;
          return [e.task, ...old];
        }
        // update
        const t = e.task;
        if (t.status === 'done' || t.status === 'canceled' || t.status === 'failed') {
          return old.filter((x) => x.id !== t.id);
        }
        const exists = old.some((x) => x.id === t.id);
        return exists ? old.map((x) => (x.id === t.id ? t : x)) : [t, ...old];
      });
      // Invalidate recent articles when a task completes
      if (e.type === 'update' && 'status' in e.task && e.task.status === 'done') {
        qc.invalidateQueries({ queryKey: ['articles'] });
      }
    });
  }, [qc]);
  return query;
}
