/** Shared formatting utilities */
export const formatCurrency = (cents) =>
  new Intl.NumberFormat('en-EG', { style: 'currency', currency: 'EGP' }).format(cents / 100);

export const formatDate = (iso) =>
  new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });

export const formatDateTime = (iso) =>
  new Date(iso).toLocaleString('en-US', { dateStyle: 'short', timeStyle: 'short' });

export const maskEmail = (email) => {
  const [local, domain] = email.split('@');
  return `${local.slice(0, 2)}**@${domain}`;
};

export const slugify = (str) =>
  str.toLowerCase().trim().replace(/[^a-z0-9\s-]/g, '').replace(/\s+/g, '-');
