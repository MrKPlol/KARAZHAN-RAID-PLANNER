"""
Karazhan Raid Planner  ·  R2 — Ultimate Edition
───────────────────────────────────────────────
KOMPLETT-VERSION:
  • Filtert 'Absence', 'Tentative', 'Late' etc. automatisch raus.
  • Stone-Fix: Fest als Tank & Montag eingeplant.
  • 2nd Raid Logik: Erstellt automatisch zwei Gruppen, wenn ein Tag voll ist.
  • Push-to-Discord: Die Aufstellung kann direkt an Raid-Helper gesendet werden.
  • Security: Nutzt Streamlit Secrets.
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from collections import defaultdict

import pandas as pd
import requests
import streamlit as st

# ══════════════════════════════════════════════════════════════════
#  KONSTANTEN
# ══════════════════════════════════════════════════════════════════

API_BASE   = "https://raid-helper.dev/api"
DAY_LABELS = ["Sunday", "Monday", "Tuesday"]
DAY_EMOJI  = ["☀️", "🌙", "⚔️"]

# Nur diese Status zählen als echte Zusage
STRICT_CONFIRMED = {"primary", "confirmed", "spec"}

ROLE_NORM: dict = {
    "tank": "Tank", "tanks": "Tank", "protection": "Tank", "mt": "Tank", "ot": "Tank",
    "heal": "Healer", "healer": "Healer", "holy": "Healer", "resto": "Healer",
    "dps": "DPS", "melee": "DPS", "ranged": "DPS", "damage": "DPS", "dd": "DPS"
}

CLASS_EMOJI: dict = {
    "warrior": "🛡️", "paladin": "✨", "hunter": "🏹", "rogue": "🔪",
    "priest": "⛪", "shaman": "⚡", "mage": "🔥", "warlock": "😈",
    "druid": "🐾", "death knight": "💀", "dk": "💀"
}

ROLE_EMOJI_MAP = {"Tank": "🛡️", "Healer": "💚", "DPS": "⚔️"}
TARGET         = {"Tank": 1, "Healer": 2, "DPS": 7}
RAID_SIZE      = 10

# R2 STANDARDS
DEFAULT_FIXED     = "Stone=Monday"
DEFAULT_OVERRIDES = "Stone=Tank"

# ══════════════════════════════════════════════════════════════════
#  DATEN-STRUKTUR & HELFER
# ══════════════════════════════════════════════════════════════════

@dataclass
class Player:
    user_id:    str
    name:       str
    class_name: str
    spec:       str
    role:       str
    avail_days: list = field(default_factory=list)
    assigned:   bool = False
    group_key:  str  = ""

    @property
    def name_lower(self) -> str:
        return self.name.lower().strip()

def _headers(k: str) -> dict:
    return {"Authorization": k, "Content-Type": "application/json"}

# ══════════════════════════════════════════════════════════════════
#  API FUNKTIONEN (INCL. PUSH)
# ══════════════════════════════════════════════════════════════════

@st.cache_data(ttl=60)
def fetch_event_detail(event_id: str, api_key: str) -> dict:
    try:
        r = requests.get(f"{API_BASE}/v2/events/{event_id}", headers=_headers(api_key), timeout=10)
        r.raise_for_status()
        return r.json()
    except: return {}

def push_composition(event_id: str, api_key: str, groups: list) -> tuple[bool, str]:
    """Schreibt die Gruppen zurück zu Raid-Helper."""
    try:
        payload = {"raidSettings": {"compositions": groups}}
        url = f"{API_BASE}/v3/events/{event_id}/compositions"
        r = requests.patch(url, headers=_headers(api_key), json=payload, timeout=10)
        if r.status_code in [200, 201, 204]:
            return True, "Success"
        return False, r.text
    except Exception as e:
        return False, str(e)

def parse_signups(event_data: dict, day_idx: int, role_overrides: dict) -> list:
    signups = event_data.get("signUps") or event_data.get("signups") or []
    players = []
    for s in signups:
        status = str(s.get("status", "")).lower().strip()
        # FILTER: "Absence", "Tentative" etc fliegen hier raus!
        if status not in STRICT_CONFIRMED:
            continue
        cls = str(s.get("className") or s.get("class") or "").lower().strip()
        if cls in ["absence", "unknown", ""]:
            continue

        name = s.get("name") or "Unknown"
        role = "DPS"
        raw_role = str(s.get("role", "")).lower()
        for k, v in ROLE_NORM.items():
            if k in raw_role:
                role = v; break

        if name.lower().strip() in role_overrides:
            role = role_overrides[name.lower().strip()]

        players.append(Player(
            user_id=str(s.get("userId") or name),
            name=name, class_name=cls, spec=str(s.get("spec", "")),
            role=role, avail_days=[day_idx]
        ))
    return players

# ══════════════════════════════════════════════════════════════════
#  ALGORITHMUS
# ══════════════════════════════════════════════════════════════════

def build_all_raids(players_by_day, fixed_assignments):
    seen: dict[str, Player] = {}
    for d_idx, plist in players_by_day.items():
        for p in plist:
            if p.name_lower not in seen:
                seen[p.name_lower] = p
            else:
                if d_idx not in seen[p.name_lower].avail_days:
                    seen[p.name_lower].avail_days.append(d_idx)

    all_players = list(seen.values())

    for name, day_idx in fixed_assignments.items():
        if name in seen:
            seen[name].avail_days = [day_idx]

    day_counts = {d: len([p for p in all_players if d in p.avail_days]) for d in range(3)}
    raids_per_day = {0: 0, 1: 0, 2: 0}
    sorted_days = sorted(day_counts.keys(), key=lambda x: day_counts[x], reverse=True)

    total_slots = 0
    for d in sorted_days:
        if total_slots < 3 and day_counts[d] >= 8:
            raids_per_day[d] = 1
            total_slots += 1

    if total_slots < 3 and sorted_days:
        raids_per_day[sorted_days[0]] += 1
    elif sorted_days and day_counts[sorted_days[0]] >= 18:
        raids_per_day[sorted_days[0]] = 2
        if sum(raids_per_day.values()) > 3:
            for d in reversed(sorted_days):
                if raids_per_day[d] == 1:
                    raids_per_day[d] = 0; break

    raid_labels = []
    for d in range(3):
        for slot in range(raids_per_day[d]):
            suffix = f" {'AB'[slot]}" if raids_per_day[d] > 1 else ""
            raid_labels.append((d, f"{DAY_EMOJI[d]} {DAY_LABELS[d]}{suffix}"))

    results = {lbl: [] for _, lbl in raid_labels}
    results["🪑 Bench"] = []

    # Verteilung Pass 1: Ein-Tages-Spieler & Fixed
    for d_idx, lbl in raid_labels:
        pool = [p for p in all_players if not p.assigned and len(p.avail_days) == 1 and p.avail_days[0] == d_idx]
        pool.sort(key=lambda x: (0 if x.role == "Tank" else (1 if x.role == "Healer" else 2)))
        for p in pool:
            if len(results[lbl]) < RAID_SIZE:
                if sum(1 for x in results[lbl] if x.role == p.role) < TARGET[p.role]:
                    results[lbl].append(p); p.assigned = True; p.group_key = lbl

    # Verteilung Pass 2: Flexible Spieler
    flex_players = [p for p in all_players if not p.assigned]
    flex_players.sort(key=lambda x: (len(x.avail_days), 0 if x.role == "Tank" else 1))

    for p in flex_players:
        best_slot, max_need = None, -1
        for d_idx, lbl in raid_labels:
            if d_idx in p.avail_days and len(results[lbl]) < RAID_SIZE:
                need = TARGET[p.role] - sum(1 for x in results[lbl] if x.role == p.role)
                if need > max_need:
                    max_need = need; best_slot = lbl
        if best_slot:
            results[best_slot].append(p); p.assigned = True; p.group_key = best_slot
        else:
            results["🪑 Bench"].append(p); p.assigned = True; p.group_key = "🪑 Bench"

    return results

# ══════════════════════════════════════════════════════════════════
#  UI
# ══════════════════════════════════════════════════════════════════

st.set_page_config(page_title="Karazhan Raid Planner", page_icon="🏰", layout="wide")

st.title("🏰 KARAZHAN RAID PLANNER — R2")

try:
    S_ID = st.secrets["RAID_HELPER_SERVER_ID"]
    A_KEY = st.secrets["RAID_HELPER_API_KEY"]
except:
    st.error("Secrets fehlen!")
    st.stop()

with st.sidebar:
    st.header("⚙️ Konfiguration")
    role_raw = st.text_area("Rollen Overrides", value=DEFAULT_OVERRIDES)
    fixed_raw = st.text_area("Festgelegte Tage", value=DEFAULT_FIXED)
    role_ov = {l.split("=")[0].strip().lower(): l.split("=")[1].strip() for l in role_raw.splitlines() if "=" in l}
    day_m = {"sunday":0, "monday":1, "tuesday":2, "sun":0, "mon":1, "tue":2}
    fix_day = {l.split("=")[0].strip().lower(): day_m.get(l.split("=")[1].strip().lower(), 1) for l in fixed_raw.splitlines() if "=" in l}

@st.cache_data(ttl=120)
def get_events():
    r = requests.get(f"{API_BASE}/v3/servers/{S_ID}/events", headers=_headers(A_KEY))
    return [e for e in r.json() if "kara" in e.get("title", "").lower()] if r.status_code == 200 else []

events = get_events()
event_options = {f"{e['title']} ({e['id']})": e for e in events}
sel_names = st.multiselect("Wähle 3 Events (So, Mo, Di)", options=list(event_options.keys()), max_selections=3)

if len(sel_names) == 3 and st.button("⚔️ PLANUNG BERECHNEN"):
    p_data = {}
    sel_events = [event_options[n] for n in sel_names]
    st.session_state["sel_events_objects"] = sel_events
    for i, ev in enumerate(sel_events):
        detail = fetch_event_detail(ev['id'], A_KEY)
        p_data[i] = parse_signups(detail, i, role_ov)
    st.session_state["raids"] = build_all_raids(p_data, fix_day)

if "raids" in st.session_state:
    raids = st.session_state["raids"]
    cols = st.columns(len(raids))
    for i, (label, plist) in enumerate(raids.items()):
        with cols[i % len(cols)]:
            st.markdown(f"### {label}")
            df = pd.DataFrame([{"Name": p.name, "Role": ROLE_EMOJI_MAP.get(p.role, "❓")} for p in plist])
            st.table(df)

    # --- PUSH ZU DISCORD ---
    st.divider()
    if st.button("🚀 Aufstellung zu Discord (Raid-Helper) übertragen"):
        sel_evs = st.session_state.get("sel_events_objects", [])
        raid_keys = [k for k in raids.keys() if "Bench" not in k]
        for i, r_key in enumerate(raid_keys):
            if i < len(sel_evs):
                # Erstelle Liste von User-IDs für Raid-Helper
                g_list = [{"user_id": p.user_id, "name": p.name} for p in raids[r_key]]
                ok, msg = push_composition(sel_evs[i]['id'], A_KEY, [g_list])
                if ok: st.success(f"Erfolg: {r_key}")
                else: st.error(f"Fehler bei {r_key}: {msg}")
