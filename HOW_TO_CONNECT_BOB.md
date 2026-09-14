# How to Connect IBM Bob — Transport Analytics DQ Dashboard

## What This Achieves

When Bob is connected, all 5 AI agents use live IBM Bob AI instead of
built-in fallback text. The dashboard becomes fully AI-powered.

---

## ⚠️ IBM VPN Required

The Bob inference API endpoint is **geo-restricted to IBM's internal network**.  
You must be connected to **Cisco AnyConnect VPN** (or on IBM corporate Wi-Fi)
for any API key authentication to work.

```
Endpoint: https://api.us-east.bob.ibm.com/inference/v1/chat/completions
Auth:     Authorization: Apikey <key>   ← capital A, capital K
Headers:  x-instance-id, x-team-id
Network:  IBM internal only
```

---

## Quick Start (3 steps)

### Step 1 — Connect to IBM VPN
Open **Cisco AnyConnect** and connect to the IBM VPN.

### Step 2 — Ensure `.env` has your credentials

```env
BOB_API_URL=https://api.us-east.bob.ibm.com/inference/v1/chat/completions
BOB_API_KEY=bob_prod_bob-apikey_2H6cALgAV...   ← your Inference key
BOB_MODEL=openai/gpt-oss-20b
BOB_INSTANCE_ID=your-instance-id-here
BOB_TEAM_ID=your-team-id-here
```

### Step 3 — Verify and start

```bash
python test_bob.py    # should print [OK] Connected successfully
python app.py         # starts dashboard with live Bob
```

---

## API Key Setup

1. Go to **[bob.ibm.com](https://bob.ibm.com)** (on IBM VPN)
2. Open your subscription instance → **API Key Management**
3. Click **Create API key** → choose **Inference** scope → Team: **default**
4. Copy the key (shown once only)
5. Add to `.env` as `BOB_API_KEY=<paste-key>`

> Your instance ID and team ID for this account:  
> `BOB_INSTANCE_ID=your-instance-id-here`  
> `BOB_TEAM_ID=your-team-id-here`

---

## Auth Format Details

Discovered from IBM Bob Electron app + Bob Shell (v1.0.6) source code:

| Key type | Header format | Path |
|----------|--------------|------|
| Inference (`bob_prod_bob-apikey_`) | `Authorization: Apikey <key>` | `/inference/v1/chat/completions` |
| OAuth JWT | `Authorization: Bearer <token>` | `/v1/chat/completions` |

Note: **`Apikey`** has capital A and capital K — not `apikey`, not `Bearer`.

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `HTTP 403` HTML response | Not on IBM VPN | Connect Cisco AnyConnect |
| `API Key verification failed` | Not on VPN OR key not yet active | Connect VPN; wait 5 min after creating key |
| `No IBM Bob credentials` | BOB_API_KEY not set | Add key to `.env` |
| Fallback text in dashboard UI | Bob unreachable | Check VPN; run `python test_bob.py` |

---

## Fallback Mode (No VPN)

All 5 agents have **intelligent rule-based fallback** when Bob is unreachable.
The full dashboard demo still works — Bob enhances the analysis quality.

| Agent | Without Bob | With Bob |
|-------|-------------|----------|
| Monitor | Hardcoded severity + messages | Dynamic AI-written alerts |
| Root-Cause | Pattern-matched templates | AI analysis of actual failing rows |
| Remediation | Hardcoded SQL templates | AI-generated targeted SQL fix |
| Summary | Template-based 4-sentence summary | Unique narrative summary |
| Chat | Rule-based KPI lookup | Conversational AI with full context |

The server log will show:
```
[Monitor] Bob unavailable (...) — using fallback
```
when running without VPN.
