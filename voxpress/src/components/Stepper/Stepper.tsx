import { Icon } from '@/components/primitives';
import s from './Stepper.module.css';

export interface StepperStep {
  label: string;
}

export interface StepperProps {
  steps: StepperStep[];
  current: number; // 0-based active; steps before are done
}

export function Stepper({ steps, current }: StepperProps) {
  return (
    <div className={s.wrap}>
      {steps.map((step, idx) => {
        const done = idx < current;
        const isCurrent = idx === current;
        const cls = [s.step, done ? s.done : '', isCurrent ? s.current : ''].filter(Boolean).join(' ');
        return (
          <div key={idx} className={cls}>
            <div className={s.badge}>{done ? <Icon name="check" size={14} /> : idx + 1}</div>
            <div className={s.labelWrap}>
              <span className={s.kicker}>STEP {idx + 1}</span>
              <span className={s.label}>{step.label}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
