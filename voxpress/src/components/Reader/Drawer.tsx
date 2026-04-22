import { useEffect, useMemo, useState } from 'react';
import { Button, Chip } from '@/components/primitives';
import { formatDuration } from '@/lib/format';
import type { TranscriptSegment } from '@/types/api';
import s from './Reader.module.css';

type CorrectionStatus = 'pending' | 'ok' | 'skipped' | 'failed' | null | undefined;

interface DrawerProps {
  segments: TranscriptSegment[];
  rawText?: string | null;
  correctedText?: string | null;
  correctionStatus?: CorrectionStatus;
  corrections?: Array<{ from: string; to: string; reason: string }>;
  whisperModel?: string | null;
  whisperLanguage?: string | null;
  correctorModel?: string | null;
  initialPromptUsed?: string | null;
}

function correctionChip(status: CorrectionStatus) {
  switch (status) {
    case 'ok':
      return <Chip variant="ok">纠错完成</Chip>;
    case 'skipped':
      return <Chip>未启用纠错</Chip>;
    case 'failed':
      return <Chip variant="warn">纠错失败 · 已降级原稿</Chip>;
    case 'pending':
      return <Chip variant="warn">待纠错</Chip>;
    default:
      return null;
  }
}

export function Drawer({
  segments,
  rawText,
  correctedText,
  correctionStatus,
  corrections = [],
  whisperModel,
  whisperLanguage,
  correctorModel,
  initialPromptUsed,
}: DrawerProps) {
  const [mode, setMode] = useState<'corrected' | 'raw'>(
    correctedText?.trim() ? 'corrected' : 'raw',
  );
  useEffect(() => {
    setMode(correctedText?.trim() ? 'corrected' : 'raw');
  }, [correctedText]);
  const correctedParagraphs = useMemo(
    () =>
      (correctedText || '')
        .split('\n')
        .map((part) => part.trim())
        .filter(Boolean),
    [correctedText],
  );
  const rawParagraphs = useMemo(
    () =>
      (rawText || '')
        .split('\n')
        .map((part) => part.trim())
        .filter(Boolean),
    [rawText],
  );

  const meta = [
    whisperModel ? `whisper ${whisperModel}` : null,
    whisperLanguage === 'auto' ? '自动语言' : whisperLanguage === 'zh' ? '中文' : whisperLanguage,
  ].filter(Boolean);

  return (
    <aside className={s.drawer}>
      <div className={s.drawerHead}>
        <div className={s.drawerHeadTop}>
          <Chip variant="accent">{mode === 'corrected' ? '纠错后稿' : '原始逐字稿'}</Chip>
          {correctionChip(correctionStatus)}
        </div>
        <div className={s.drawerModeBar}>
          <Button
            size="sm"
            variant={mode === 'corrected' ? 'primary' : 'default'}
            onClick={() => setMode('corrected')}
            disabled={!correctedText?.trim()}
          >
            纠错稿
          </Button>
          <Button
            size="sm"
            variant={mode === 'raw' ? 'primary' : 'default'}
            onClick={() => setMode('raw')}
          >
            原稿
          </Button>
        </div>
        <div className={s.drawerMetaStack}>
          {meta.length ? <span className={s.drawerMeta}>{meta.join(' · ')}</span> : null}
          {mode === 'corrected' && correctorModel ? (
            <span className={s.drawerMeta}>corrector {correctorModel}</span>
          ) : null}
          {initialPromptUsed ? (
            <span className={s.drawerMeta}>initial prompt 已注入</span>
          ) : null}
        </div>
      </div>
      <div className={s.drawerBody}>
        {mode === 'raw' ? (
          segments.map((seg, i) => (
            <div key={`${seg.ts_sec}-${i}`} className={s.seg}>
              <span className={s.ts}>{formatDuration(seg.ts_sec)}</span>
              <span>{seg.text}</span>
            </div>
          ))
        ) : correctedParagraphs.length ? (
          <>
            <div className={s.correctedBlock}>
              {correctedParagraphs.map((part, idx) => (
                <p key={idx}>{part}</p>
              ))}
            </div>
            {corrections.length ? (
              <div className={s.changeList}>
                <div className={s.changeListTitle}>本次纠错 {corrections.length} 处</div>
                {corrections.map((change, idx) => (
                  <div key={`${change.from}-${change.to}-${idx}`} className={s.changeItem}>
                    <strong>{change.from}</strong>
                    <span>→</span>
                    <strong>{change.to}</strong>
                    {change.reason ? <em>{change.reason}</em> : null}
                  </div>
                ))}
              </div>
            ) : null}
          </>
        ) : rawParagraphs.length ? (
          <div className={s.correctedBlock}>
            {rawParagraphs.map((part, idx) => (
              <p key={idx}>{part}</p>
            ))}
          </div>
        ) : (
          <div className={s.drawerEmpty}>暂无逐字稿</div>
        )}
      </div>
    </aside>
  );
}
