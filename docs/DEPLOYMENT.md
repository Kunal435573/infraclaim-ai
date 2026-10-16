# Protected single-instance deployment

The included Compose stack runs a non-root FastAPI backend, a non-root Next.js standalone server and a Caddy gateway. Only the gateway has published ports. Every dashboard/API request requires the demo password. Evaluation API runs are disabled. SQLite and Caddy certificates use durable volumes.

## Local container rehearsal

1. Copy `.env.deploy.example` to `.env.deploy` if it does not already exist.
2. Set a unique username and bcrypt hash. Run `docker run --rm -it caddy:2-alpine caddy hash-password` to enter a password privately; paste the hash into `.env.deploy` in **single quotes**. Do not commit the file.
3. Keep `BIND_ADDRESS=127.0.0.1`, `SITE_ADDRESS=:80`, `AUTH_COOKIE_SECURE=false` and `INFRACLAIM_LLM_MODE=mock` for the local simulation.
4. Run:

```powershell
docker compose --env-file .env.deploy config --quiet
docker compose --env-file .env.deploy up --build -d
docker compose --env-file .env.deploy ps
```

Open `http://localhost:8086`. Basic authentication over HTTP is suitable only for this loopback rehearsal; public access must use HTTPS.

Create individual accounts inside the running backend with `docker compose --env-file .env.deploy exec backend python -m scripts.create_pilot_users /data/pilot-accounts.txt`, then copy the generated credentials privately with `docker compose --env-file .env.deploy cp backend:/data/pilot-accounts.txt ./pilot-accounts.txt`. This command refuses to overwrite existing accounts. The second sign-in screen records operator/reviewer/admin identity. Keep this credential file private and out of the release archive.

## Remote host

Use one Docker-capable Linux host with at least 2 GB RAM (more may be required during image builds). Copy the source without local environments/build caches, and install the private backend key as a server environment secret or protected `backend/.env` file. The key is never a Docker build argument.

Set `.env.deploy` to the chosen DNS name in `SITE_ADDRESS`, `BIND_ADDRESS=0.0.0.0`, `HTTP_PORT=80`, `HTTPS_PORT=443` and the intended inference mode. Point DNS to that host and allow inbound TCP 80/443. Caddy obtains HTTPS certificates. Use a dedicated Nebius endpoint if you require region guarantees; the public endpoint does not guarantee processing location.

Set `AUTH_COOKIE_SECURE=true` for HTTPS. Provision named accounts on the host; do not use the bundled local pilot credentials. Account creation is a local admin operation and must not be exposed as a public API.

Set `DEPLOY_DATABASE_PATH=/data/infraclaim-live.sqlite3` in `.env.deploy` for the live demo instead of continuing mock cases. Keep one backend worker/replica. Back up the volume with SQLite's online backup API before any storage or schema change. Never delete volumes as a routine restart or reset.

## Verification before claiming deployment

- Unauthenticated access to both `/` and `/api/cases` must return 401.
- `/api/health` must report version 0.8.0 and the intended mode. Health is intentionally unauthenticated for the container probe.
- Sign in with each role; confirm operators cannot approve and reviewers cannot correct or submit. Confirm decisions record the account username and sign-out revokes the session.
- `/api/ready` must return 200; it does **not** prove real inference.
- Run the five-case live smoke evaluation, then the 50-case run and live rehearsal from the host. Review failures before publishing numbers.
- In the browser, run the hero and ambiguous cases. Confirm case-specific live inference records, matched simulated memo and blocked ambiguous submission.
- Restart the backend and verify cases and the single $40,000 simulated ledger entry survive.
- Check HTTPS certificates, HTTP redirect and dashboard/API authentication on the actual remote URL.

No remote URL is supplied or verified by these files. Container build success and local rehearsal must not be described as a public deployment.

References: [Caddy authentication](https://caddyserver.com/docs/caddyfile/directives/basic_auth), [Nebius public endpoint limits](https://docs.tokenfactory.nebius.com/public-serverless).
