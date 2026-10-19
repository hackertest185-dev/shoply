/**
 * components/OTPInput.jsx  ★
 * 4-cell PIN-style input for delivery confirmation.
 * Each digit gets its own input; auto-advances on entry.
 */
import { useRef, useState } from 'react';

export function OTPInput({ value, onChange, disabled, error }) {
  const inputs = useRef([]);

  const handleChange = (index, char) => {
    if (!/^\d?$/.test(char)) return;
    const digits = value.split('');
    digits[index] = char;
    const next = digits.join('');
    onChange(next.padEnd(4, '').slice(0, 4));
    if (char && index < 3) inputs.current[index + 1]?.focus();
  };

  const handleKeyDown = (index, e) => {
    if (e.key === 'Backspace' && !value[index] && index > 0) {
      inputs.current[index - 1]?.focus();
    }
  };

  const handlePaste = (e) => {
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 4);
    onChange(pasted.padEnd(4, ''));
    inputs.current[Math.min(pasted.length, 3)]?.focus();
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <label style={{ fontSize: '13px', fontWeight: 600, color: '#b3c2b9' }}>
        Customer OTP <span style={{ color: '#dfbd89' }}>*</span>
      </label>
      <div style={{ display: 'flex', gap: '12px' }} onPaste={handlePaste}>
        {[0, 1, 2, 3].map((i) => (
          <input
            key={i}
            ref={(el) => (inputs.current[i] = el)}
            type="text"
            inputMode="numeric"
            maxLength={1}
            value={value[i] || ''}
            onChange={(e) => handleChange(i, e.target.value)}
            onKeyDown={(e) => handleKeyDown(i, e)}
            disabled={disabled}
            aria-label={`OTP digit ${i + 1}`}
            style={{
              width: '56px', height: '64px', textAlign: 'center',
              fontSize: '28px', fontWeight: 700, fontFamily: 'var(--font-mono, monospace)',
              background: '#142a27', border: `2px solid ${error ? '#ef4444' : value[i] ? '#dfbd89' : '#2a4540'}`,
              borderRadius: '12px', color: '#f7f1e7', outline: 'none',
              caretColor: '#dfbd89', transition: 'border-color 0.2s',
              opacity: disabled ? 0.5 : 1,
            }}
            onFocus={(e) => { e.target.style.borderColor = '#dfbd89'; }}
            onBlur={(e)  => { e.target.style.borderColor = value[i] ? '#dfbd89' : error ? '#ef4444' : '#2a4540'; }}
          />
        ))}
      </div>
      {error && <span style={{ fontSize: '12px', color: '#ef4444' }}>{error}</span>}
    </div>
  );
}
