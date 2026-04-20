import { Chip } from '@/components/primitives';
import { formatDuration } from '@/lib/format';
import type { TranscriptSegment } from '@/types/api';
import s from './Reader.module.css';

export function Drawer({ segments }: { segments: TranscriptSegment[] }) {
  return (
    <aside className={s.drawer}>
      <div className={s.drawerHead}>
        <Chip variant="accent">原始逐字稿</Chip>
        <span className={s.drawerMeta}>whisper large-v3</span>
      </div>
      <div className={s.drawerBody}>
        {segments.map((seg, i) => (
          <div key={`${seg.ts_sec}-${i}`} className={s.seg}>
            <span className={s.ts}>{formatDuration(seg.ts_sec)}</span>
            <span>{seg.text}</span>
          </div>
        ))}
      </div>
    </aside>
  );
}
