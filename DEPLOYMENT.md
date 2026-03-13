# 🏰 Karazhan Raid Planner — Deployment Guide

## Files
| File | Purpose |
|------|---------|
| `app.py` | The Streamlit application |
| `requirements.txt` | Python dependencies |
| `.streamlit/secrets.toml` | API keys (local only, never commit!) |
| `.gitignore` | Ensures secrets are not pushed to GitHub |

---

## 🖥️ Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## 🔑 How to Get Your Raid-Helper API Key

1. Go to **raid-helper.dev** → Log in with Discord
2. Navigate to **Your Servers** → Select your server
3. Click **API Keys** → **Create New Key**
4. Copy the key — you'll need it in the sidebar or as a Secret

---

## ☁️ Deploy to Streamlit Community Cloud (Free)

### Step 1 — Create GitHub Repository
1. Go to **github.com** → Click **New repository**
2. Name it e.g. `kara-raid-planner`  
3. Set to **Public** (required for free tier) or Private (Pro)
4. Click **Create repository**

### Step 2 — Upload Files
Upload these files to your repo:
- `app.py`
- `requirements.txt`
- `.gitignore`
- ⚠️ **Do NOT upload** `.streamlit/secrets.toml`

### Step 3 — Deploy
1. Go to **share.streamlit.io**
2. Click **New app**
3. Select your GitHub repo
4. Set **Main file path**: `app.py`
5. Click **Advanced settings...** → **Secrets**

### Step 4 — Add Secrets Securely
In the **Secrets** text box, paste:
```toml
RAID_HELPER_SERVER_ID = "your_discord_server_id_here"
RAID_HELPER_API_KEY   = "your_raid_helper_api_key_here"
```
Click **Save** then **Deploy**.

### Step 5 — Share the Link
After ~1 minute you get a URL like:
```
https://yourname-kara-raid-planner-app-xxxx.streamlit.app
```
Share this with your guild officers! 🎉

---

## 🔒 Why Secrets Are Safe

- Secrets stored in Streamlit Cloud are **encrypted at rest**
- They are **never visible** in the deployed app or GitHub
- The `secrets.toml` file is in `.gitignore` so it's never accidentally pushed
- The app reads credentials with `st.secrets["RAID_HELPER_API_KEY"]`

---

## 🧪 Demo Mode

If no API key is configured, the app automatically shows a **Demo Mode** checkbox
which uses 32 pre-built mock players — no API key needed for testing.

---

## 📡 Raid-Helper API Endpoints Used

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/v3/servers/{serverId}/events` | List all server events |
| GET | `/api/v2/events/{eventId}` | Get event detail + sign-ups |
| POST | `/api/v3/comps/{eventId}` | Push compositions back |

