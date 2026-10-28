import { basinDepth, MOUNDS, T } from '@abuk/core';
import { record, setState, useApp } from '../store';

export function toggleTask(id: number) {
  let done = false;
  setState(st => ({ tasks: st.tasks.map(t => (t.id === id ? ((done = !t.done), { ...t, done }) : t)) }));
  record('task', { id, done });
}

export const useL = () => { const s = useApp(); return T[s.lang === 'ar' ? 'ar' : 'en']; };
export const useGreet = () => {
  const s = useApp(), L = useL();
  const first = s.session?.user.name.split(' ')[0];
  return first ? `${L.greet}, ${first}` : L.greet;
};

// Mound line colours on the map diagrams: grey when the crest is under water.
export const moundLines = (ys: number[], depth = basinDepth(0)) =>
  ys.map((y, i) => ({ y, c: MOUNDS[i][1] < depth ? 'var(--color-neutral-600)' : 'var(--color-accent)' }));

export const basinOpacity = (depth = basinDepth(0)) => (depth / 1.2 * 0.6).toFixed(2);
