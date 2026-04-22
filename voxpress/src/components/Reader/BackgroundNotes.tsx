import type { BackgroundNotes as BackgroundNotesData } from '@/types/api';
import { Chip, Icon } from '@/components/primitives';
import s from './Reader.module.css';

function confidenceVariant(confidence: 'high' | 'medium' | 'low') {
  if (confidence === 'high') return 'ok';
  if (confidence === 'medium') return 'warn';
  return 'default';
}

function confidenceLabel(confidence: 'high' | 'medium' | 'low') {
  if (confidence === 'high') return '高置信度';
  if (confidence === 'medium') return '中置信度';
  return '低置信度';
}

export function BackgroundNotes({ notes }: { notes: BackgroundNotesData | null | undefined }) {
  const aliases = (notes?.aliases ?? []).filter((alias) => alias.confidence !== 'low');
  const highAliases = aliases.filter((alias) => alias.confidence === 'high');
  const mediumAliases = aliases.filter((alias) => alias.confidence === 'medium');
  const context = notes?.context?.trim() ?? '';
  if (aliases.length === 0 && !context) return null;

  return (
    <section className={s.backgroundNotes}>
      <div className={s.backgroundNotesHead}>
        <div className={s.backgroundNotesTitle}>
          <Icon name="sparkle" size={13} />
          <span>背景注</span>
        </div>
        <span className={s.backgroundNotesHint}>辅助理解，不改写正文</span>
      </div>

      {highAliases.length > 0 ? (
        <div className={s.backgroundAliasList}>
          {highAliases.map((alias) => (
            <div key={`${alias.term}-${alias.refers_to}`} className={s.backgroundAliasItem}>
              <div className={s.backgroundAliasRow}>
                <strong className={s.backgroundAliasTerm}>{alias.term}</strong>
                <span className={s.backgroundAliasArrow}>→</span>
                <span className={s.backgroundAliasTarget}>{alias.refers_to}</span>
              </div>
              <Chip variant={confidenceVariant(alias.confidence)}>{confidenceLabel(alias.confidence)}</Chip>
            </div>
          ))}
        </div>
      ) : null}

      {mediumAliases.length > 0 ? (
        <details className={s.backgroundPending}>
          <summary className={s.backgroundPendingSummary}>
            还有 {mediumAliases.length} 条待确认代称
          </summary>
          <div className={s.backgroundAliasList}>
            {mediumAliases.map((alias) => (
              <div key={`${alias.term}-${alias.refers_to}`} className={s.backgroundAliasItem}>
                <div className={s.backgroundAliasRow}>
                  <strong className={s.backgroundAliasTerm}>{alias.term}</strong>
                  <span className={s.backgroundAliasArrow}>→</span>
                  <span className={s.backgroundAliasTarget}>{alias.refers_to}</span>
                </div>
                <Chip variant={confidenceVariant(alias.confidence)}>{confidenceLabel(alias.confidence)}</Chip>
              </div>
            ))}
          </div>
        </details>
      ) : null}

      {context ? (
        <p className={s.backgroundContext}>
          <strong>补充背景：</strong>
          {context}
        </p>
      ) : null}
    </section>
  );
}
