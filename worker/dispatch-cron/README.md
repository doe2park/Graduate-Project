# graduate-project-dispatch

Tiny Cloudflare Worker that triggers the BMO data workflows via `workflow_dispatch`
because GitHub's `schedule` trigger on this public repo only fires every ~4-5 hours.

| Cron | Workflow |
|---|---|
| `*/15 * * * *` | `bmo-campus-energy.yml` (campus) |
| `7,22,37,52 * * * *` | `bmo-fetch.yml` (Grimes, offset kept) |

## Setup

1. Create a fine-grained GitHub PAT (Settings > Developer settings > Personal access tokens):
   repository access limited to `doe2park/Graduate-Project` only, permission
   **Actions: Read and write** only, and a short expiry (e.g. 30-90 days; note the date to rotate it).
2. Store it as a secret:
   ```
   cd worker/dispatch-cron
   npx wrangler secret put GITHUB_TOKEN
   ```
3. Deploy:
   ```
   npx wrangler deploy
   ```
4. Verify: in the repo's Actions tab, runs should appear with event `workflow_dispatch`
   roughly every 15 minutes. Failed dispatches are logged (`npx wrangler tail`).

## Notes

- Cost: Workers free tier includes cron triggers (96 + 96 invocations/day, far below limits);
  Actions minutes are free for public repos.
- Both workflows use `concurrency: cancel-in-progress: true`, so an overlapping run cancels the older one.
- The existing `schedule` cron in the workflows stays as a fallback.
- The Worker exposes no public endpoint (every HTTP request returns 404).
- When the PAT expires, dispatches fail with 401 and are logged; create a new token and re-run step 2.

## Stop

Remove the `[triggers]` section and redeploy, or delete the Worker entirely:
```
cd worker/dispatch-cron && npx wrangler delete
```
Also revoke the PAT on GitHub.

## Test

`node --test tests/dispatch-cron.test.mjs` (from the repo root; no Cloudflare access needed).
