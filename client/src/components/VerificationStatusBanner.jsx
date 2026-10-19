/**
 * components/VerificationStatusBanner.jsx  ★
 * Full-width contextual banner shown to delivery agents on /verification.
 * Displays current status and rejection reason if applicable.
 */
export function VerificationStatusBanner({ status, rejectionReason }) {
  if (!status) return null;

  const configs = {
    pending: {
      bg:    '#dfbd8911',
      border:'#dfbd8944',
      icon:  '⏳',
      title: 'Documents Under Review',
      text:  'Your documents have been submitted and are being reviewed by our admin team. This typically takes 1–2 business days.',
      color: '#dfbd89',
    },
    approved: {
      bg:    '#10b98111',
      border:'#10b98144',
      icon:  '✅',
      title: 'Verification Approved',
      text:  'Your account is verified. You can now access the delivery dashboard.',
      color: '#10b981',
    },
    rejected: {
      bg:    '#ef444411',
      border:'#ef444444',
      icon:  '❌',
      title: 'Documents Rejected',
      text:  rejectionReason || 'Your documents were not accepted. Please review the reason and re-upload corrected files.',
      color: '#ef4444',
    },
  };

  const cfg = configs[status];
  if (!cfg) return null;

  return (
    <div style={{
      background: cfg.bg, border: `1px solid ${cfg.border}`,
      borderLeft: `4px solid ${cfg.color}`,
      borderRadius: '12px', padding: '20px 24px',
      display: 'flex', gap: '16px', alignItems: 'flex-start',
      marginBottom: '24px',
    }}>
      <span style={{ fontSize: '24px', flexShrink: 0 }}>{cfg.icon}</span>
      <div>
        <div style={{ fontWeight: 700, fontSize: '15px', color: cfg.color, marginBottom: '4px' }}>
          {cfg.title}
        </div>
        <div style={{ fontSize: '14px', color: '#b3c2b9', lineHeight: 1.6 }}>
          {cfg.text}
        </div>
      </div>
    </div>
  );
}
