# Shoply admin security runbook

Admin accounts are provisioned and recovered outside the application. The public API never creates, promotes, suspends, or changes an admin account.

When changing an admin password, generate a bcrypt hash in a trusted local environment, then update MongoDB:

\`\`\`javascript
db.users.updateOne(
  { email: "admin@example.com", role: "admin" },
  {
    $set: {
      password_hash: "<bcrypt-hash>",
      status: "active",
      is_verified: true,
      updated_at: new Date()
    },
    $inc: { auth_version: 1 }
  }
)

db.refresh_tokens.updateMany(
  { user_id: "<admin-object-id-as-string>" },
  { $set: { is_revoked: true } }
)
\`\`\`

Only the database owner should run these operations. Never paste the plaintext password, SMTP app password, JWT private key, or OTP into Git, logs, or chat.

After a manual change, the next admin login must use the password followed by the email OTP. If the SMTP account is unavailable, repair the SMTP configuration before attempting login; there is no application bypass.
