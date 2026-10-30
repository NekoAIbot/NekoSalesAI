# Deploy Nera on Render

This repository includes `render.yaml`, a Render Blueprint for a free Python web service. It uses `backend` as the service root, installs `backend/requirements.txt`, runs Alembic migrations before Uvicorn starts, and listens on Render's `$PORT`. The health check is `/`.

## Create the service

1. Sign up for Render with GitHub and authorize access to `NekoAIbot/NekoSalesAI`. This account authorization is required once; it cannot be completed from this repo without the user's Render account.
2. In Render, choose **New > Blueprint**, connect `https://github.com/NekoAIbot/NekoSalesAI`, and select branch `work/nera-website-telegram`. Render will read `render.yaml`; review and create the free service. Alternatively choose **New > Web Service**, select that repo and branch, set root directory `backend`, build command `pip install -r requirements.txt`, start command `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`, and instance type `Free`.
3. In the service's Environment settings, set `PUBLIC_BASE_URL` to the assigned `https://<service>.onrender.com` URL, and set `CORS_ORIGINS` to the production origins that should be permitted. Only add credentials for integrations being enabled. The app reads these settings from `backend/app/config/settings.py`.
4. Set actual integration credentials as needed: `PAYSTACK_SECRET_KEY`, `PAYSTACK_PUBLIC_KEY`, `GROQ_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_APP_ID`, `BREVO_API_KEY`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, and `SMTP_PASSWORD`. Never commit real secrets. Render Blueprint leaves credentials blank for entry in its dashboard and generates `SECRET_KEY` automatically.

## Free-tier notes

Render's free web services spin down after 15 minutes of inactivity, so first request after idle can be delayed by a cold start. Local filesystem data on a free instance is ephemeral, and free instances do not support persistent disks. The Blueprint therefore uses SQLite only as a starter/demo configuration: its database can be lost on restart, redeploy, or instance replacement. For durable customer, order, or payment state, configure a persistent database such as managed Postgres and set `DATABASE_URL` accordingly before production use.

Render supports deploying a public Git repository without GitHub OAuth, but the public-repository mode disables auto-deploys. For the requested push-to-deploy behavior, the Render account must link GitHub and select the repo/branch. A one-command API deployment also needs an authenticated Render account, workspace, and service, so it cannot be provisioned before the user creates/signs in to that account.
