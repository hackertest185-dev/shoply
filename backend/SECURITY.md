# Shoply security baseline

The API treats product descriptions, reviews, chat messages, and addresses as
plain text. React renders them as escaped text; no user supplied HTML is
accepted. Product uploads are validated by their decoded content and are
re-encoded as metadata-free WebP before they are stored.

## Production requirements

- Keep `DEBUG=false` and use HTTPS origins only in `ALLOWED_ORIGINS`.
- Keep MongoDB, Redis, SMTP, JWT keys, and object-storage credentials outside
  Git and Docker images.
- Configure the product bucket for read-only object delivery and keep delivery
  documents and proof-of-delivery objects private.
- Rotate JWT keys and revoke refresh-token records after a suspected exposure.
- Run the backend unit/integration suite, frontend lint/build, dependency
  audits, secret scan, and a staging OWASP ZAP baseline before release.

The public registration flow can create customers only. Admin accounts and
admin password changes are database operations; admin sign-in requires the
password plus the email MFA code. Redis stores only hashes for OTPs, reset
tokens, and short-lived rate-limit counters.
