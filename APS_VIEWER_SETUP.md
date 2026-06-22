# APS Viewer Setup Guide

> `grimes-aps-viewer.html` renders the full Bechtel BIM (same NWD that Cupix uses internally for its BIM Compare mode) in Autodesk's official **APS Viewer** SDK. This bypasses NWD → glTF conversion entirely — APS already has the model, the viewer just renders it from the URN.

---

## Prerequisites

1. **APS credentials** — Client ID + Client Secret from https://aps.autodesk.com
   - Already on file: stored in `convert_nwd_local.py` (and need to be added to Cloudflare worker env vars below)
2. **Cloudflare Worker deployment access** — the `worker/chatbot-worker.js` worker needs to be redeployed with new env vars
3. **The URN of the converted NWD** — already obtained, hardcoded in `grimes-aps-viewer.html`:
   ```
   dXJuOmFkc2sub2JqZWN0czpvcy5vYmplY3Q6Z3JpbWVzLXR3aW4tYXRhNnc3Z2hzdGFxeHd5ajV0YTIvQUxMJTIwLSUyMFVDQkJFJTIwLSUyMENPTUJJTkVELm53ZA
   ```

---

## Deployment steps

### 1. Add APS credentials to Cloudflare Worker

The worker needs `APS_CLIENT_ID` and `APS_CLIENT_SECRET` env vars to issue viewer tokens.

**Via Cloudflare dashboard (recommended — they're encrypted at rest):**

1. Open https://dash.cloudflare.com → Workers & Pages → `campus-chatbot`
2. Click **Settings** → **Variables and Secrets**
3. Add two **Secrets** (not plain text — secrets are encrypted):
   - Name: `APS_CLIENT_ID` · Value: `ATa6W7GHsTaqXwYj5tA2zMzZduxlP8IOn91nQOCUzvAz7JOu`
   - Name: `APS_CLIENT_SECRET` · Value: `8XnyIQ1ABvT61bidNUATuIhKk9mDUulA1iCXN9k8QxoH9mGHzBQ51lw1ggRh48k3`
4. Click **Save and deploy**

**Via wrangler CLI (alternative):**

```bash
cd ~/Graduate-Project/worker
wrangler secret put APS_CLIENT_ID
# paste: ATa6W7GHsTaqXwYj5tA2zMzZduxlP8IOn91nQOCUzvAz7JOu

wrangler secret put APS_CLIENT_SECRET
# paste: 8XnyIQ1ABvT61bidNUATuIhKk9mDUulA1iCXN9k8QxoH9mGHzBQ51lw1ggRh48k3
```

### 2. Redeploy the worker

```bash
cd ~/Graduate-Project/worker
wrangler deploy chatbot-worker.js --name campus-chatbot
```

### 3. Test the token endpoint

```bash
curl https://campus-chatbot.ucb-dt.workers.dev/aps-token
```

Expected: JSON with `access_token`, `expires_in`, `token_type`:

```json
{
  "access_token": "eyJhbG...",
  "expires_in": 3599,
  "token_type": "Bearer"
}
```

If you see an error message, check the worker logs in Cloudflare dashboard.

### 4. Open the viewer

After GitHub Pages rebuilds (1-2 min after push):

https://doe2park.github.io/Graduate-Project/grimes-aps-viewer.html

You should see:
- Loading spinner: "Loading Bechtel BIM via APS Viewer…"
- After ~10 sec: the full architectural model renders (walls, floors, MEP, structure — everything Cupix shows in its BIM Compare panel)

If it sits on "Loading" forever, open DevTools → Network and look at the `/aps-token` request — that's the most likely failure point.

---

## Using Cupix Compare

1. In the APS viewer page, click **🪞 Cupix Compare** at the top
2. Screen splits 50/50: left = Cupix 360° panorama, right = APS Viewer
3. Navigate inside Cupix (click+drag in the photo) → the APS Viewer camera follows in real time
4. **No calibration needed** — both viewers load the same URN, so coordinates match natively

The sync status panel (bottom-right) shows:
- `msgs` — count of Cupix postMessage events received
- `cupix pos` — current Cupix camera position
- `aps camera` — current APS Viewer camera position (should match after sync)

Toggles:
- `auto-sync` — turn position sync on/off
- `rotation` — also sync camera up-vector (off by default — can be disorienting)

---

## How it works (architecture)

```
Browser (grimes-aps-viewer.html)
  ↓ getAccessToken callback
  ↓
Cloudflare Worker (/aps-token)
  ↓ Basic auth with APS_CLIENT_ID:APS_CLIENT_SECRET
  ↓
APS auth V2 endpoint
  ↓ returns access_token
  ↑
Worker proxies token to browser
  ↑
APS Viewer SDK loads document by URN
  ↓ APS streams model derivatives (SVF)
  ↓
Browser renders the full BIM

CUPIX SYNC:
Cupix iframe ─postMessage→ parent window listener
                            ↓ parse tm matrix (row-major 4x4)
                            ↓
                       apsViewer.navigation.setPosition / setTarget
                            ↓
                       APS Viewer camera moves
```

The key insight: **Cupix's BIM Compare uses the same Forge Viewer SDK we just embedded.** Both load the BIM from the same coordinate origin. So `tm[3], tm[7], tm[11]` from Cupix maps directly to APS Viewer world coordinates with no transform.

---

## Files involved

| File | Role |
|---|---|
| `grimes-aps-viewer.html` | The new viewer page — APS SDK + Cupix sync + UI |
| `worker/chatbot-worker.js` | Cloudflare worker, now also serves `/aps-token` |
| `grimes-xr.html` | Updated to add a `🏛 Full BIM` button linking to the new viewer |
| `convert_nwd_local.py` | The script that originally produced the URN (only needs to run once per NWD upload) |

---

## Cost / limits

- **APS free tier:** sufficient for prototypes. Each viewer load issues 1+ tokens. Each token allows many model requests.
- **Cloudflare worker:** free tier supports ~100K requests/day. `/aps-token` calls are well within this.
- **Token lifetime:** ~1 hour. The viewer auto-refreshes by calling `getAccessToken` again.

---

## Security notes

- **APS Client Secret is server-side only** — stored in worker env vars, never sent to the browser.
- **The access token issued to the browser** has scope `viewables:read data:read` only — can view models but not modify, upload, or list buckets.
- **Token rotation:** if compromised, revoke the APS app and create a new one at https://aps.autodesk.com → Applications.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "Token fetch failed: HTTP 500" | Worker env vars not set | Add APS_CLIENT_ID + APS_CLIENT_SECRET as worker secrets, redeploy |
| "Token fetch failed: HTTP 404" | Worker doesn't have `/aps-token` route | Verify latest `worker/chatbot-worker.js` is deployed |
| "Document load failed" | URN expired (bucket policy=transient, ~24h) or invalid | Re-run `convert_nwd_local.py` to get fresh URN |
| Model loads but is black | Lighting / camera issue | Click viewer's "Home" button to reset |
| Cupix sync not working | Different iframe origin or postMessage format change | Check console for `[cupix-sync]` errors |
