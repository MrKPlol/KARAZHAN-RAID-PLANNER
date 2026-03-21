# 🏰 Karazhan Raid Planner
**R2 — Make Raids Great Again · TBC Classic Anniversary**

> ⚠️ **This project is the exclusive property of the R2 guild.**
> You are welcome to view the code, but copying, reusing or redistributing it for other guilds or purposes is not permitted.

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
- **Absence / Bench filter** — Raid-Helper junk entries automatically ignored
- **Role detection** from Raid-Helper's `roleName` field
- **Role Overrides** — e.g. `Stone=Tank`
- **Fixed Assignments** — lock a player to a specific raid day
- **Buddy Groups** — soft preference to keep pairs/groups together
- **Avoid Pairings** — never place two players in the same group
- **Buddy Char** — for alt players, specify which char counts for buddy logic
- **Alt-char support** — same player with different classes handled correctly

### 🎯 Score-Based Optimisation
| Buff | Class | Points |
|---|---|---|
| Bloodlust | Shaman | +300 |
| Curse of Elements | Warlock | +100 |
| Blessings | Paladin | +120 |
| Ferocious Inspiration | Hunter | +80 |
| Shadow Weaving + VT | Shadow Priest | +60 (+100 w/ Warlock) |
| Moonkin Aura | Balance Druid | +70 |
| Innervate + Rebirth + MotW | Druid | +100 |
| Arcane Brilliance | Mage | +50 |

**Equity system** — all groups get fair buffs, no stacking.

### 🏆 Parse Group
Optionally steer best buffs toward a designated group — configurable boost strength. All groups stay fair.

### 🔷🔶 Subgroup Assignments
- **Prot Paladin Tank → SG1 = Casters** (benefits from Int/Wrath of Air)
- **Druid/Warrior Tank → SG1 = Melee** (physical fighters)
- Casters: Warlock · Mage · SPriest · Ele Shaman · Boomkin
- Melee: Warriors · Rogues · Ret Paladin · Feral Druid · Enh Shaman · Hunter

### 📋 Raid Overview
Visual group cards with spec icons per player, split by subgroup — similar to the Raid-Helper Comp Tool.

### 🔄 Sync to Raid-Helper
Push final compositions back via API including correct subgroup assignments. Direct links to Raid-Helper Comp Tool after push.

---

## ☁️ Deployment (Streamlit Cloud)

1. Push repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) → New app → select repo → `app.py`
3. Advanced Settings → Secrets → paste:
```toml
RAID_HELPER_SERVER_ID = "your_discord_server_id"
RAID_HELPER_API_KEY   = "your_raidhelper_api_key"
```
4. Deploy

---

## 📁 Project Structure

```
kara-planer/
├── app.py           # Main application
├── VERSION          # Current version
├── icons/           # WoW class + spec icons
├── requirements.txt
└── .streamlit/
    └── secrets.toml  # API credentials (never commit!)
```

---

*© R2 — Make Raids Great Again · All rights reserved*
