const COMMON_PASSWORDS = new Set([
  'passwordpassword', 'password1234', '123456789012', 'qwertyuiop12',
  'letmein123456', 'adminadmin1234', 'welcome123456', 'welcome12345',
  'password123', 'password12345', 'admin123456', 'shoply123456', 'qwerty123456',
]);
const SYMBOLS = '!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~';

export function getPasswordFeedback(password) {
  const normalized = password.toLowerCase().replace(/[^a-z0-9]/g, '');
  const bytes = new globalThis.TextEncoder().encode(password).length;
  const requirements = [
    { label: 'At least 12 characters', message: 'Use at least 12 characters.', met: Array.from(password).length >= 12 },
    { label: 'An uppercase letter (A–Z)', message: 'Add an uppercase letter (A–Z).', met: /[A-Z]/.test(password) },
    { label: 'A lowercase letter (a–z)', message: 'Add a lowercase letter (a–z).', met: /[a-z]/.test(password) },
    { label: 'A number (0–9)', message: 'Add a number (0–9).', met: /[0-9]/.test(password) },
    { label: 'A symbol, such as @, # or !', message: 'Add a symbol, such as @, # or !.', met: Array.from(password).some(char => SYMBOLS.includes(char)) },
    { label: 'Avoid common passwords', message: 'Choose a less common password. Adding a symbol to a common password is not enough.', met: !!password && !COMMON_PASSWORDS.has(normalized) },
    { label: 'No spaces at the start or end', message: 'Remove spaces from the start or end.', showWhenUnmet: true, met: !!password && password.trim() === password },
    { label: 'Within the password length limit', message: 'This password is too long. Use fewer characters.', showWhenUnmet: true, met: bytes <= 72 },
  ];
  const missing = requirements.filter(rule => !rule.met);
  const ready = missing.length === 0;
  const score = !password ? 0 : ready ? (Array.from(password).length >= 16 ? 4 : 3) : Math.min(2, Math.floor(requirements.filter(rule => rule.met).length / 3));
  const label = !password ? 'Choose a strong password' : ready ? (score === 4 ? 'Strong' : 'Good') : 'Weak';
  return { requirements, ready, score, label, message: missing[0]?.message || '' };
}
