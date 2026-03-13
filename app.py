"""
Karazhan Raid Planner  ·  R2 — Make Raids Great Again
──────────────────────────────────────────────────────
Fixes in this version:
  • Absence Filter: Ignoriert Spieler mit Status oder Klasse 'Absence'.
  • Stone-Fix: Stone wird fest als Tank und fest am Montag (Monday) gesetzt.
  • Monday-Double-Raid: Priorisiert Montag für zwei Gruppen, um insgesamt 3 Raids zu füllen.
  • Beinhaltet den gesamten Originalcode (Buddies, Styling, Editor).
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
#  CONSTANTS
# ══════════════════════════════════════════════════════════════════

API_BASE   = "https://raid-helper.dev/api"
DAY_LABELS = ["Sunday", "Monday", "Tuesday"]
DAY_EMOJI  = ["☀️", "🌙", "⚔️"]

STRICT_CONFIRMED = {"primary", "confirmed", "spec"}
LOOSE_CONFIRMED  = {"primary", "confirmed", "spec", "late", "tentative", "standby"}

ROLE_NORM: dict = {
    "tank": "Tank", "tanks": "Tank", "tank1": "Tank", "tank2": "Tank",
    "maintank": "Tank", "offtank": "Tank", "mt": "Tank", "ot": "Tank",
    "protection": "Tank",
    "heal": "Healer", "healer": "Healer", "healers": "Healer",
    "healing": "Healer", "holy": "Healer", "resto": "Healer",
    "restoration": "Healer", "disc": "Healer", "discipline": "Healer",
    "dps": "DPS", "ranged": "DPS", "ranged dps": "DPS", "rdps": "DPS",
    "melee": "DPS", "melee dps": "DPS", "mdps": "DPS",
    "damage": "DPS", "damager": "DPS", "dd": "DPS", "caster": "DPS",
    "striker": "DPS",
    "1": "Tank", "2": "Healer", "3": "DPS", "4": "DPS", "5": "DPS",
}

SPEC_ROLE_FALLBACK: dict = {
    "protection": "Tank",  "prot": "Tank",  "blood": "Tank",
    "guardian":   "Tank",  "brewmaster": "Tank", "vengeance": "Tank",
    "holy":       "Healer","discipline":  "Healer","disc": "Healer",
    "restoration":"Healer","resto":       "Healer",
    "mistweaver": "Healer","preservation":"Healer",
}

CLASS_EMOJI: dict = {
    "warrior": "<:warrior:>",  "paladin": "<:paladin:>",
    "hunter":  "<:hunter:>",  "rogue":   "<:rogue:>",
    "priest":  "<:priest:>",  "shaman":  "<:shaman:>",
    "mage":    "<:mage:>",    "warlock": "<:warlock:>",
    "druid":   "<:druid:>",   "death knight": "<:deathknight:>",
    "dk":      "<:deathknight:>",
}

CLASS_COLOR: dict = {
    "warrior": "#C79C6E", "paladin": "#F58CBA", "hunter": "#ABD473",
    "rogue":   "#FFF569", "priest":  "#FFFFFF", "shaman": "#0070DE",
    "mage":    "#69CCF0", "warlock": "#9482C9", "druid":  "#FF7D0A",
    "death knight": "#C41E3A", "dk": "#C41E3A",
}

ROLE_EMOJI_MAP = {"Tank": "🛡️", "Healer": "💚", "DPS": "⚔️"}
TARGET         = {"Tank": 1, "Healer": 2, "DPS": 7}
RAID_SIZE      = 10
KARA_KEYWORDS  = ["kara", "karazhan", "karaz"]

DEFAULT_BUDDIES = (
    "Ketaminkåre,Tuva\n"
    "Miroga,Terry,Vowly\n"
    "Xylvia,Rockedw\n"
    "Mb,Langballje\n"
    "Stone,Pumpyy"
)
DEFAULT_FIXED    = "Stone=Monday\nPumpyy=Monday"
DEFAULT_OVERRIDES = "Stone=Tank"


# ══════════════════════════════════════════════════════════════════
#  DATA CLASS
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
    def color(self) -> str:
        return CLASS_COLOR.get(self.class_name.lower(), "#AAAAAA")

    @property
    def name_lower(self) -> str:
        return self.name.lower().strip()


# ══════════════════════════════════════════════════════════════════
#  API HELPERS
# ══════════════════════════════════════════════════════════════════

def _headers(k: str) -> dict:
    return {"Authorization": k, "Content-Type": "application/json"}

@st.cache_data(ttl=120, show_spinner=False)
def fetch_server_events(server_id: str, api_key: str) -> list:
    url = f"{API_BASE}/v3/servers/{server_id}/events"
    try:
        r = requests.get(url, headers=_headers(api_key), timeout=10)
        r.raise_for_status()
        d = r.json()
        return d if isinstance(d, list) else (d.get("postedEvents") or d.get("events") or [])
    except requests.HTTPError as e:
        st.error(f"API {e.response.status_code}: {e.response.text[:200]}")
        return []
    except Exception as e:
        st.error(f"Network error: {e}")
        return []

@st.cache_data(ttl=60, show_spinner=False)
def fetch_event_detail(event_id: str, api_key: str) -> dict:
    url = f"{API_BASE}/v2/events/{event_id}"
    try:
        r = requests.get(url, headers=_headers(api_key), timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as e:
        st.error(f"API {e.response.status_code} for event {event_id}")
        return {}
    except Exception as e:
        st.error(f"Network error: {e}")
        return {}

def push_composition(event_id: str, api_key: str, groups: list) -> tuple:
    url     = f"{API_BASE}/v3/comps/{event_id}"
    payload = []
    for idx, group in enumerate(groups, 1):
        for pos, p in enumerate(group, 1):
            payload.append({"userId": p.get("user_id",""), "name": p.get("name",""),
                             "groupId": idx, "position": pos})
    try:
        r = requests.post(url, headers=_headers(api_key), json=payload, timeout=15)
        r.raise_for_status()
        return True, "Success"
    except requests.HTTPError as e:
        return False, f"{e.response.status_code}: {e.response.text[:300]}"
    except Exception as e:
        return False, str(e)


# ══════════════════════════════════════════════════════════════════
#  EVENT HELPERS
# ══════════════════════════════════════════════════════════════════

def _event_ts(e: dict) -> int:
    return int(e.get("startTime") or e.get("date") or 0)

def _is_kara(e: dict) -> bool:
    return any(kw in (e.get("title") or "").lower() for kw in KARA_KEYWORDS)

def _event_label(e: dict) -> str:
    ts = _event_ts(e)
    try:
        dt      = datetime.fromtimestamp(ts, tz=timezone.utc)
        weekday = dt.strftime("%A")
        date    = dt.strftime("%d %b %Y")
        t       = dt.strftime("%H:%M")
    except Exception:
        weekday = date = t = "?"
    emoji = next((em for em, lb in zip(DAY_EMOJI, DAY_LABELS)
                  if lb.lower() == weekday.lower()), "")
    title   = e.get("title") or "(no title)"
    n_subs  = len(e.get("signUps") or e.get("signups") or [])
    sub_str = f"  ·  {n_subs} sign-ups" if n_subs else ""
    return f"{emoji} {weekday}  {date} {t} UTC  —  {title}{sub_str}"

def filter_events(events: list, show_all: bool) -> list:
    if not show_all:
        now    = datetime.now(tz=timezone.utc)
        past   = (now - timedelta(days=14)).timestamp()
        future = (now + timedelta(days=30)).timestamp()
        events = [e for e in events if past <= _event_ts(e) <= future]
    kara  = sorted([e for e in events if _is_kara(e)],     key=_event_ts, reverse=True)
    other = sorted([e for e in events if not _is_kara(e)], key=_event_ts, reverse=True)
    return kara + other


def _weekday_info(ts: int) -> tuple:
    """Returns (emoji, weekday_name) for a Unix timestamp."""
    try:
        dt      = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        weekday = dt.strftime("%A")
        emoji   = next((em for em, lb in zip(DAY_EMOJI, DAY_LABELS)
                        if lb.lower() == weekday.lower()), "📅")
        return emoji, weekday
    except Exception:
        return "📅", "Unknown"


def make_day_info(selected_events: list) -> dict:
    """
    Returns {day_idx: (emoji, weekday_name)} based on real event timestamps.
    Works for any number of selected events (2, 3, 4…).
    Two events on the same weekday both get that name — A/B suffix added by algorithm.
    """
    return {i: _weekday_info(_event_ts(e)) for i, e in enumerate(selected_events)}


def make_dynamic_day_map(day_info: dict) -> dict:
    """
    Maps weekday name aliases → list of day_idx values.
    So 'stone=monday' resolves to whichever slot(s) have a Monday event.
    """
    dm: dict = {}
    for idx, (em, wd) in day_info.items():
        for alias in [wd.lower(), wd.lower()[:3]]:
            dm.setdefault(alias, [])
            if idx not in dm[alias]:
                dm[alias].append(idx)
    for i in range(5):
        dm[str(i)] = [i]
    return dm



# ══════════════════════════════════════════════════════════════════
#  PARSING
# ══════════════════════════════════════════════════════════════════

def _extract_role(s: dict) -> str:
    for f in ["entryType","role","roleName","roleType","signUpRole","position","class_role","type"]:
        raw = s.get(f)
        if raw is None:
            continue
        resolved = ROLE_NORM.get(str(raw).lower().strip(), "")
        if resolved:
            return resolved
    spec = str(s.get("specName") or s.get("spec") or "").lower().strip()
    return SPEC_ROLE_FALLBACK.get(spec, "DPS")

def parse_signups(event_data: dict, day_idx: int, strict: bool, role_overrides: dict) -> list:
    statuses = STRICT_CONFIRMED if strict else LOOSE_CONFIRMED
    signups  = (event_data.get("signUps") or event_data.get("signups")
                or event_data.get("players") or [])
    players  = []
    for s in signups:
        # --- FIX: ABSENCE FILTER ---
        status = str(s.get("status","")).lower().strip()
        if status not in statuses or status == "absence":
            continue

        cls = str(s.get("className") or s.get("class") or "").lower().strip()
        if cls == "absence" or not cls:
            continue

        uid  = str(s.get("userId") or s.get("id") or s.get("discordId") or s.get("name") or "")
        name = s.get("name") or s.get("displayName") or s.get("characterName") or "Unknown"
        spec = str(s.get("specName") or s.get("spec") or "").strip()
        role = _extract_role(s)

        # --- FIX: ROLE OVERRIDES (Stone=Tank) ---
        override_role = role_overrides.get(name.lower().strip())
        if override_role:
            role = override_role

        players.append(Player(
            user_id=uid or name, name=name,
            class_name=cls or "unknown", spec=spec,
            role=role, avail_days=[day_idx],
        ))
    return players


# ══════════════════════════════════════════════════════════════════
#  CONFIG PARSERS
# ══════════════════════════════════════════════════════════════════

def parse_fixed(raw: str, day_map: dict | None = None) -> dict:
    if day_map is None:
        day_map = {"sunday":[0],"monday":[1],"tuesday":[2],
                   "sun":[0],"mon":[1],"tue":[2],
                   "0":[0],"1":[1],"2":[2]}
    result: dict = {}
    for line in raw.strip().splitlines():
        if "=" not in line:
            continue
        name, _, day = line.partition("=")
        name = name.strip().lower()
        day  = day.strip().lower()
        if name and day in day_map:
            result[name] = day_map[day][0]
    return result

def parse_role_overrides(raw: str) -> dict:
    valid = {"tank":"Tank","healer":"Healer","heal":"Healer","dps":"DPS"}
    result: dict = {}
    for line in raw.strip().splitlines():
        if "=" not in line:
            continue
        name, _, role = line.partition("=")
        name = name.strip().lower()
        role = role.strip().lower()
        if name and role in valid:
            result[name] = valid[role]
    return result

def parse_buddies(raw: str) -> list:
    groups = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        members = {m.strip().lower() for m in line.split(",") if m.strip()}
        if len(members) >= 2:
            groups.append(members)
    return groups


# ══════════════════════════════════════════════════════════════════
#  ALGORITHM
# ══════════════════════════════════════════════════════════════════

def build_all_raids(players_by_day: dict, fixed_assignments: dict, buddy_groups: list, day_info: dict | None = None) -> dict:
    if day_info is None:
        day_info = {i: (DAY_EMOJI[i] if i < 3 else '📅', DAY_LABELS[i] if i < 3 else f'Day {i}') for i in range(3)}
    seen: dict = {}
    for day_idx in sorted(players_by_day):
        for p in players_by_day[day_idx]:
            key = p.name_lower
            if key not in seen:
                p.assigned = False; p.group_key = ""
                seen[key] = p
            elif day_idx not in seen[key].avail_days:
                seen[key].avail_days.append(day_idx)

    all_players = list(seen.values())
    for p in all_players:
        p.assigned = False; p.group_key = ""

    # --- FIX: FIXED DAYS (Stone=Monday) ---
    for name_lower, forced_day in fixed_assignments.items():
        if name_lower in seen:
            seen[name_lower].avail_days = [forced_day]

    for bset in buddy_groups:
        bps = [p for p in all_players if p.name_lower in bset]
        if len(bps) < 2: continue
        common = set(bps[0].avail_days)
        for bp in bps[1:]:
            common &= set(bp.avail_days)
        if common:
            for bp in bps:
                bp.avail_days = sorted(common)

    exclusive_count: dict = defaultdict(int)
    for p in all_players:
        if len(p.avail_days) == 1:
            exclusive_count[p.avail_days[0]] += 1

    # --- FIX: DYNAMIC SLOT CALCULATION (3 RAIDS TOTAL) ---
    raw_count = {d: len(v) for d, v in players_by_day.items()}
    raids_per_day: dict = {}

    # Standard-Zuweisung: 2 Raids wenn exklusiv > 18, sonst 1 wenn > 10
    all_day_idxs = sorted(players_by_day.keys())
    for d in all_day_idxs:
        excl = exclusive_count.get(d, 0)
        has_players = raw_count.get(d, 0) >= 10
        raids_per_day[d] = 2 if excl >= 18 else (1 if has_players else 0)

    total = sum(raids_per_day.values())

    active = sorted([d for d in all_day_idxs if raw_count.get(d,0) >= 10], key=lambda d: -raw_count.get(d,0))
    while total < 3 and active:
        bumped = False
        for d in active:
            if total >= 3: break
            if raids_per_day.get(d,0) < 2:
                raids_per_day[d] = raids_per_day.get(d,0) + 1
                total += 1
                bumped = True
        if not bumped: break

    slot_labels: list[tuple] = []
    # Use real weekday names from event timestamps
    for day_idx in all_day_idxs:
        n  = raids_per_day.get(day_idx, 0)
        em, dn = day_info.get(day_idx, ("📅", f"Day {day_idx}"))
        for slot in range(1, n+1):
            lbl = f"{em} {dn}" if n == 1 else f"{em} {dn} {'AB'[slot-1]}"
            slot_labels.append((day_idx, lbl))

    results: dict = {lbl: [] for _, lbl in slot_labels}
    results["🪑 Bench"] = []

    # First Pass: Exclusive
    for day_idx, label in slot_labels:
        pool = [p for p in all_players if len(p.avail_days) == 1 and p.avail_days[0] == day_idx and not p.assigned]
        fixed_here = [p for p in pool if p.name_lower in fixed_assignments and fixed_assignments[p.name_lower] == day_idx]
        others     = [p for p in pool if p not in fixed_here]

        def rq_excl(role):
            return [p for p in fixed_here if p.role == role] + [p for p in others if p.role == role]

        group = results[label]
        for p in rq_excl("Tank"):
            if sum(1 for x in group if x.role=="Tank") >= TARGET["Tank"]: break
            group.append(p); p.assigned = True; p.group_key = label
        for p in rq_excl("Healer"):
            if p.assigned: continue
            if sum(1 for x in group if x.role=="Healer") >= TARGET["Healer"]: break
            group.append(p); p.assigned = True; p.group_key = label
        dps_need = RAID_SIZE - len(group); done = 0
        for p in rq_excl("DPS"):
            if p.assigned or done >= dps_need: break
            group.append(p); p.assigned = True; p.group_key = label; done += 1

    # Second Pass: Flex
    flexible = [p for p in all_players if not p.assigned and len(p.avail_days) > 1]
    def _need(role: str, label: str) -> int:
        have = sum(1 for x in results[label] if x.role == role)
        return max(0, TARGET[role] - have)

    flexible.sort(key=lambda p: (0 if p.name_lower in fixed_assignments else 1, 0 if p.role == "Tank" else (1 if p.role == "Healer" else 2)))

    for p in flexible:
        if p.assigned: continue
        candidates = [(day_idx, lbl) for day_idx, lbl in slot_labels if day_idx in p.avail_days and len(results[lbl]) < RAID_SIZE]
        if not candidates: continue
        candidates.sort(key=lambda entry: (-_need(p.role, entry[1]), len(results[entry[1]])))
        best_day, best_label = candidates[0]
        results[best_label].append(p); p.assigned = True; p.group_key = best_label

    for p in all_players:
        if not p.assigned:
            p.group_key = "🪑 Bench"
            results["🪑 Bench"].append(p)
    return results


# ══════════════════════════════════════════════════════════════════
#  UI & EXPORT (ORIGINAL)
# ══════════════════════════════════════════════════════════════════

def discord_block(label: str, players: list) -> str:
    lines = [f"**{label}** [{len(players)}/10]", ""]
    for role in ["Tank", "Healer", "DPS"]:
        rp = [p for p in players if p.role == role]
        if not rp: continue
        lines.append(f"{ROLE_EMOJI_MAP[role]} **{role}s**")
        for p in rp:
            emoji = CLASS_EMOJI.get(p.class_name.lower(), "")
            spec  = p.spec or p.class_name.title()
            lines.append(f"  {emoji} {p.name} — {spec}")
        lines.append("")
    return "\n".join(lines).strip()


# ══════════════════════════════════════════════════════════════════
#  MOCK DATA
# ══════════════════════════════════════════════════════════════════

def _mk(title, rows):
    return {"id": title.replace(" ","_"), "title": title,
            "startTime": int(time.time()) + 3600,
            "signUps": [{"userId": n, "name": n, "className": c,
                         "specName": s, "entryType": r, "status": "primary"}
                        for n,c,s,r in rows]}

DEMO_EVENTS = [
    _mk("Kara ☀️ Sunday", [
        ("Tankbringer",  "Warrior","Protection",   "Tank"),
        ("Shieldwall",   "Paladin","Protection",   "Tank"),
        ("ChainHealer",  "Shaman", "Restoration",  "Heal"),
        ("HolyLight",    "Paladin","Holy",          "Heal"),
        ("DiscoPriest",  "Priest", "Discipline",    "Heal"),
        ("ShadowBolt",   "Warlock","Destruction",   "DPS"),
        ("ArrowStorm",   "Hunter", "Beast Mastery", "DPS"),
        ("IceBlast",     "Mage",   "Frost",         "DPS"),
        ("StabStab",     "Rogue",  "Combat",        "DPS"),
        ("Xylvia",       "Mage",   "Arcane",        "DPS"),
        ("Rockedw",      "Hunter", "Beast Mastery", "DPS"),
        ("VoidPact",     "Warlock","Affliction",    "DPS"),
    ]),
    _mk("Kara 🌙 Monday", [
        ("IronClad",     "Warrior","Protection",   "Tank"),
        ("HolyAvenger",  "Paladin","Protection",   "Tank"),
        ("WaveRider",    "Shaman", "Restoration",  "Heal"),
        ("HealBot",      "Priest", "Holy",          "Heal"),
        ("TreeHugger",   "Druid",  "Restoration",  "Heal"),
        ("Miroga",       "Mage",   "Frost",         "DPS"),
        ("Terry",        "Hunter", "Survival",      "DPS"),
        ("Vowly",        "Warlock","Destruction",   "DPS"),
        ("Mb",           "Rogue",  "Combat",        "DPS"),
        ("Langballje",   "Hunter", "Marksmanship",  "DPS"),
        ("ArcaneSpam",   "Mage",   "Arcane",        "DPS"),
        ("RageFury",     "Warrior","Fury",           "DPS"),
        ("Shadowfire",   "Priest", "Shadow",         "DPS"),
        ("Earthshaker",  "Shaman", "Enhancement",   "DPS"),
        ("Soulreaper",   "Warlock","Affliction",    "DPS"),
        ("Gracewind",    "Druid",  "Restoration",  "Heal"),
        ("Ketaminkåre",  "Rogue",  "Subtlety",      "DPS"),
        ("Tuva",         "Druid",  "Balance",       "DPS"),
        ("Ironbreaker",  "Warrior","Fury",           "DPS"),
        ("Venomstrike",  "Rogue",  "Combat",        "DPS"),
        ("Frostweave",   "Mage",   "Frost",         "DPS"),
    ]),
    _mk("Kara ⚔️ Tuesday", [
        # Stone signs up as DPS in Raid-Helper — role override makes him Tank
        ("Stone",        "Druid",  "Guardian",      "DPS"),
        ("Pumpyy",       "Paladin","Protection",   "Tank"),
        ("Totemzilla",   "Shaman", "Restoration",  "Heal"),
        ("GracefulHeal", "Priest", "Holy",          "Heal"),
        ("SacredLight",  "Paladin","Holy",          "Heal"),
        ("VoidMaster",   "Warlock","Destruction",   "DPS"),
        ("SurvivalMode", "Hunter", "Survival",      "DPS"),
        ("FrostNova",    "Mage",   "Frost",         "DPS"),
        ("BerserkX",     "Warrior","Fury",           "DPS"),
        ("ShadowDancer", "Rogue",  "Subtlety",      "DPS"),
    ]),
]


# ══════════════════════════════════════════════════════════════════
#  PAGE CONFIG + CSS
# ══════════════════════════════════════════════════════════════════

st.set_page_config(page_title="Karazhan Raid Planner", page_icon="🏰",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;600;900&family=Crimson+Pro:wght@300;400;600&display=swap');
html,body,[data-testid="stAppViewContainer"]{background:#07070f !important;color:#c2b28a !important;}
[data-testid="stHeader"]{background:transparent !important;}
.kh{background:radial-gradient(ellipse 90% 70% at 50% 0%,rgba(130,85,15,.5) 0%,transparent 70%),
    linear-gradient(180deg,#1c1005 0%,#07070f 100%);
    border-bottom:2px solid #6b4c1e;padding:2.2rem 2rem 1.8rem;
    text-align:center;margin-bottom:1.5rem;}
.kh-title{font-family:'Cinzel',serif;font-size:clamp(1.7rem,4.5vw,3rem);font-weight:900;
    color:#f0c060;text-shadow:0 0 40px rgba(240,160,40,.55),0 2px 4px rgba(0,0,0,.9);
    letter-spacing:.09em;}
.kh-sub{font-family:'Crimson Pro',serif;font-size:.95rem;color:#8a6a38;
    letter-spacing:.18em;text-transform:uppercase;margin-top:.3rem;}
.gold-div{height:1px;max-width:480px;margin:.6rem auto;
    background:linear-gradient(90deg,transparent,#c9a84c 30%,#f0c060 50%,#c9a84c 70%,transparent);}
.sh{font-family:'Cinzel',serif;font-size:1rem;font-weight:600;color:#c9a84c;
    margin:.6rem 0 .3rem;display:flex;align-items:center;gap:.35rem;}
.ib{background:rgba(201,168,76,.07);border-left:3px solid #c9a84c;border-radius:0 6px 6px 0;
    padding:.55rem .85rem;font-family:'Crimson Pro',serif;font-size:.9rem;
    color:#9a7840;margin-bottom:.8rem;}
.wb{background:rgba(200,60,30,.07);border-left:3px solid #c04020;border-radius:0 6px 6px 0;
    padding:.55rem .85rem;font-family:'Crimson Pro',serif;font-size:.9rem;
    color:#b05030;margin-bottom:.8rem;}
.sb{background:rgba(40,180,60,.07);border-left:3px solid #30a040;border-radius:0 6px 6px 0;
    padding:.55rem .85rem;font-family:'Crimson Pro',serif;font-size:.9rem;
    color:#50a060;margin-bottom:.8rem;}
.chip{font-family:'Cinzel',serif;font-size:.67rem;padding:.1rem .48rem;
    border-radius:20px;border:1px solid;font-weight:600;}
.chips{display:flex;gap:.35rem;flex-wrap:wrap;margin-bottom:.55rem;}
.stButton>button{background:linear-gradient(135deg,#3a2200,#5a3800) !important;
    border:1px solid #c9a84c !important;color:#f0c060 !important;
    font-family:'Cinzel',serif !important;font-weight:600 !important;
    letter-spacing:.06em !important;padding:.5rem 1.4rem !important;
    border-radius:4px !important;font-size:.78rem !important;
    text-transform:uppercase !important;transition:all .18s !important;}
.stButton>button:hover{background:linear-gradient(135deg,#5a3800,#7a5000) !important;
    box-shadow:0 0 18px rgba(201,168,76,.3) !important;}
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea{
    background:#0c0c18 !important;border:1px solid #2a2010 !important;
    color:#a09060 !important;font-family:'Crimson Pro',serif !important;
    border-radius:5px !important;}
[data-testid="stTextInput"] input:focus,[data-testid="stTextArea"] textarea:focus{
    border-color:#c9a84c !important;
    box-shadow:0 0 0 2px rgba(201,168,76,.18) !important;}
section[data-testid="stSidebar"]{background:#0a0a14 !important;
    border-right:1px solid #1e1810 !important;}
.stTabs [data-baseweb="tab-list"]{background:transparent !important;gap:.35rem;}
.stTabs [data-baseweb="tab"]{background:#0e0e1c !important;
    border:1px solid #2a2010 !important;border-radius:4px !important;
    color:#6a5a38 !important;font-family:'Cinzel',serif !important;
    font-size:.73rem !important;padding:.32rem .75rem !important;}
.stTabs [aria-selected="true"]{
    background:linear-gradient(135deg,#281600,#382400) !important;
    border-color:#c9a84c !important;color:#f0c060 !important;}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
#  HEADER
# ══════════════════════════════════════════════════════════════════

st.markdown("""
<div class="kh">
  <div class="kh-title">🏰 KARAZHAN RAID PLANNER</div>
  <div class="gold-div"></div>
  <div class="kh-sub">R2 — Make Raids Great Again &nbsp;·&nbsp; TBC Classic Anniversary</div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
#  LOAD CREDENTIALS (FROM SECRETS ONLY)
# ══════════════════════════════════════════════════════════════════

try:
    # We fetch them here, so we don't need text inputs in the UI
    server_id = st.secrets.get("RAID_HELPER_SERVER_ID", "")
    api_key   = st.secrets.get("RAID_HELPER_API_KEY",   "")
except Exception:
    # If secrets file is missing or corrupted
    server_id = ""
    api_key   = ""

# ══════════════════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════════════════

with st.sidebar:
    # st.markdown('<div class="sh">🔑 Credentials</div>', unsafe_allow_html=True)
    # --- INPUT FIELDS REMOVED FOR SECURITY ---
    # server_id = st.text_input("Discord Server ID", value=default_server,
    #                            placeholder="123456789012345678")
    # api_key   = st.text_input("Bot API Key", value=default_key, type="password",
    #                            placeholder="/apikey show in Discord")

    # If credentials are empty, we might want to force Demo Mode
    credentials_missing = not (server_id and api_key)

    st.markdown('<div class="sh">⚙️ General Settings</div>', unsafe_allow_html=True)

    # We use a checkbox for Demo Mode, but if creds are missing, we could disable the uncheck
    demo_mode = st.checkbox("🧪 Demo Mode", value=credentials_missing,
                             disabled=credentials_missing,
                             help="Uses sample data if real API credentials are not set." if not credentials_missing
                             else "API credentials not found. Demo Mode is forced.")

    strict_mode = st.checkbox("Strict status filter", value=True,
                               help="Only primary/confirmed/spec. Uncheck for late/tentative too.")

    st.markdown("---")
    st.markdown('<div class="sh">🎭 Role Overrides</div>', unsafe_allow_html=True)
    st.markdown("""<div style='font-family:"Crimson Pro",serif;font-size:.8rem;
    color:#5a4a28;margin-bottom:.4rem'>
    Format: <code style='color:#9a7a40'>Name=Role</code> — one per line<br>
    Overrides the role from Raid-Helper.<br>
    Role = Tank / Healer / DPS<br>
    <em>Example: Stone signs up as DPS but tanks.</em>
    </div>""", unsafe_allow_html=True)
    override_raw = st.text_area("override_input", value=DEFAULT_OVERRIDES,
                                 height=80, label_visibility="collapsed",
                                 placeholder="Stone=Tank\nSomeHealer=Healer")

    st.markdown("---")
    st.markdown('<div class="sh">📌 Fixed Assignments</div>', unsafe_allow_html=True)
    st.markdown("""<div style='font-family:"Crimson Pro",serif;font-size:.8rem;
    color:#5a4a28;margin-bottom:.4rem'>
    Format: <code style='color:#9a7a40'>Name=Day</code> — one per line<br>
    Day = Sunday / Monday / Tuesday
    </div>""", unsafe_allow_html=True)
    fixed_raw = st.text_area("fixed_input", value=DEFAULT_FIXED,
                              height=90, label_visibility="collapsed",
                              placeholder="Stone=Tuesday\nTankbringer=Sunday")

    st.markdown("---")
    st.markdown('<div class="sh">👥 Buddy Groups</div>', unsafe_allow_html=True)
    st.markdown("""<div style='font-family:"Crimson Pro",serif;font-size:.8rem;
    color:#5a4a28;margin-bottom:.4rem'>
    One group per line, comma-separated.<br>
    <em>Soft preference — kept together if possible.</em>
    </div>""", unsafe_allow_html=True)
    buddy_raw = st.text_area("buddy_input", value=DEFAULT_BUDDIES,
                              height=130, label_visibility="collapsed")

    st.markdown("---")
    st.markdown("""<div style='font-family:"Crimson Pro",serif;font-size:.78rem;
    color:#4a3a20;line-height:1.7'>
    <b style='color:#7a5a28'>Rule</b>: 1 Tank · 2 Healers · 7 DPS<br>
    <b style='color:#7a5a28'>2nd group</b>: only when ≥18 <em>exclusive</em> sign-ups<br>
    <b style='color:#7a5a28'>Flex players</b>: placed where role is most needed<br>
    <b style='color:#7a5a28'>Buddies</b>: soft preference, no hard lock
    </div>""", unsafe_allow_html=True)

role_overrides    = parse_role_overrides(override_raw)
fixed_assignments = parse_fixed(fixed_raw)
buddy_groups      = parse_buddies(buddy_raw)

# ══════════════════════════════════════════════════════════════════
#  STEP 1 — Select Events
# ══════════════════════════════════════════════════════════════════

st.markdown('<div class="sh">📅 Step 1 — Select Your 3 Karazhan Events</div>',
            unsafe_allow_html=True)

if demo_mode:
    available_events = DEMO_EVENTS
    st.markdown('<div class="ib">🧪 <b>Demo Mode</b> active. '
                'Sample data is used. (Credentials are missing or Demo is checked).</div>',
                unsafe_allow_html=True)
else:
    # If creds are missing, this block will be skipped due to demo_mode being True
    with st.spinner("Loading events from Raid-Helper..."):
        raw_events = fetch_server_events(server_id, api_key)
    if not raw_events:
        st.markdown('<div class="wb">❌ No events found. Your API credentials might be invalid, or something went wrong. Check if your <code>secrets.toml</code> is correct.</div>',
                    unsafe_allow_html=True)
        st.stop()
    _, col_toggle = st.columns([3, 1])
    with col_toggle:
        show_all = st.checkbox("Show all events", value=False,
                               help="Default: last 14 days + next 30 days only.")
    available_events = filter_events(raw_events, show_all)
    if not available_events:
        st.markdown('<div class="wb">⚠️ No recent events. Enable "Show all events".</div>',
                    unsafe_allow_html=True)
        st.stop()

event_options = {_event_label(e): e for e in available_events}
event_labels  = list(event_options.keys())
kara_labels   = [l for l in event_labels if any(kw in l.lower() for kw in KARA_KEYWORDS)]
default_sel   = kara_labels[:3] if len(kara_labels) >= 3 else event_labels[:3]

st.markdown("""<div class="ib">
🏰 <b>Kara events are listed first</b> and pre-selected.
Select <b>2–4 events</b> — the app builds raids for exactly the events you pick.
Two events on the same day? Automatically gets an A/B split if enough sign-ups.
</div>""", unsafe_allow_html=True)

selected_labels = st.multiselect(
    "Choose your raid events (2–4, order matters: earliest day first)",
    options=event_labels, default=default_sel, max_selections=4,
)

if len(selected_labels) < 2:
    st.markdown(f'<div class="ib">ℹ️ Select at least <b>2 events</b> '
                f'(currently {len(selected_labels)}).</div>', unsafe_allow_html=True)
    st.stop()

selected_events = [event_options[l] for l in selected_labels]

# Show active config summary
if role_overrides:
    st.markdown('<div class="ib">🎭 Role overrides: ' +
                " · ".join(f"<b>{n.title()}</b> → {r}" for n,r in role_overrides.items()) +
                "</div>", unsafe_allow_html=True)
if fixed_assignments:
    # Build day name map from real weekday of each selected event
    _di = make_day_info(selected_events)
    _dn = {i: wd for i, (em, wd) in _di.items()}
    st.markdown('<div class="ib">📌 Fixed: ' +
                " · ".join(f"<b>{n.title()}</b> → {_dn.get(d, f'Day {d}')}"
                           for n,d in fixed_assignments.items()) +
                "</div>", unsafe_allow_html=True)
if buddy_groups:
    st.markdown('<div class="ib">👥 Buddies: ' +
                " · ".join(", ".join(sorted(g)).title() for g in buddy_groups) +
                "</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
#  STEP 2 — Calculate
# ══════════════════════════════════════════════════════════════════

st.markdown('<div class="sh">⚔️ Step 2 — Build Compositions</div>', unsafe_allow_html=True)

if st.button("⚔️  Calculate Raid Compositions", use_container_width=True):
    players_by_day: dict = {}
    debug_raw: dict      = {}

    # Derive real weekday info from event timestamps (works for any number of events)
    day_info    = make_day_info(selected_events)
    dynamic_map = make_dynamic_day_map(day_info)
    dyn_fixed   = parse_fixed(fixed_raw, dynamic_map)

    with st.spinner("Fetching sign-up data..."):
        for day_idx, event in enumerate(selected_events):
            event_data = event if demo_mode else fetch_event_detail(
                str(event.get("id","")), api_key)
            if event_data:
                raw_su = (event_data.get("signUps") or event_data.get("signups")
                          or event_data.get("players") or [])
                em, wd = day_info.get(day_idx, ("📅", f"Day {day_idx}"))
                debug_raw[f"{em} {wd} (slot {day_idx})"] = raw_su[:3]
                plist = parse_signups(event_data, day_idx, strict_mode, role_overrides)
                if plist:
                    players_by_day[day_idx] = plist

    if not players_by_day:
        st.markdown('<div class="wb">❌ No confirmed sign-ups found.</div>',
                    unsafe_allow_html=True)
        st.stop()

    results = build_all_raids(players_by_day, dyn_fixed, buddy_groups, day_info)
    st.session_state.update({
        "results": results, "selected_events": selected_events,
        "api_key_used": api_key, "demo_mode": demo_mode,
        "debug_raw": debug_raw, "day_info": day_info,
    })
    st.rerun()

# ══════════════════════════════════════════════════════════════════
#  STEP 3 — Editor + Validation
# ══════════════════════════════════════════════════════════════════

if "results" not in st.session_state:
    st.markdown("""
    <div style='text-align:center;padding:5rem 2rem;color:#2e2410'>
      <div style='font-size:3.5rem;margin-bottom:.8rem'>🏰</div>
      <div style='font-family:"Cinzel",serif;font-size:1.15rem;color:#5a4a22'>
        Select your events above and click <em>Calculate Raid Compositions</em>
      </div>
    </div>""", unsafe_allow_html=True)
    st.stop()

results      = st.session_state["results"]
sel_events   = st.session_state["selected_events"]
# We get the key used during calculation from session state
api_key_sess = st.session_state.get("api_key_used", api_key)
is_demo      = st.session_state.get("demo_mode", demo_mode)

raid_keys = [k for k in results if "Bench" not in k]
bench_key = "🪑 Bench"
n_placed  = sum(len(results[k]) for k in raid_keys)
n_bench   = len(results.get(bench_key, []))

st.markdown(f"""<div class="ib">
⚔️ <b>{len(raid_keys)} Raids</b> built &nbsp;·&nbsp;
👥 <b>{n_placed}</b> assigned &nbsp;·&nbsp;
🪑 <b>{n_bench}</b> on bench
</div>""", unsafe_allow_html=True)

if st.session_state.get("debug_raw"):
    with st.expander("🔍 Debug — Raw API fields", expanded=False):
        st.markdown('<div class="ib">First 3 raw sign-up entries per day. '
                    'Look for the field containing Tank/Healer/DPS.</div>',
                    unsafe_allow_html=True)
        for day_name, entries in st.session_state["debug_raw"].items():
            st.markdown(f"**{day_name}**")
            st.json(entries)

st.markdown('<div class="sh">🃏 Step 3 — Review & Edit Compositions</div>',
            unsafe_allow_html=True)
st.markdown('<div class="ib">💡 Change <b>Group</b> to move a player between raids or to bench. '
            'Change <b>Role</b> to fix a misclassification.</div>', unsafe_allow_html=True)

all_rows = []
for label in raid_keys + [bench_key]:
    for p in results.get(label, []):
        all_rows.append({
            "Name":      p.name,
            "Class":     p.class_name.title(),
            "Spec":      p.spec or "—",
            "Role":      p.role,
            "Group":     label,
            "Available": ", ".join(
                f"{st.session_state.get('day_info',{}).get(d,('📅',f'Day {d}'))[0]} "
                f"{st.session_state.get('day_info',{}).get(d,('📅',f'Day {d}'))[1]}"
                for d in sorted(p.avail_days)
            ),
        })

flat_df       = (pd.DataFrame(all_rows) if all_rows else
                 pd.DataFrame(columns=["Name","Class","Spec","Role","Group","Available"]))
group_options = raid_keys + [bench_key]

edited_df = st.data_editor(
    flat_df, use_container_width=True, hide_index=True, num_rows="fixed",
    column_config={
        "Name":      st.column_config.TextColumn("Name",      disabled=True, width="medium"),
        "Class":     st.column_config.TextColumn("Class",     disabled=True, width="small"),
        "Spec":      st.column_config.TextColumn("Spec",      disabled=True, width="medium"),
        "Role":      st.column_config.SelectboxColumn("Role",
                         options=["Tank","Healer","DPS"], width="small"),
        "Group":     st.column_config.SelectboxColumn("Group (reassign here)",
                         options=group_options, width="large"),
        "Available": st.column_config.TextColumn("Available", disabled=True, width="medium"),
    },
    key="player_editor",
)

edited_groups: dict = {k: [] for k in group_options}
for _, row in edited_df.iterrows():
    g = row.get("Group", bench_key)
    if g not in edited_groups:
        g = bench_key
    edited_groups[g].append(row.to_dict())

# Validation
st.markdown('<div class="sh">🔍 Live Validation</div>', unsafe_allow_html=True)
all_valid = True
val_cols  = st.columns(max(len(raid_keys), 1))

for ci, label in enumerate(raid_keys):
    g     = edited_groups.get(label, [])
    tanks = sum(1 for p in g if p.get("Role")=="Tank")
    heals = sum(1 for p in g if p.get("Role")=="Healer")
    dps   = sum(1 for p in g if p.get("Role")=="DPS")
    total = len(g)
    valid = tanks==1 and heals==2 and dps==7 and total==10
    if not valid:
        all_valid = False

    def _c(val, need, icon):
        col = "#50c050" if val==need else "#e06040"
        return (f'<span class="chip" style="color:{col};border-color:{col}30;'
                f'background:{col}18">{icon} {val}/{need}</span>')

    with val_cols[ci % len(val_cols)]:
        bc = "#30a040" if valid else "#c04020"
        st.markdown(f"""
        <div style="background:#0d0d18;border:1px solid {bc};border-radius:6px;
                    padding:.65rem .8rem;margin-bottom:.5rem">
          <div style="font-family:'Cinzel',serif;font-size:.88rem;color:#f0c060;
                      margin-bottom:.45rem">{'✅' if valid else '⚠️'} {label}</div>
          <div class="chips">
            {_c(tanks,1,'🛡️')}{_c(heals,2,'💚')}{_c(dps,7,'⚔️')}
            <span class="chip" style="color:#a09060;border-color:#4a3a2030;
                  background:#4a3a2018">📊 {total}/10</span>
          </div>
        </div>""", unsafe_allow_html=True)

if not all_valid:
    st.markdown('<div class="wb">⚠️ One or more groups violate '
                '<b>1 Tank · 2 Healers · 7 DPS</b>.</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="sb">✅ All groups are valid '
                '<b>1-2-7 compositions!</b></div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
#  STEP 4 — Discord Export
# ══════════════════════════════════════════════════════════════════

st.markdown('<div class="sh" style="margin-top:1rem">📢 Step 4 — Discord Export</div>',
            unsafe_allow_html=True)

keys_to_export = raid_keys + ([bench_key] if edited_groups.get(bench_key) else [])
if keys_to_export:
    tabs = st.tabs(keys_to_export)
    for tab, label in zip(tabs, keys_to_export):
        with tab:
            class _P:
                def __init__(self, d):
                    self.name=d.get("Name","?"); self.class_name=d.get("Class","").lower()
                    self.spec=d.get("Spec",""); self.role=d.get("Role","DPS")
            st.code(discord_block(label, [_P(r) for r in edited_groups.get(label,[])]),
                    language=None)
            st.caption("📋 Click the copy icon (top-right) to copy to clipboard.")

# ══════════════════════════════════════════════════════════════════
#  STEP 5 — Push to Raid-Helper
# ══════════════════════════════════════════════════════════════════

st.markdown('<div class="sh" style="margin-top:1rem">🔄 Step 5 — Sync to Raid-Helper</div>',
            unsafe_allow_html=True)

if is_demo:
    st.markdown('<div class="ib">ℹ️ Push disabled in Demo Mode.</div>',
                unsafe_allow_html=True)
else:
    st.markdown('<div class="ib">Overwrites compositions in Raid-Helper for all 3 events. '
                '<b>Cannot be undone from this tool.</b></div>', unsafe_allow_html=True)
    if st.button("🚀  Push Compositions to Raid-Helper", type="primary",
                 use_container_width=True):
        st.session_state["push_confirm"] = True

    if st.session_state.get("push_confirm"):
        st.warning("⚠️ **Are you sure?**\n\n"
                   "This will overwrite all event compositions in Raid-Helper.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅  Yes, push all", use_container_width=True):
                st.session_state["push_confirm"] = False
                errors, successes = [], []
                for i, label in enumerate([k for k in edited_groups if "Bench" not in k]):
                    if i >= len(sel_events):
                        break
                    eid    = str(sel_events[i].get("id",""))
                    gdicts = [{"user_id": r.get("Name",""), "name": r.get("Name","")}
                              for r in edited_groups.get(label, [])]
                    # api_key_sess contains the token used during calculation
                    ok, msg = push_composition(eid, api_key_sess, [gdicts])
                    (successes if ok else errors).append(label if ok else f"{label}: {msg}")
                if successes:
                    st.markdown(f'<div class="sb">✅ Pushed: {", ".join(successes)}</div>',
                                unsafe_allow_html=True)
                for err in errors:
                    st.markdown(f'<div class="wb">❌ {err}</div>', unsafe_allow_html=True)
        with c2:
            if st.button("❌  Cancel", use_container_width=True):
                st.session_state["push_confirm"] = False
                st.rerun()
