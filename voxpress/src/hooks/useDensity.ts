import { useEffect } from 'react';
import { usePersistedState } from './usePersistedState';

export type Density = 'comfortable' | 'compact';

export function useDensity() {
  const [density, setDensity] = usePersistedState<Density>('voxpress_density', 'comfortable');
  useEffect(() => {
    document.body.classList.toggle('density-compact', density === 'compact');
  }, [density]);
  return { density, setDensity };
}
