import { getPasswordFeedback } from '../utils/passwordPolicy';

export default function PasswordStrength({ password }) {
  const feedback = getPasswordFeedback(password);
  const color = !password ? 'var(--muted)' : feedback.ready ? 'var(--success)' : 'var(--amber)';
  return <div style={{ display: 'grid', gap: 10, padding: '14px 16px', border: '1px solid var(--navy-border)', borderRadius: 'var(--radius-sm)', background: 'var(--navy-card)' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 12 }}>
      <span style={{ color: 'var(--muted)' }}>Password strength</span>
      <strong aria-live="polite" style={{ color }}>{feedback.label}</strong>
    </div>
    <div role="meter" aria-label="Password strength" aria-valuemin={0} aria-valuemax={4} aria-valuenow={feedback.score} aria-valuetext={feedback.label} style={{ display: 'flex', gap: 5 }}>
      {[1, 2, 3, 4].map(segment => <span key={segment} style={{ flex: 1, height: 4, borderRadius: 4, background: feedback.score >= segment ? color : 'var(--navy-border)', transition: 'background 160ms ease' }} />)}
    </div>
    <ul style={{ display: 'grid', gap: 7, listStyle: 'none', margin: 0, padding: 0 }}>
      {feedback.requirements.filter(rule => !rule.showWhenUnmet || (password && !rule.met)).map(rule => <li key={rule.label} style={{ display: 'flex', gap: 8, color: password && rule.met ? 'var(--success)' : 'var(--muted)', fontSize: 12, lineHeight: 1.45 }}>
        <span aria-hidden="true">{password && rule.met ? '✓' : '○'}</span><span>{rule.label}</span>
      </li>)}
    </ul>
    {password && !feedback.ready && <p style={{ margin: 0, color: 'var(--amber)', fontSize: 12 }}>{feedback.message}</p>}
    {feedback.ready && <p style={{ margin: 0, color: 'var(--muted)', fontSize: 12 }}>Meets the requirements. A longer, unique password is even better.</p>}
  </div>;
}
