# Put the InfraClaim demo online

The local demo and live-model evaluation are complete. This document covers a **password-protected public demo**, not a production claims service. No server, domain, or public URL has been created yet.

## What the owner needs to do

1. Create a [DigitalOcean account](https://www.digitalocean.com/) and add billing privately. Do not send account credentials or payment details to anyone helping with deployment.
2. Register a domain with a registrar. DigitalOcean can manage DNS but does not sell domains. The demo can use a subdomain such as `demo.yourdomain.com`.
3. Create an Ubuntu 24.04 Droplet in a nearby region. The 2 GB Basic plan is the minimum running target; **4 GB is recommended for building the Docker images on the server**. Check the displayed price before creating it. Use SSH-key login and a cloud firewall: port 22 from your IP, ports 80 and 443 from the internet.
4. Send the deployment operator only the Droplet's public IP and the chosen demo hostname. Keep the Nebius API key, SSH private key, demo password, and billing details private.

The operator can then install Docker, place the package on the server, set the private key and demo password there, point the hostname's A record to the IP, start the containers, and verify the public URL. Wait for verification before sharing the link.

## Operator checklist

Apply [SECURITY.md](SECURITY.md) before proceeding. Production configuration must include `INFRACLAIM_DEPLOYMENT=hosted` and `AUTH_COOKIE_SECURE=true`; keep signup disabled and provision invited judge accounts. The backend must remain reachable only by the frontend/private administration path. The existing local checks do not verify a public host.

1. Follow [Docker's Ubuntu installation guide](https://docs.docker.com/engine/install/ubuntu/) to install Docker Engine and the Compose plugin. Keep the server patched and use a non-root sudo user with SSH keys.
2. Transfer `infraclaim-ai-phase6.zip` to the host and extract it. The archive contains source and reports only: no local `.env` files, private key, database, `.venv`, `node_modules`, or `.next` build.
3. In the project directory, copy `.env.deploy.production.example` to `.env.deploy`. Set `SITE_ADDRESS` to the actual hostname. Generate a bcrypt hash with `docker run --rm -it caddy:2-alpine caddy hash-password`, then place it in `DEMO_PASSWORD_HASH` with single quotes. Replace the example username.
4. Create `backend/.env` on the host with `NEBIUS_API_KEY` and the intended provider settings. Limit file permissions to the deployment user. Never put the key in Compose arguments, the ZIP, a screenshot, or chat.
5. Run `docker compose --env-file .env.deploy config --quiet`, then `docker compose --env-file .env.deploy up --build -d`. Keep one backend worker and the persistent `claims` volume.
6. Point an A record for the hostname at the Droplet IP. Caddy obtains HTTPS when public DNS resolves and ports 80/443 reach the host.
7. Verify unauthenticated `/` and `/api/cases` return 401. Then authenticate and check the dashboard, `/api/health`, `/api/ready`, saved-case persistence after restart, a live hero run, blocked ambiguous case, and simulated credit reconciliation. Confirm the browser uses HTTPS and no API key appears in responses.
8. Record the actual URL and check results in `docs/STATUS.md`. Until these checks pass, describe the app as locally validated only.

The latest local evidence is in [STATUS.md](STATUS.md). Vendor submission, dispute, acceptance, and credit posting remain simulated even when Nemotron inference is live.
