# Shoply

Shoply is a React storefront backed by FastAPI, MongoDB, and Redis.

## Shopping flow

1. Anyone can browse the active catalog; customers sign in to save items, add them to a cart, and submit orders.
2. An admin adds products in the Admin Dashboard. Only admins can create, change, publish, or hide products.
3. The customer adds products to the cart and submits an order request with a WhatsApp number in international format, such as `+201234567890`.
4. The order is recorded as `pending_contact` and `unpaid`. The admin opens the prepared WhatsApp message and, after sending it, clicks **Confirm message sent**. The customer then sees the contact status in their orders.
5. After receiving payment and delivering the order, the admin confirms both in the dashboard. The customer can then download a PDF receipt, and the sale appears in the admin report.

Submitting an order request does not charge the customer or reserve stock. Admin accounts are provisioned separately; public registration creates customer accounts only. The application does not send a WhatsApp message automatically.

Admins can choose a JPEG, PNG, or WebP file directly in the product form; the image is stored with the product record and displayed in the catalog. WhatsApp does not tell this app whether a message was sent: the admin must confirm it in the dashboard. The prepared message includes the order items, total, InstaPay, and `01030888493`.

## Run locally

Configure `backend/.env` with MongoDB, Redis, and JWT keys, then run:

```bash
docker compose up -d --build
```

Open [http://localhost](http://localhost). The API health endpoint is [http://localhost:8000/health](http://localhost:8000/health).

For frontend development, run `npm ci` and `npm run dev` inside `client`. For backend tests, install `requirements-dev.txt` in a Python 3.11 environment, then run from `backend`:

```powershell
pytest tests -q
```

## Free public deployment

The repository contains deployment scaffolding for a zero-cost pilot:

- Cloudflare Pages builds the `client` directory with `npm ci && npm run build` and publishes `dist`.
- The Pages Function at `client/functions/api/[[path]].js` proxies `/api/*` to the Render API. Set the Pages environment variable `BACKEND_URL` to the Render service URL and keep `VITE_API_URL=/api/v1`.
- Render can deploy `render.yaml`, which defines a free Docker web service. Set `MONGO_URI`, `REDIS_URL`, `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY`, `ALLOWED_ORIGINS`, `SMTP_USER`, `SMTP_PASSWORD`, and `EMAIL_FROM` in Render. Use a free Upstash Redis database for `REDIS_URL`: this account's Render Key Value setup requires a payment card. The Gmail SMTP values are needed for customer email-code sign-in.
- Create the MongoDB Atlas Free Cluster separately, then run `ADMIN_EMAIL=... ADMIN_PASSWORD=... python scripts/bootstrap_admin.py` from `backend/` once against the production database. On a fresh database, `python -m scripts.populate_catalog` adds the sample catalog after the admin exists; categories are seeded at API startup.

The free backend sleeps after inactivity. Redis only stores temporary OTP and rate-limit data; MongoDB Atlas holds orders and products. MongoDB Atlas Free is limited in storage and throughput, so this setup is intended for a public pilot rather than a high-availability production service. Never commit `.env`, `env`, JWT keys, database passwords, or provider tokens.

## Transactional email

Account verification, sign-in codes, password recovery, order updates and chat notifications
use a shared mobile-friendly Shoply email layout, with a plain-text alternative.
Set `EMAIL_FROM_NAME=Shoply` for the sender display name. Personal Gmail SMTP always
uses the authenticated `SMTP_USER` mailbox as its actual sender address; an unverified
brand address must not impersonate a domain. Other SMTP providers require a verified
`EMAIL_FROM` address. Email action buttons only link to `FRONTEND_URL`, which must be
the public HTTPS storefront URL in production.

Delivery to the inbox is not guaranteed by an HTML template. For a branded domain,
verify that domain with the email provider and publish its SPF, DKIM and DMARC records.
Do not invent these DNS values or use a domain the store does not control. Check
received-message headers (Authentication-Results, mailed-by and signed-by) before
diagnosing spam filtering. Gmail's requirements are documented in the
[Google sender guidelines](https://support.google.com/mail/answer/81126).

## Main directories

- `backend/app/routers`: HTTP endpoints and role checks
- `backend/app/services`: product, cart, authentication, and order logic
- `backend/app/models`: MongoDB access
- `client/src/Storefront.jsx`: customer storefront and admin product/order screens

The repository also contains legacy delivery and Stripe modules. The current customer checkout uses the WhatsApp order request flow described above.

## Security baseline

Security controls and the production checklist are documented in
[`backend/SECURITY.md`](backend/SECURITY.md). Product images should be sent
through `POST /api/v1/products/images` as an admin; the API validates and
normalizes them before a product stores the resulting image value.
