# 🏰 R2 – Karazhan Smart Planner
**Make Raids Great Again · TBC Classic Anniversary**

A Streamlit web-app that automatically assigns players to Karazhan raid days using a score-based composition optimizer.

---

## ⚙️ Hard Rules baked in
| Rule | Detail |
|------|--------|
| 🔒 Stone | Always locked as **Monday tank** |
| 🔵 Buddy group 1 | Ketaminkåre + Tuva / Cowgirlie always together |
| 🟡 Buddy group 2 | Terry + Miroga + Vowly / Voidling always together |
| 🟠 Buddy group 3 | Xylvia + Rockedw always together |
| ⚔️ Comp target | 1 Tank · 3 Healers · 6 DPS per raid |
| 🚫 No double-dipping | Each player is assigned to at most one raid |

---

## 🚀 Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## ☁️ Deploy to Streamlit Community Cloud (free, shareable link)

### Step 1 – Push to GitHub
```bash
git init
git add app.py requirements.txt README.md
git commit -m "Initial commit – R2 Kara Planner"
# Create a repo on github.com, then:
git remote add origin https://github.com/YOUR_USERNAME/r2-kara-planner.git
git push -u origin main
```

### Step 2 – Deploy on Streamlit Cloud
1. Go to **https://share.streamlit.io** and sign in with GitHub
2. Click **"New app"**
3. Select your repository (`r2-kara-planner`)
4. Set **Main file path** to `app.py`
5. Click **Deploy!**

Within ~60 seconds you'll get a public URL like:
`https://your-username-r2-kara-planner-app-xxxx.streamlit.app`

Share that link with your guild officers. ✅

---

## 📋 JSON format (raid-helper.dev)
The app accepts the standard raid-helper.dev JSON export.
Each entry should have:
```json
{
  "name": "Playername",
  "class": "warrior",
  "spec": "Protection Warrior",
  "role": "tank"
}
```
The `role` field is optional — the app infers it from class/spec automatically.
