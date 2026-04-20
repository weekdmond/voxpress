import { useEffect, useState } from 'react';
import { useDensity, type Density } from '@/hooks/useDensity';
import s from './TweaksPanel.module.css';

interface Tweaks {
  density: Density;
  fontSerif: boolean;
  accentHue: number;
}

const DEFAULTS: Tweaks = {
  density: 'comfortable',
  fontSerif: false,
  accentHue: 210,
};

export function TweaksPanel() {
  const [open, setOpen] = useState(false);
  const { density, setDensity } = useDensity();
  const [fontSerif, setFontSerif] = useState<boolean>(() => document.body.classList.contains('serif'));
  const [accentHue, setAccentHue] = useState<number>(DEFAULTS.accentHue);

  useEffect(() => {
    if (import.meta.env.VITE_ENABLE_TWEAKS !== 'true') return;
    const onMessage = (ev: MessageEvent) => {
      if (ev.data?.type === '__activate_edit_mode') setOpen(true);
      if (ev.data?.type === '__deactivate_edit_mode') setOpen(false);
    };
    window.addEventListener('message', onMessage);
    window.parent.postMessage({ type: '__edit_mode_available' }, '*');
    return () => window.removeEventListener('message', onMessage);
  }, []);

  useEffect(() => {
    document.body.classList.toggle('serif', fontSerif);
  }, [fontSerif]);

  useEffect(() => {
    // Leave default tokens untouched in current MVP — store for now
    document.documentElement.style.setProperty('--vp-accent-hue', String(accentHue));
  }, [accentHue]);

  if (!open) return null;

  const emit = (patch: Partial<Tweaks>) => {
    window.parent.postMessage({ type: '__edit_mode_set_keys', edits: patch }, '*');
  };

  return (
    <div className={s.panel} role="dialog" aria-label="Tweaks">
      <div className={s.head}>
        <span>Tweaks</span>
        <button className={s.close} onClick={() => setOpen(false)}>
          close
        </button>
      </div>
      <div className={s.row}>
        <span>密度</span>
        <div className={s.radioGroup}>
          {(['comfortable', 'compact'] as const).map((v) => (
            <button
              key={v}
              className={[s.radio, density === v ? s.active : ''].join(' ')}
              onClick={() => {
                setDensity(v);
                emit({ density: v });
              }}
            >
              {v === 'comfortable' ? '舒适' : '紧凑'}
            </button>
          ))}
        </div>
      </div>
      <div className={s.row}>
        <span>正文字体</span>
        <button
          className={[s.radio, fontSerif ? s.active : ''].join(' ')}
          onClick={() => {
            const v = !fontSerif;
            setFontSerif(v);
            emit({ fontSerif: v });
          }}
        >
          {fontSerif ? 'Serif' : 'Sans'}
        </button>
      </div>
      <div className={s.row}>
        <span>Accent</span>
        <input
          type="range"
          min={180}
          max={260}
          value={accentHue}
          onChange={(e) => {
            const v = Number(e.target.value);
            setAccentHue(v);
            emit({ accentHue: v });
          }}
        />
      </div>
    </div>
  );
}
