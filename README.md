# TrustBridge

Neutral trust agent between buyers and sellers. Full-stack MVP with buyer/seller auth, inventory, payment intent, Razorpay UPI verification, shared ledger, disputes, admin resolution, and password reset.

## Stack
- Web: React + Vite + Tailwind CSS
- API: FastAPI (Python) + SQLite

## Requirements
- Node 18+
- Python 3.11 or 3.12 (Python 3.14 will fail `pydantic-core` build)

## Run Web
1. `cd /Users/sufyanbahauddin/TrustBridge/web`
2. `npm install`
3. `npm run dev`

## Run API
1. `cd /Users/sufyanbahauddin/TrustBridge/api`
2. `python3.12 -m venv .venv`
3. `source .venv/bin/activate`
4. `pip install -r requirements.txt`
5. Set env:
   - `export RAZORPAY_KEY_ID="your_key_id"`
   - `export RAZORPAY_KEY_SECRET="your_key_secret"`
   - `export RAZORPAY_WEBHOOK_SECRET="your_webhook_secret"`
   - `export TB_ADMIN_INVITE="your-admin-code"` (optional)
   - `export SENDGRID_API_KEY="your_sendgrid_key"`
   - `export SENDGRID_FROM_EMAIL="verified@yourdomain.com"`
   - `export APP_BASE_URL="https://yourdomain.com"`
6. `uvicorn main:app --reload --port 8000`

## Core Flows
- Register buyer or seller
- Seller adds inventory with market context
- Buyer selects card + quantity, then pays via Razorpay Checkout
- Server verifies Razorpay signature and fetches payment status
- Shared proof ledger shows Razorpay order/payment IDs
- Dispute can be opened by either side
- Admin dispute resolution dashboard (invite-only)
- Forgot password (email reset link)

## API Endpoints
- `GET /health`
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/reset-request`
- `POST /auth/reset-confirm`
- `GET /me`
- `POST /inventory` (seller)
- `GET /inventory` (seller)
- `GET /inventory/public`
- `POST /transactions` (buyer)
- `POST /transactions/{id}/create-order` (buyer)
- `GET /transactions`
- `GET /transactions/{id}`
- `POST /transactions/{id}/verify-payment`
- `POST /transactions/{id}/poll-status`
- `GET /ledger/{id}`
- `POST /disputes`
- `GET /disputes/{id}`
- `GET /admin/disputes`
- `POST /admin/disputes/{id}/resolve`
- `POST /webhooks/razorpay`

## Password Reset (Production)
- Request reset: `POST /auth/reset-request` (sends email only; no token returned)
- Confirm reset: `POST /auth/reset-confirm`
- Reset link format: `${APP_BASE_URL}/reset?token=...`

## Razorpay Webhook
Create a webhook in Razorpay Dashboard pointing to:
```
https://<your-domain>/webhooks/razorpay
```
Use the webhook secret to set `RAZORPAY_WEBHOOK_SECRET` on the API server.

Recommended events:
- `payment.captured`
- `payment.failed`
- `order.paid`

## Admin Access
Set an invite code to register admins:
```
export TB_ADMIN_INVITE="your-code"
```
When registering an admin, include header `X-Admin-Invite: your-code`.
