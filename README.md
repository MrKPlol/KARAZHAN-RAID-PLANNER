# 🏰 Karazhan Raid Planner
**R2 — Make Raids Great Again · TBC Classic Anniversary**

A Streamlit web app for automatically building and managing Karazhan 10-man raid compositions, fully integrated with [Raid-Helper](https://raid-helper.dev).

---

## ✨ Features

### 📅 Event Management
- Connects directly to **Raid-Helper API** — no manual copy-pasting
- Supports **2–4 events** per planning session (any weekday combination)
- Auto-detects Karazhan events and pre-selects them
- Smart event filtering: shows only recent + upcoming events by default
- Automatic **A/B split** when ≥18 exclusive sign-ups on one day

### ⚔️ Composition Engine
- Strict **1 Tank · 2 Healers · 7 DPS** rule
- **Absence / Bench filter** — Raid-Helper junk entries are automatically ignored
- **Role detection** from Raid-Helper's `roleName` field (Tanks/Melee/Ranged/Healers)
- **Role Overrides** — e.g. `Stone=Tank` (signs up as DPS but tanks)
- **Fixed Assignments** — lock a player to a specific day (e.g. `Stone=Monday`)
- **Buddy Groups** — soft preference to keep pairs/groups together
- **Avoid Pairings** — never place two players in the same group (e.g. `Vowly=!Vapecum`)
- **Buddy Char** — for players with alts, specify which char counts for buddy logic (e.g. `Rock=Paladin`)
- **Alt-char support** — same player signing up with different classes is handled correctly

### 🎯 Score-Based Optimisation
Flex players (available on multiple days) are placed where they contribute most, while keeping all groups **fair and balanced**:

| Buff | Class | Points |
|---|---|---|
| Bloodlust | Shaman | +300 |
| Curse of Elements | Warlock | +150 |
| Blessings | Paladin | +120 |
| Ferocious Inspiration | Hunter | +80 |
| Shadow Weaving + VT | Shadow Priest | +100 |
| Moonkin Aura | Balance Druid | +70 |
| Innervate + Rebirth + MotW | Druid | +60 |
| Arcane Brilliance | Mage | +50 |
| SPriest × Warlock synergy | — | +50 |

**Equity system** — groups below average score attract flex players, preventing buff stacking in one group.

### 🏆 Parse Group
Optional mode to steer the best buff combinations towards a designated group — with a configurable boost strength. All groups remain fair and playable.

### 🔷🔶 Subgroup Assignments
Automatically splits each 10-man into two 5-man subgroups for Raid-Helper export:
- **SG1 (Casters):** Tank · Healers · Warlock · Mage · Boomkin · Shadow Priest · Ele Shaman
- **SG2 (Melee):** Melee DPS · Hunter · Enhancement Shaman

### 📝 Interactive Editor
- Edit Group and Subgroup assignments manually via `st.data_editor`
- Live **1-2-7 validation** per group with colour-coded chips
- Buff presence display: `✓ Shaman  ✓ Paladin  ✗ Druid  ✓ Mage  ✓ Warlock  |  ✓ SPriest`
- Score per group (⭐⭐⭐) + balance indicator across all groups

### 📢 Discord Export
- Formatted output with WoW class emojis, split by subgroup
- Copy to clipboard with one click

### 🔄 Sync to Raid-Helper
- Push final compositions back to Raid-Helper via API
- Includes correct subgroup (groupId 1/2) assignments

---

## 🚀 Setup

### Prerequisites
```
Python 3.10+
pip install streamlit requests pandas
```

### Credentials
Create `.streamlit/secrets.toml` in the project folder:
```toml
RAID_HELPER_SERVER_ID = "your_discord_server_id"
RAID_HELPER_API_KEY   = "your_raidhelper_api_key"
```

- **Server ID:** Discord → Enable Developer Mode → Right-click server → Copy Server ID
- **API Key:** In Discord, type `/apikey show` (requires admin)

### Run locally
```bash
streamlit run app.py
```

---

## ⚙️ Sidebar Configuration

| Setting | Format | Example |
|---|---|---|
| Role Override | `Name=Role` | `Stone=Tank` |
| Fixed Assignment | `Name=Day` | `Stone=Monday` |
| Buddy Groups | `Name1,Name2` (one group per line) | `Miroga,Terry,Vowly` |
| Avoid Pairings | `PlayerA=!PlayerB` | `Vowly=!Vapecum` |
| Buddy Char | `Name=Class` | `Rock=Paladin` |
| Parse Group | Checkbox + Dropdown + Slider | — |

---

## 🌐 Deployment (Streamlit Cloud)

1. Push repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) → New app → select repo → `app.py`
3. Advanced Settings → Secrets → paste your `secrets.toml` content
4. Deploy

---

## 📁 Project Structure

```
kara-planer/
├── app.py          # Main application
├── VERSION         # Current version (e.g. v1.7.2)
├── requirements.txt
└── .streamlit/
    └── secrets.toml   # API credentials (never commit this!)
```

---

*🛡️ R2 — Make Raids Great Again · TBC Classic Anniversary*
