"""
Karazhan Raid Planner  v5  ·  R2 — Make Raids Great Again
Score-based composition + Subgroups + Avoid Pairings
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter

import pandas as pd
import requests
import streamlit as st

# ─── INTERNAL VERSION MARKER — do not remove ───────────────────
# APP_FILE_VERSION = "v1.9.0"
# ───────────────────────────────────────────────────────────────

API_BASE   = "https://raid-helper.dev/api"
DAY_LABELS = ["Sunday", "Monday", "Tuesday"]
DAY_EMOJI  = ["☀️", "🌙", "⚔️"]

STRICT_CONFIRMED = {"primary", "confirmed", "spec"}
LOOSE_CONFIRMED  = {"primary", "confirmed", "spec", "late", "tentative", "standby"}
INVALID_STATUSES = {"absence", "bench", "no", "declined", "absent", "unavailable"}
VALID_WOW_CLASSES = {
    "warrior","paladin","hunter","rogue","priest",
    "shaman","mage","warlock","druid","death knight","dk",
    "tank",  # Raid-Helper stores tank-spec entries with className="Tank"
}
RAIDHELPER_TANK_SPEC_TO_CLASS: dict = {
    "protection":  "warrior",
    "protection1": "paladin",
    "guardian":    "druid",
    "blood":       "death knight",
}

ROLE_NORM: dict = {
    "tank":"Tank","tanks":"Tank","tank1":"Tank","tank2":"Tank",
    "maintank":"Tank","offtank":"Tank","mt":"Tank","ot":"Tank","protection":"Tank",
    "heal":"Healer","healer":"Healer","healers":"Healer","healing":"Healer",
    "holy":"Healer","resto":"Healer","restoration":"Healer","disc":"Healer","discipline":"Healer",
    "dps":"DPS","ranged":"DPS","ranged dps":"DPS","rdps":"DPS",
    "melee":"DPS","melee dps":"DPS","mdps":"DPS",
    "damage":"DPS","damager":"DPS","dd":"DPS","caster":"DPS","striker":"DPS",
    "1":"Tank","2":"Healer","3":"DPS","4":"DPS","5":"DPS",
}
SPEC_ROLE_FALLBACK: dict = {
    "protection":"Tank","prot":"Tank","blood":"Tank",
    "guardian":"Tank","brewmaster":"Tank","vengeance":"Tank",
    "holy":"Healer","discipline":"Healer","disc":"Healer",
    "restoration":"Healer","resto":"Healer","mistweaver":"Healer","preservation":"Healer",
}
CLASS_EMOJI: dict = {
    "warrior":"<:warrior:>","paladin":"<:paladin:>","hunter":"<:hunter:>","rogue":"<:rogue:>",
    "priest":"<:priest:>","shaman":"<:shaman:>","mage":"<:mage:>","warlock":"<:warlock:>",
    "druid":"<:druid:>","death knight":"<:deathknight:>","dk":"<:deathknight:>",
}
CLASS_COLOR: dict = {
    "warrior":"#C79C6E","paladin":"#F58CBA","hunter":"#ABD473","rogue":"#FFF569",
    "priest":"#FFFFFF","shaman":"#0070DE","mage":"#69CCF0","warlock":"#9482C9",
    "druid":"#FF7D0A","death knight":"#C41E3A","dk":"#C41E3A",
}
ROLE_EMOJI_MAP = {"Tank":"🛡️","Healer":"💚","DPS":"⚔️"}

ICON_BASE = "https://raw.githubusercontent.com/MrKPlol/KARAZHAN-RAID-PLANNER/main/icons"
CLASS_ICON_URL: dict = {
    "warrior":     f"{ICON_BASE}/class_warrior.jpg",
    "paladin":     f"{ICON_BASE}/class_paladin.jpg",
    "hunter":      f"{ICON_BASE}/class_hunter.jpg",
    "rogue":       f"{ICON_BASE}/class_rogue.jpg",
    "priest":      f"{ICON_BASE}/class_priest.jpg",
    "shaman":      f"{ICON_BASE}/class_shaman.jpg",
    "mage":        f"{ICON_BASE}/class_mage.jpg",
    "warlock":     f"{ICON_BASE}/class_warlock.jpg",
    "druid":       f"{ICON_BASE}/class_druid.jpg",
}
SPEC_ICON_URL: dict = {
    # Warrior
    "arms":           f"{ICON_BASE}/warrior_arms.jpg",
    "fury":           f"{ICON_BASE}/warrior_fury.jpg",
    "protection":     f"{ICON_BASE}/warrior_protection.jpg",
    # Paladin
    "holy":           f"{ICON_BASE}/paladin_holy.jpg",
    "protection1":    f"{ICON_BASE}/paladin_protection.jpg",
    "retribution":    f"{ICON_BASE}/paladin_retribution.jpg",
    # Hunter
    "beastmastery":   f"{ICON_BASE}/hunter_beastmastery.jpg",
    "beast mastery":  f"{ICON_BASE}/hunter_beastmastery.jpg",
    "marksmanship":   f"{ICON_BASE}/hunter_marksmanship.jpg",
    "survival":       f"{ICON_BASE}/hunter_survival.jpg",
    # Rogue
    "assassination":  f"{ICON_BASE}/rogue_assassination.jpg",
    "combat":         f"{ICON_BASE}/rogue_combat.jpg",
    "subtlety":       f"{ICON_BASE}/rogue_subtlety.jpg",
    # Priest
    "discipline":     f"{ICON_BASE}/priest_discipline.jpg",
    "shadow":         f"{ICON_BASE}/priest_shadow.jpg",
    # Shaman
    "elemental":      f"{ICON_BASE}/shaman_elemental.jpg",
    "enhancement":    f"{ICON_BASE}/shaman_enhancement.jpg",
    "restoration":    f"{ICON_BASE}/shaman_restoration.jpg",
    "restoration1":   f"{ICON_BASE}/shaman_restoration.jpg",
    # Mage
    "arcane":         f"{ICON_BASE}/mage_arcane.jpg",
    "fire":           f"{ICON_BASE}/mage_fire.jpg",
    "frost":          f"{ICON_BASE}/mage_frost.jpg",
    # Warlock
    "affliction":     f"{ICON_BASE}/warlock_affliction.jpg",
    "demonology":     f"{ICON_BASE}/warlock_demonology.jpg",
    "destruction":    f"{ICON_BASE}/warlock_destruction.jpg",
    # Druid
    "balance":        f"{ICON_BASE}/druid_balance.jpg",
    "feral":          f"{ICON_BASE}/druid_feral.jpg",
    "guardian":       f"{ICON_BASE}/druid_guardian.jpg",
}

def spec_icon_url(cls: str, spec: str) -> str:
    """Returns the best icon URL for a given class+spec combination."""
    spec_key = spec.lower().strip()
    if spec_key in SPEC_ICON_URL:
        return SPEC_ICON_URL[spec_key]
    return CLASS_ICON_URL.get(cls.lower().strip(), f"{ICON_BASE}/class_warrior.jpg")
TARGET         = {"Tank":1,"Healer":2,"DPS":7}
RAID_SIZE      = 10
KARA_KEYWORDS  = ["kara","karazhan","karaz"]

def _get_version() -> str:
    """Read version from VERSION file next to app.py — single source of truth."""
    import os
    try:
        version_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")
        with open(version_file, "r") as f:
            return f.read().strip()
    except Exception:
        return "v1.7.2"

APP_VERSION = _get_version()

DEFAULT_BUDDIES  = "Ketaminkåre,Tuva\nMiroga,Terry,Vowly\nXylvia,Rock\nMb,Langballje\nStone,Pumpyy"
DEFAULT_FIXED    = "Stone=Monday\nPumpyy=Monday"
DEFAULT_OVERRIDES= "Stone=Tank"
DEFAULT_AVOID    = "Vowly=!Vapecum"
DEFAULT_BUDDY_CHAR  = "Rock=Paladin"  # For buddy logic only: use this char. Other chars raid freely.

# ── DATA CLASS
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
    subgroup:   int  = 1

    @property
    def name_lower(self) -> str:
        return self.name.lower().strip()

# ══════════════════════════════════════════════════════════════════
#  COMPOSITION SCORING
#  Key principle: each buff scores high the FIRST time in a group,
#  near-zero the second time. This naturally distributes Shamans,
#  Warlocks, etc. across all groups without hard rules.
#  Score is a TIEBREAKER — role balance and equity always win first.
# ══════════════════════════════════════════════════════════════════

def is_melee(p: Player) -> bool:
    cls  = p.class_name.lower()
    spec = p.spec.lower()
    if cls in {"warrior","rogue","death knight","dk"}: return True
    if cls == "paladin" and "retri" in spec: return True
    if cls == "druid" and ("feral" in spec or "guardian" in spec): return True
    if cls == "shaman" and "enhancement" in spec: return True
    return False

def _has(group: list, cls_name: str) -> bool:
    return any(x.class_name.lower() == cls_name for x in group)

def _spec_match(group: list, cls_name: str, *frags) -> bool:
    return any(x.class_name.lower()==cls_name and any(f in x.spec.lower() for f in frags) for x in group)

def score_gain(player: Player, group: list, parse_boost: int = 0) -> int:
    """
    Score contribution of adding player to group.
    parse_boost: extra points for the designated parse group (0 normally).
    """
    score = 0
    cls   = player.class_name.lower()
    spec  = player.spec.lower()

    # Bloodlust/Heroism — most impactful buff in Kara
    if cls == "shaman":
        shaman_cnt = sum(1 for x in group if x.class_name.lower() == "shaman")
        if shaman_cnt == 0:
            score += 300    # First Shaman = huge value (BL)
        elif shaman_cnt == 1:
            score += 60     # Second Shaman = great! Windfury (Melee) + Wrath of Air (Casters)
        else:
            score -= 150    # Third+ Shaman = too many, diminishing returns

    # Warlock — CoE (+10% magic dmg), Healthstone, Soulstone
    if cls == "warlock":
        score += 0 if _has(group,"warlock") else 100
        if _has(group,"warlock"): score -= 20

    # Paladin — Blessings (Kings/Salv/Wisdom), Auras, BoP, Lay on Hands
    if cls == "paladin":
        score += 0 if _has(group,"paladin") else 120

    # Hunter — Ferocious Inspiration, Trueshot Aura, Misdirection
    if cls == "hunter":
        score += 0 if _has(group,"hunter") else 80

    # Shadow Priest — Shadow Weaving (13% shadow dmg), Vampiric Touch (mana regen)
    if cls == "priest" and "shadow" in spec:
        score += 0 if _spec_match(group,"priest","shadow") else 60

    # Balance Druid — Moonkin Aura (+5% spell crit for whole group)
    if cls == "druid" and any(f in spec for f in ("balance","moonkin","boomkin")):
        score += 0 if _spec_match(group,"druid","balance","moonkin","boomkin") else 70

    # Druid (any) — Innervate, Mark of the Wild, Rebirth (combat rez!)
    if cls == "druid":
        score += 0 if _has(group,"druid") else 100

    # Mage — Arcane Brilliance, Spellsteal, Polymorph CC, Curse removal
    if cls == "mage":
        score += 0 if _has(group,"mage") else 50

    # Synergy: Shadow Priest + Warlock (Shadow Weaving × CoE = best caster combo)
    if cls == "priest" and "shadow" in spec and _has(group,"warlock"): score += 100
    if cls == "warlock" and _spec_match(group,"priest","shadow"):       score += 100

    # Curse removal (Mage or Druid — helpful for Curator, Maiden, others)
    if cls in ("mage","druid") and not (_has(group,"mage") or _has(group,"druid")):
        score += 25

    # Melee / Ranged balance — gentle guidance only, no hard walls
    if player.role == "DPS":
        melee_cnt = sum(1 for x in group if x.role=="DPS" and is_melee(x))
        if is_melee(player):
            if melee_cnt < 2:   score += 50
            elif melee_cnt < 3: score += 15
            # 4+ melee: no penalty — accept reality
        else:
            if melee_cnt >= 4: score += 25

    # Class stacking penalty (mild — don't force all Druids into one group)
    same = sum(1 for x in group if x.class_name.lower()==cls)
    if same >= 3:   score -= 120
    elif same >= 2: score -= 20

    # Parse group boost — meaningful but not dominant
    score += parse_boost

    return score


def group_score(group: list) -> int:
    """Complete score for a finished group — used for display and equity."""
    score   = 0
    classes = [p.class_name.lower() for p in group]
    specs   = [(p.class_name.lower(), p.spec.lower()) for p in group]

    score += 300 if "shaman"  in classes else -200
    score += 100 if "warlock" in classes else 0
    score += 120 if "paladin" in classes else 0
    score += 80  if "hunter"  in classes else 0
    score += 100 if "druid"   in classes else 0
    score += 50  if "mage"    in classes else 0

    if any(c=="priest" and "shadow" in s for c,s in specs):   score += 60
    if any(c=="druid"  and any(f in s for f in ("balance","moonkin")) for c,s in specs): score += 70

    has_spr = any(c=="priest" and "shadow" in s for c,s in specs)
    if has_spr and "warlock" in classes: score += 100

    dps   = [p for p in group if p.role=="DPS"]
    melee = sum(1 for p in dps if is_melee(p))
    if 2 <= melee <= 3:  score += 80
    elif melee < 2:      score -= 25

    for cnt in Counter(classes).values():
        if cnt >= 3:   score -= 100
        elif cnt >= 2: score -= 10

    return score


def score_label(s: int) -> tuple:
    if s >= 700: return "⭐⭐⭐","#50c050"
    if s >= 450: return "⭐⭐","#a0c040"
    if s >= 200: return "⭐","#c0a030"
    return "⚠️","#e06040"

# ── SUBGROUP ASSIGNMENT
def _is_caster_dps(p) -> bool:
    """True if this DPS belongs in the caster subgroup."""
    cls  = p.class_name.lower()
    spec = p.spec.lower()
    if cls in ("warlock", "mage"): return True
    if cls == "priest":            return True   # Shadow Priest → caster group
    if cls == "shaman" and "elemental" in spec: return True
    if cls == "druid"  and any(f in spec for f in ("balance","moonkin","boomkin")): return True
    return False


def _is_prot_pala(p) -> bool:
    cls  = p.class_name.lower()
    spec = p.spec.lower()
    return cls == "paladin" and ("protection" in spec or "prot" in spec)


def assign_subgroups(players: list) -> list:
    """
    If tank is Prot Paladin:  SG1 = Casters,  SG2 = Melee
    If tank is Druid/Warrior: SG1 = Melee,    SG2 = Casters
    The group containing the tank is always SG1.
    """
    # Determine tank type to decide which group is SG1
    tanks = [p for p in players if p.role == "Tank"]
    pala_tank = any(_is_prot_pala(p) for p in tanks)
    # pala_tank=True  → SG1=Casters, SG2=Melee  (default)
    # pala_tank=False → SG1=Melee,   SG2=Casters (swap)

    caster_sg = 1 if pala_tank else 2
    melee_sg  = 2 if pala_tank else 1

    sg1, sg2 = [], []

    def add(p, sg):
        p.subgroup = sg
        (sg1 if sg == 1 else sg2).append(p)

    # 1. Tank → into its natural group
    for p in players:
        if p.role == "Tank":
            if _is_prot_pala(p):
                add(p, caster_sg)
            else:
                add(p, melee_sg)

    # 2. Healers → caster group first, overflow to melee group
    for p in players:
        if p.role == "Healer" and p not in sg1+sg2:
            add(p, caster_sg) if len(sg1 if caster_sg==1 else sg2) < 5 else add(p, melee_sg)

    dps      = [p for p in players if p.role == "DPS"]
    cast_dps = [p for p in dps if _is_caster_dps(p)]
    mele_dps = [p for p in dps if not _is_caster_dps(p)]

    # 3. Caster DPS → caster group preferred; swap a melee out if needed
    for p in cast_dps:
        if p in sg1+sg2: continue
        csg = sg1 if caster_sg == 1 else sg2
        msg = sg1 if melee_sg  == 1 else sg2
        if len(csg) < 5:
            add(p, caster_sg)
        else:
            melee_in_csg = [x for x in csg if not _is_caster_dps(x) and x.role == "DPS"]
            if melee_in_csg and len(msg) < 5:
                swap = melee_in_csg[-1]
                csg.remove(swap)
                swap.subgroup = melee_sg
                msg.append(swap)
                add(p, caster_sg)
            elif len(msg) < 5:
                add(p, melee_sg)

    # 4. Melee DPS → melee group preferred
    for p in mele_dps:
        if p in sg1+sg2: continue
        msg = sg1 if melee_sg == 1 else sg2
        csg = sg1 if caster_sg == 1 else sg2
        add(p, melee_sg) if len(msg) < 5 else add(p, caster_sg) if len(csg) < 5 else None

    # 5. Overflow
    for p in players:
        if p not in sg1+sg2:
            if len(sg1) < 5:   add(p, 1)
            elif len(sg2) < 5: add(p, 2)

    # 6. Fix labels in discord export: SG1 always contains the tank
    #    (already correct since we used sg_num() above)

    return sg1+sg2

# ── API HELPERS
def _headers(k: str) -> dict:
    return {"Authorization": k, "Content-Type": "application/json"}

@st.cache_data(ttl=120, show_spinner=False)
def fetch_server_events(server_id: str, api_key: str) -> list:
    url = f"{API_BASE}/v3/servers/{server_id}/events"
    try:
        r = requests.get(url, headers=_headers(api_key), timeout=10)
        r.raise_for_status()
        d = r.json()
        return d if isinstance(d,list) else (d.get("postedEvents") or d.get("events") or [])
    except requests.HTTPError as e:
        st.error(f"API {e.response.status_code}: {e.response.text[:200]}")
        return []
    except Exception as e:
        st.error(f"Network: {e}"); return []

@st.cache_data(ttl=60, show_spinner=False)
def fetch_event_detail(event_id: str, api_key: str) -> dict:
    url = f"{API_BASE}/v2/events/{event_id}"
    try:
        r = requests.get(url, headers=_headers(api_key), timeout=10)
        r.raise_for_status(); return r.json()
    except requests.HTTPError as e:
        st.error(f"API {e.response.status_code}"); return {}
    except Exception as e:
        st.error(f"Network: {e}"); return {}

def push_composition(event_id: str, api_key: str, players: list) -> tuple:
    """
    PATCH /api/v3/comps/COMPID
    Comp ID = Event ID (confirmed from Raid-Helper JSON structure).
    Payload: {"slots": [{name, className, specName, isConfirmed, groupNumber, slotNumber}]}
    groupNumber 1 = SG1 (Casters), groupNumber 2 = SG2 (Melee)
    """
    url   = f"{API_BASE}/v3/comps/{event_id}"
    slots = []
    sg1   = [p for p in players if p.get("subgroup", 1) == 1]
    sg2   = [p for p in players if p.get("subgroup", 1) == 2]
    for group_num, grp in enumerate([sg1, sg2], 1):
        for slot_num, p in enumerate(grp, 1):
            slots.append({
                "name":        p.get("name", ""),
                "className":   p.get("class_name", p.get("className", "")),
                "specName":    p.get("spec", p.get("specName", "")),
                "isConfirmed": "unconfirmed",
                "groupNumber": group_num,
                "slotNumber":  slot_num,
            })
    try:
        r = requests.patch(url, headers=_headers(api_key),
                           json={"slots": slots}, timeout=15)
        r.raise_for_status()
        return True, "Success"
    except requests.HTTPError as e:
        return False, f"{e.response.status_code}: {e.response.text[:300]}"
    except Exception as e:
        return False, str(e)

# ── EVENT HELPERS
def _event_ts(e: dict) -> int:
    return int(e.get("startTime") or e.get("date") or 0)

def _is_kara(e: dict) -> bool:
    return any(kw in (e.get("title") or "").lower() for kw in KARA_KEYWORDS)

def _weekday_info(ts: int) -> tuple:
    try:
        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        wd = dt.strftime("%A")
        em = next((e for e,l in zip(DAY_EMOJI,DAY_LABELS) if l.lower()==wd.lower()), "📅")
        return em,wd
    except: return "📅","Unknown"

def make_day_info(events: list) -> dict:
    return {i: _weekday_info(_event_ts(e)) for i,e in enumerate(events)}

def make_dynamic_day_map(day_info: dict) -> dict:
    dm: dict = {}
    for idx,(em,wd) in day_info.items():
        for alias in [wd.lower(), wd.lower()[:3]]:
            dm.setdefault(alias,[]); 
            if idx not in dm[alias]: dm[alias].append(idx)
    for i in range(5): dm[str(i)] = [i]
    return dm

def _event_label(e: dict) -> str:
    ts = _event_ts(e)
    try:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        wd,date,t = dt.strftime("%A"),dt.strftime("%d %b %Y"),dt.strftime("%H:%M")
    except: wd=date=t="?"
    em    = next((e for e,l in zip(DAY_EMOJI,DAY_LABELS) if l.lower()==wd.lower()), "📅")
    title = e.get("title") or "(no title)"
    n     = len(e.get("signUps") or e.get("signups") or [])
    return f"{em} {wd}  {date} {t} UTC  —  {title}" + (f"  ·  {n} sign-ups" if n else "")

def filter_events(events: list, show_all: bool) -> list:
    if not show_all:
        now = datetime.now(tz=timezone.utc)
        p,f = (now-timedelta(days=14)).timestamp(),(now+timedelta(days=30)).timestamp()
        events = [e for e in events if p <= _event_ts(e) <= f]
    kara  = sorted([e for e in events if _is_kara(e)],     key=_event_ts, reverse=True)
    other = sorted([e for e in events if not _is_kara(e)], key=_event_ts, reverse=True)
    return kara+other

# ── PARSING
def _extract_role(s: dict) -> str:
    for f in ["roleName","entryType","role","roleType","signUpRole","class_role","type"]:  # roleName most reliable in real RH events
        raw = s.get(f)
        if raw is None: continue
        r = ROLE_NORM.get(str(raw).lower().strip(),"")
        if r: return r
    spec = str(s.get("specName") or s.get("spec") or "").lower().strip()
    return SPEC_ROLE_FALLBACK.get(spec,"DPS")

def parse_signups(event_data: dict, day_idx: int, strict: bool, role_overrides: dict) -> list:
    statuses = STRICT_CONFIRMED if strict else LOOSE_CONFIRMED
    signups  = event_data.get("signUps") or event_data.get("signups") or event_data.get("players") or []
    players  = []
    for s in signups:
        status = str(s.get("status","")).lower().strip()
        if status in INVALID_STATUSES or status not in statuses: continue
        cls = str(s.get("className") or s.get("class") or "").lower().strip()
        if not cls or cls not in VALID_WOW_CLASSES: continue
        if str(s.get("entryType") or s.get("role") or "").lower().strip() in INVALID_STATUSES: continue
        uid  = str(s.get("userId") or s.get("id") or s.get("discordId") or s.get("name") or "")
        name = s.get("name") or s.get("displayName") or s.get("characterName") or "Unknown"
        spec = str(s.get("specName") or s.get("spec") or "").strip()
        role = _extract_role(s)
        ov   = role_overrides.get(name.lower().strip())
        if ov: role = ov
        if cls == "tank":
            real_cls = RAIDHELPER_TANK_SPEC_TO_CLASS.get(spec.lower().strip())
            if real_cls: cls = real_cls

        players.append(Player(user_id=uid or name, name=name, class_name=cls,
                               spec=spec, role=role, avail_days=[day_idx]))
    return players

# ── CONFIG PARSERS
def parse_fixed(raw: str, day_map: dict | None = None) -> dict:
    if day_map is None:
        day_map = {"sunday":[0],"monday":[1],"tuesday":[2],
                   "sun":[0],"mon":[1],"tue":[2],"0":[0],"1":[1],"2":[2]}
    result: dict = {}
    for line in raw.strip().splitlines():
        if "=" not in line: continue
        name,_,day = line.partition("=")
        name,day   = name.strip().lower(), day.strip().lower()
        if name and day in day_map: result[name] = day_map[day][0]
    return result

def parse_role_overrides(raw: str) -> dict:
    valid = {"tank":"Tank","healer":"Healer","heal":"Healer","dps":"DPS"}
    result: dict = {}
    for line in raw.strip().splitlines():
        if "=" not in line: continue
        name,_,role = line.partition("=")
        name,role   = name.strip().lower(), role.strip().lower()
        if name and role in valid: result[name] = valid[role]
    return result

def parse_buddies(raw: str) -> list:
    groups = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        members = {m.strip().lower() for m in line.split(",") if m.strip()}
        if len(members) >= 2: groups.append(members)
    return groups

def parse_avoid_pairings(raw: str) -> list:
    pairs = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=!" not in line: continue
        a,_,b = line.partition("=!")
        a,b   = a.strip().lower(), b.strip().lower()
        if a and b: pairs.append({a,b})
    return pairs

def parse_buddy_char(raw: str) -> dict:
    """
    Format: Name=Class  →  {name_lower: class_lower}
    For buddy matching only: when this player has multiple chars in the pool,
    only the specified class is included in buddy group logic.
    ALL chars can still raid — this only affects buddy day-restriction.
    """
    result: dict = {}
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, cls = line.partition("=")
        name = name.strip().lower()
        cls  = cls.strip().lower()
        if name and cls:
            result[name] = cls
    return result


# ── ALGORITHM
def _avoid_conflict(player: Player, group: list, avoid_pairs: list) -> bool:
    names = {p.name_lower for p in group}
    for pair in avoid_pairs:
        if player.name_lower in pair and (pair - {player.name_lower}) & names:
            return True
    return False

def build_all_raids(players_by_day: dict, fixed_assignments: dict, buddy_groups: list,
                    day_info: dict | None = None, avoid_pairs: list | None = None,
                    parse_group_label: str = "", parse_boost: int = 0,
                    buddy_char: dict | None = None) -> dict:
    if day_info is None:
        day_info = {i:(DAY_EMOJI[i] if i<3 else "📅", DAY_LABELS[i] if i<3 else f"Day {i}") for i in range(3)}
    if avoid_pairs is None: avoid_pairs = []
    if buddy_char is None:  buddy_char  = {}

    seen: dict = {}
    for day_idx in sorted(players_by_day):
        for p in players_by_day[day_idx]:
            # Key = (userId, class) — same person with different class on different
            # days is treated as a separate entry (they're bringing an alt).
            # Same person + same class on multiple days → merge into avail_days.
            key = (p.user_id.lower(), p.class_name.lower())
            if key not in seen:
                p.assigned=False; p.group_key=""; p.subgroup=1; seen[key]=p
            elif day_idx not in seen[key].avail_days:
                seen[key].avail_days.append(day_idx)

    all_players = list(seen.values())
    for p in all_players: p.assigned=False; p.group_key=""; p.subgroup=1

    # Fixed assignments still match by name (case-insensitive)
    for name_lower,forced_day in fixed_assignments.items():
        for p in all_players:
            if p.name_lower == name_lower:
                p.avail_days = [forced_day]

    for bset in buddy_groups:
        # For each name in the buddy set, pick the right Player entry:
        # - If buddy_char specifies a class for this player → use only that char
        # - Otherwise → use any char (first found, as before)
        # Other chars of the same player are left untouched and raid independently.
        bps = []
        for name in bset:
            candidates = [p for p in all_players if p.name_lower == name]
            if not candidates:
                continue
            required_cls = buddy_char.get(name)
            if required_cls:
                # Use the char with matching class for buddy constraint
                match = next((p for p in candidates if p.class_name.lower() == required_cls), None)
                if match:
                    bps.append(match)
                # Other chars of this player are NOT added to bps → no constraint on them
            else:
                # No char preference → add all chars (original behaviour)
                bps.extend(candidates)
        if len(bps) < 2: continue
        common = set(bps[0].avail_days)
        for bp in bps[1:]: common &= set(bp.avail_days)
        if common:
            for bp in bps: bp.avail_days = sorted(common)

    all_day_idxs = sorted(players_by_day.keys())
    raw_count    = {d:len(v) for d,v in players_by_day.items()}
    excl_count: dict = defaultdict(int)
    for p in all_players:
        if len(p.avail_days)==1: excl_count[p.avail_days[0]] += 1

    # Raid slot logic:
    # - Goal: always fill up to 3 raids total across all selected events
    # - Each event starts with 1 slot if ≥10 sign-ups, 0 if fewer
    # - A/B split (2 slots on one day) is always allowed if ≥18 exclusive sign-ups
    # - The boost loop fills remaining slots on the busiest day until total = 3
    # - Max 3 raids ever (max 2 slots per day)
    MAX_RAIDS = 3

    raids_per_day: dict = {}
    for d in all_day_idxs:
        excl = excl_count.get(d, 0)
        # Always create at least 1 slot per selected event — even with <10 sign-ups.
        # Exclusive players must always have a home; leftovers fill in via Pass 3.
        # A/B split only when ≥18 exclusive sign-ups on that day.
        raids_per_day[d] = 2 if excl >= 18 else 1

    total  = sum(raids_per_day.values())
    active = sorted([d for d in all_day_idxs if raw_count.get(d, 0) >= 10],
                    key=lambda d: -raw_count.get(d, 0))
    while total < MAX_RAIDS and active:
        bumped = False
        for d in active:
            if total >= MAX_RAIDS: break
            if raids_per_day.get(d, 0) < 2 and raw_count.get(d, 0) >= 10:
                raids_per_day[d] += 1; total += 1; bumped = True
        if not bumped: break

    slot_labels: list[tuple] = []
    for day_idx in all_day_idxs:
        n = raids_per_day.get(day_idx,0)
        em,dn = day_info.get(day_idx,("📅",f"Day {day_idx}"))
        for slot in range(1, n+1):
            lbl = f"{em} {dn}" if n==1 else f"{em} {dn} {'AB'[slot-1]}"
            slot_labels.append((day_idx,lbl))

    results: dict = {lbl:[] for _,lbl in slot_labels}
    results["🪑 Bench"] = []

    # Pass 1: Exclusive players
    for day_idx,label in slot_labels:
        pool = [p for p in all_players
                if len(p.avail_days)==1 and p.avail_days[0]==day_idx and not p.assigned]
        fixed_here = [p for p in pool
                      if p.name_lower in fixed_assignments and fixed_assignments[p.name_lower]==day_idx]
        others = [p for p in pool if p not in fixed_here]

        def rq(role):
            return [p for p in fixed_here if p.role==role] + [p for p in others if p.role==role]

        group = results[label]
        for p in rq("Tank"):
            if sum(1 for x in group if x.role=="Tank") >= TARGET["Tank"]: break
            if _avoid_conflict(p,group,avoid_pairs): continue
            group.append(p); p.assigned=True; p.group_key=label
        for p in rq("Healer"):
            if p.assigned: continue
            if sum(1 for x in group if x.role=="Healer") >= TARGET["Healer"]: break
            if _avoid_conflict(p,group,avoid_pairs): continue
            group.append(p); p.assigned=True; p.group_key=label
        dps_need = RAID_SIZE-len(group); done=0
        for p in rq("DPS"):
            if p.assigned or done>=dps_need: break
            if _avoid_conflict(p,group,avoid_pairs): continue
            group.append(p); p.assigned=True; p.group_key=label; done+=1

    # Pass 2: Flex players — equity-aware, score-guided
    # Priority: 1. role need  2. equity (low-scoring groups attract players)  3. score gain
    # This keeps all groups fair while still optimising buffs.
    flexible = [p for p in all_players if not p.assigned and len(p.avail_days)>1]
    flexible.sort(key=lambda p: (
        0 if p.name_lower in fixed_assignments else 1,
        0 if p.role=="Tank" else (1 if p.role=="Healer" else 2),
    ))

    def _role_need(role, label):
        have = sum(1 for x in results[label] if x.role==role)
        return max(0, TARGET[role]-have)
    def _free(label): return RAID_SIZE-len(results[label])
    def _cur_score(label): return group_score(results[label]) if results[label] else 0

    for p in flexible:
        if p.assigned: continue
        cands = [(di,lbl) for di,lbl in slot_labels
                 if di in p.avail_days and _free(lbl)>0
                 and not _avoid_conflict(p,results[lbl],avoid_pairs)]
        if not cands:
            cands = [(di,lbl) for di,lbl in slot_labels
                     if di in p.avail_days and _free(lbl)>0]
        if not cands: continue

        live_scores = [_cur_score(lbl) for _,lbl in slot_labels]
        avg = sum(live_scores)/len(live_scores) if live_scores else 0

        def _key(entry):
            _, lbl = entry
            rn = _role_need(p.role, lbl)
            sg = score_gain(p, results[lbl])
            eq = max(0, avg - _cur_score(lbl)) * 0.6
            fr = _free(lbl)

            if parse_group_label and lbl == parse_group_label and rn > 0:
                # Parse group gets absolute priority when it still needs this role.
                # Tier 0 = parse group (always beats other groups in same tier).
                # Within tier 0: stronger boost → higher score pull.
                return (0, -(sg + eq + parse_boost), -fr, entry[0])
            else:
                # Normal groups: tier 1, sorted by role need then score.
                return (1, -rn, -(sg + eq), -fr)

        cands.sort(key=_key)
        _, best_lbl = cands[0]
        results[best_lbl].append(p); p.assigned=True; p.group_key=best_lbl

    # Pass 3: rescue — don't bench anyone who could fill an incomplete group
    for p in [x for x in all_players if not x.assigned]:
        rescue = [(di,lbl) for di,lbl in slot_labels
                  if di in p.avail_days and _free(lbl)>0]
        if rescue:
            rescue.sort(key=lambda e: (-_role_need(p.role,e[1]), -_free(e[1])))
            _, best = rescue[0]
            results[best].append(p); p.assigned=True; p.group_key=best

    # Subgroup assignment
    for lbl,grp in results.items():
        if lbl != "🪑 Bench":
            results[lbl] = assign_subgroups(grp)

    # Bench
    for p in all_players:
        if not p.assigned:
            p.group_key="🪑 Bench"; results["🪑 Bench"].append(p)

    return results

# ── DISCORD EXPORT
def discord_block(label: str, players: list) -> str:
    # Determine SG labels based on tank type
    tanks     = [p for p in players if getattr(p,"role","DPS") == "Tank"]
    pala_tank = any(_is_prot_pala(p) for p in tanks) if tanks else True
    sg_labels = {
        1: ("🔷", "Subgroup 1 — Casters" if pala_tank else "🔶 Subgroup 1 — Melee"),
        2: ("🔶", "Subgroup 2 — Melee"   if pala_tank else "🔷 Subgroup 2 — Casters"),
    }
    lines = [f"**{label}**  [{len(players)}/10]",""]
    for sg in [1, 2]:
        sgt = [p for p in players if getattr(p,"subgroup",1)==sg]
        if not sgt: continue
        em, sg_lbl = sg_labels[sg]
        lines.append(f"**{em} {sg_lbl}**")
        for role in ["Tank","Healer","DPS"]:
            for p in [x for x in sgt if x.role==role]:
                cls_em = CLASS_EMOJI.get(p.class_name.lower(),"")
                spec   = p.spec or p.class_name.title()
                lines.append(f"  {ROLE_EMOJI_MAP[role]} {cls_em} {p.name} — {spec}")
        lines.append("")
    return "\n".join(lines).strip()

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
    linear-gradient(180deg,#1c1005 0%,#07070f 100%);border-bottom:2px solid #6b4c1e;
    padding:2.2rem 2rem 1.8rem;text-align:center;margin-bottom:1.5rem;}
.kh-title{font-family:'Cinzel',serif;font-size:clamp(1.7rem,4.5vw,3rem);font-weight:900;
    color:#f0c060;text-shadow:0 0 40px rgba(240,160,40,.55),0 2px 4px rgba(0,0,0,.9);letter-spacing:.09em;}
.kh-sub{font-family:'Crimson Pro',serif;font-size:.95rem;color:#8a6a38;letter-spacing:.18em;text-transform:uppercase;margin-top:.3rem;}
.gold-div{height:1px;max-width:480px;margin:.6rem auto;background:linear-gradient(90deg,transparent,#c9a84c 30%,#f0c060 50%,#c9a84c 70%,transparent);}
.sh{font-family:'Cinzel',serif;font-size:1rem;font-weight:600;color:#c9a84c;margin:.6rem 0 .3rem;display:flex;align-items:center;gap:.35rem;}
.ib{background:rgba(201,168,76,.07);border-left:3px solid #c9a84c;border-radius:0 6px 6px 0;padding:.55rem .85rem;font-family:'Crimson Pro',serif;font-size:.9rem;color:#d4aa55;margin-bottom:.8rem;}
.wb{background:rgba(200,60,30,.07);border-left:3px solid #c04020;border-radius:0 6px 6px 0;padding:.55rem .85rem;font-family:'Crimson Pro',serif;font-size:.9rem;color:#b05030;margin-bottom:.8rem;}
.sb{background:rgba(40,180,60,.07);border-left:3px solid #30a040;border-radius:0 6px 6px 0;padding:.55rem .85rem;font-family:'Crimson Pro',serif;font-size:.9rem;color:#50a060;margin-bottom:.8rem;}
.chip{font-family:'Cinzel',serif;font-size:.67rem;padding:.1rem .48rem;border-radius:20px;border:1px solid;font-weight:600;}
.chips{display:flex;gap:.35rem;flex-wrap:wrap;margin-bottom:.55rem;}
.stButton>button{background:linear-gradient(135deg,#3a2200,#5a3800) !important;border:1px solid #c9a84c !important;color:#f0c060 !important;font-family:'Cinzel',serif !important;font-weight:600 !important;letter-spacing:.06em !important;padding:.5rem 1.4rem !important;border-radius:4px !important;font-size:.78rem !important;text-transform:uppercase !important;transition:all .18s !important;}
.stButton>button:hover{background:linear-gradient(135deg,#5a3800,#7a5000) !important;box-shadow:0 0 18px rgba(201,168,76,.3) !important;}
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea{background:#0c0c18 !important;border:1px solid #2a2010 !important;color:#a09060 !important;font-family:'Crimson Pro',serif !important;border-radius:5px !important;}
[data-testid="stTextInput"] input:focus,[data-testid="stTextArea"] textarea:focus{border-color:#c9a84c !important;box-shadow:0 0 0 2px rgba(201,168,76,.18) !important;}
section[data-testid="stSidebar"]{background:#0a0a14 !important;border-right:1px solid #1e1810 !important;}
.stTabs [data-baseweb="tab-list"]{background:transparent !important;gap:.35rem;}
.stTabs [data-baseweb="tab"]{background:#0e0e1c !important;border:1px solid #2a2010 !important;border-radius:4px !important;color:#6a5a38 !important;font-family:'Cinzel',serif !important;font-size:.73rem !important;padding:.32rem .75rem !important;}
.stTabs [aria-selected="true"]{background:linear-gradient(135deg,#281600,#382400) !important;border-color:#c9a84c !important;color:#f0c060 !important;}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="kh">
  <div class="kh-title">🏰 KARAZHAN RAID PLANNER</div>
  <div class="gold-div"></div>
  <div class="kh-sub">R2 — Make Raids Great Again &nbsp;·&nbsp; TBC Classic Anniversary</div>
</div>
""", unsafe_allow_html=True)

try:
    server_id = st.secrets.get("RAID_HELPER_SERVER_ID","")
    api_key   = st.secrets.get("RAID_HELPER_API_KEY","")
except Exception:
    server_id = ""; api_key = ""

# ── SIDEBAR
with st.sidebar:
    # ── General
    st.markdown('<div class="sh">⚙️ Settings</div>', unsafe_allow_html=True)
    strict_mode = st.checkbox(
        "Confirmed sign-ups only", value=True,
        help="When ON: only players with status primary/confirmed/spec are included.\n"
             "When OFF: also includes late, tentative and standby sign-ups."
    )

    # ── Parse Group
    st.markdown("---")
    st.markdown('<div class="sh">🏆 Parse Group</div>', unsafe_allow_html=True)
    enable_parse_group = st.checkbox("Activate Parse Group", value=False, key="enable_parse_group")
    if enable_parse_group:
        known_keys = [k for k in st.session_state.get("results",{}) if "Bench" not in k]
        if known_keys:
            st.selectbox("Which group?", options=known_keys, key="parse_group_sel")
            st.slider("Boost strength", min_value=50, max_value=300, value=150, step=50,
                      key="parse_boost_val",
                      help="50 = subtle  ·  150 = noticeable  ·  300 = strong")
            st.markdown("""<div style='font-family:"Crimson Pro",serif;font-size:.75rem;color:#5a4a28'>
            ↑ Change settings, then click <b>Apply Parse Group</b> below.</div>""",
            unsafe_allow_html=True)
        else:
            st.caption("Calculate first, then select a group here.")



    # ── Role Overrides + Fixed + Buddies + Avoid (collapsed by default)
    st.markdown("---")
    with st.expander("⚙️ Composition Rules", expanded=False):
        override_raw = st.text_area("🎭 Role Overrides", value=DEFAULT_OVERRIDES, height=65,
                     key="override_input",
                     help="Format: Name=Role\nForce a player into a specific role regardless of their Raid-Helper sign-up.\nRoles: Tank / Healer / DPS\nExample: Stone=Tank")
        fixed_raw = st.text_area("📌 Fixed Days", value=DEFAULT_FIXED, height=65,
                     key="fixed_input",
                     help="Format: Name=Day\nLock a player to a specific raid day.\nDays: Sunday / Monday / Tuesday / Friday etc.\nExample: Stone=Monday")
        buddy_raw = st.text_area("👥 Buddy Groups", value=DEFAULT_BUDDIES, height=110,
                     key="buddy_input",
                     help="One group per line, names comma-separated.\nBuddies are kept in the same raid if possible (soft preference — not guaranteed).\nExample: Miroga,Terry,Vowly")
        buddy_char_raw = st.text_area("🧬 Buddy Char", value=DEFAULT_BUDDY_CHAR, height=65,
                     key="buddy_char_input",
                     help="Format: Name=Class\nFor players with multiple alts: only this class counts for buddy logic.\nThe other chars still raid freely.\nExample: Rock=Paladin")

    with st.expander("🚫 Avoid Pairings", expanded=False):
        avoid_raw = st.text_area("🚫 Avoid Pairings", value=DEFAULT_AVOID, height=80,
                                  key="avoid_input",
                                  help="Format: PlayerA=!PlayerB\nThese two players will never be placed in the same group.\nIf unavoidable, the rule is relaxed automatically.\nExample: Vowly=!Vapecum")


    st.markdown("---")
    st.markdown(f"""<div style='font-family:"Crimson Pro",serif;font-size:.72rem;color:#3a2e18;text-align:center;margin-top:.5rem'>
    {APP_VERSION}
    </div>""", unsafe_allow_html=True)

role_overrides    = parse_role_overrides(override_raw)
fixed_assignments = parse_fixed(fixed_raw)
buddy_groups      = parse_buddies(buddy_raw)
avoid_pairs       = parse_avoid_pairings(avoid_raw)
buddy_char        = parse_buddy_char(buddy_char_raw)

# ── STEP 1
st.markdown('<div class="sh">📅 Step 1 — Select Your Karazhan Events</div>', unsafe_allow_html=True)

with st.spinner("Loading events..."):
    raw_events = fetch_server_events(server_id, api_key)
if not raw_events:
    st.markdown('<div class="wb">❌ No events found. Check your <code>secrets.toml</code>.</div>', unsafe_allow_html=True)
    st.stop()
_,col_t = st.columns([3,1])
with col_t:
    show_all = st.checkbox("Show all events", value=False,
                            help="By default only events from the last 14 days and next 30 days are shown.")
available_events = filter_events(raw_events, show_all)
if not available_events:
    st.markdown('<div class="wb">⚠️ No recent events. Enable "Show all events".</div>', unsafe_allow_html=True)
    st.stop()

event_options = {_event_label(e):e for e in available_events}
event_labels  = list(event_options.keys())
kara_labels   = [l for l in event_labels if any(kw in l.lower() for kw in KARA_KEYWORDS)]
default_sel   = kara_labels[:3] if len(kara_labels)>=3 else event_labels[:3]

st.markdown("""<div class="ib">🏰 <b>Kara events listed first.</b>
Select <b>2–4 events</b> in chronological order. Two events on the same day → auto A/B split.</div>""", unsafe_allow_html=True)

selected_labels = st.multiselect("Choose events (2–4, earliest first)",
    options=event_labels, default=default_sel, max_selections=4)

if len(selected_labels) < 2:
    st.markdown(f'<div class="ib">ℹ️ Select at least <b>2 events</b> (currently {len(selected_labels)}).</div>', unsafe_allow_html=True)
    st.stop()

selected_events = [event_options[l] for l in selected_labels]

if role_overrides:
    st.markdown('<div class="ib">🎭 Overrides: '+" · ".join(f"<b>{n.title()}</b>→{r}" for n,r in role_overrides.items())+"</div>", unsafe_allow_html=True)
if fixed_assignments:
    _di = make_day_info(selected_events)
    _dn = {i:wd for i,(_,wd) in _di.items()}
    st.markdown('<div class="ib">📌 Fixed: '+" · ".join(f"<b>{n.title()}</b>→{_dn.get(d,f'Day {d}')}" for n,d in fixed_assignments.items())+"</div>", unsafe_allow_html=True)
if avoid_pairs:
    st.markdown('<div class="ib">🚫 Avoid Pairings: '+" · ".join(" ≠ ".join(p.title() for p in sorted(pair)) for pair in avoid_pairs)+"</div>", unsafe_allow_html=True)
if buddy_groups:
    buddy_str = " · ".join(", ".join(n.title() for n in sorted(g)) for g in buddy_groups)
    st.markdown(f'<div class="ib">👥 Buddy Groups: {buddy_str}</div>', unsafe_allow_html=True)

# ── STEP 2
st.markdown('<div class="sh">⚔️ Step 2 — Build Compositions</div>', unsafe_allow_html=True)

if st.button("⚔️  Calculate Raid Compositions", width='stretch'):
    players_by_day: dict = {}
    day_info    = make_day_info(selected_events)
    dynamic_map = make_dynamic_day_map(day_info)
    dyn_fixed   = parse_fixed(fixed_raw, dynamic_map)

    with st.spinner("Fetching sign-up data..."):
        for day_idx,event in enumerate(selected_events):
            event_data = fetch_event_detail(str(event.get("id","")), api_key)
            if event_data:
                raw_su = event_data.get("signUps") or event_data.get("signups") or event_data.get("players") or []
                em,wd  = day_info.get(day_idx,("📅",f"Day {day_idx}"))
                plist  = parse_signups(event_data, day_idx, strict_mode, role_overrides)
                if plist: players_by_day[day_idx] = plist

    if not players_by_day:
        st.markdown('<div class="wb">❌ No confirmed sign-ups found.</div>', unsafe_allow_html=True)
        st.stop()

    _pg_label = st.session_state.get("parse_group_sel", "") if st.session_state.get("enable_parse_group") else ""
    _pg_boost = st.session_state.get("parse_boost_val", 0) if st.session_state.get("enable_parse_group") else 0
    results   = build_all_raids(players_by_day, dyn_fixed, buddy_groups, day_info, avoid_pairs, _pg_label, _pg_boost)
    # Store everything needed for live-rebuild when parse settings change
    st.session_state.update({
        "results":         results,
        "selected_events": selected_events,
        "api_key_used":    api_key,
        "day_info":        day_info,
        # Rebuild ingredients (no re-fetch needed)
        "_players_by_day": players_by_day,
        "_dyn_fixed":      dyn_fixed,
        "_buddy_groups":   buddy_groups,
        "_buddy_char":     buddy_char,
        "_avoid_pairs":    avoid_pairs,
        "_fixed_raw":      fixed_raw,
    })
    st.rerun()

# ── PARSE GROUP APPLY (shown when results exist + parse group active)
if "results" in st.session_state and st.session_state.get("enable_parse_group"):
    _pg_sel   = st.session_state.get("parse_group_sel", "")
    _pg_boost = st.session_state.get("parse_boost_val", 150)
    known_keys = [k for k in st.session_state["results"] if "Bench" not in k]

    if _pg_sel and _pg_sel in known_keys and "_players_by_day" in st.session_state:
        col_info, col_btn = st.columns([3, 1])
        with col_info:
            st.markdown(
                f'<div class="ib">🏆 Parse Group: <b>{_pg_sel}</b> &nbsp;·&nbsp; ' +
                f'Boost: <b>{_pg_boost}</b></div>',
                unsafe_allow_html=True,
            )
        with col_btn:
            if st.button("🔄 Apply", width='stretch',
                         help="Recalculate with current Parse Group settings"):
                _new = build_all_raids(
                    st.session_state["_players_by_day"],
                    st.session_state["_dyn_fixed"],
                    st.session_state["_buddy_groups"],
                    st.session_state["day_info"],
                    st.session_state["_avoid_pairs"],
                    _pg_sel,
                    _pg_boost,
                    st.session_state.get("_buddy_char",{}),
                )
                st.session_state["results"] = _new
                st.rerun()

# ── STEP 3
if "results" not in st.session_state:
    st.markdown("""<div style='text-align:center;padding:5rem 2rem;color:#2e2410'>
      <div style='font-size:3.5rem;margin-bottom:.8rem'>🏰</div>
      <div style='font-family:"Cinzel",serif;font-size:1.15rem;color:#5a4a22'>
        Select events above and click <em>Calculate Raid Compositions</em></div>
    </div>""", unsafe_allow_html=True)
    st.stop()

results      = st.session_state["results"]
sel_events   = st.session_state["selected_events"]
api_key_sess = st.session_state.get("api_key_used", api_key)
di           = st.session_state.get("day_info", {})

raid_keys = [k for k in results if "Bench" not in k]
bench_key = "🪑 Bench"
n_placed  = sum(len(results[k]) for k in raid_keys)
n_bench   = len(results.get(bench_key,[]))

st.markdown(f"""<div class="ib">⚔️ <b>{len(raid_keys)} Raids</b> built &nbsp;·&nbsp;
👥 <b>{n_placed}</b> assigned &nbsp;·&nbsp; 🪑 <b>{n_bench}</b> on bench</div>""", unsafe_allow_html=True)


st.markdown('<div class="sh">🃏 Step 3 — Review & Edit Compositions</div>', unsafe_allow_html=True)
st.markdown('<div class="ib">💡 Change <b>Group</b> to move a player. Change <b>Role</b> or <b>SG</b> (subgroup) to adjust. '
            '<b>✅ Confirmed Days</b> shows only real confirmed days.</div>', unsafe_allow_html=True)

all_rows = []
for label in raid_keys+[bench_key]:
    for p in results.get(label,[]):
        conf = ", ".join(f"{di.get(d,('📅',f'Day {d}'))[0]} {di.get(d,('📅',f'Day {d}'))[1]}" for d in sorted(p.avail_days))
        all_rows.append({"Name":p.name,"Class":p.class_name.title(),"Spec":p.spec or "—",
                          "Role":p.role,"Group":label,"SG":p.subgroup,"✅ Confirmed Days":conf})

flat_df       = pd.DataFrame(all_rows) if all_rows else pd.DataFrame(columns=["Name","Class","Spec","Role","Group","SG","✅ Confirmed Days"])
group_options = raid_keys+[bench_key]

edited_df = st.data_editor(flat_df, width='stretch', hide_index=True, num_rows="fixed",
    column_config={
        "Name":     st.column_config.TextColumn("Name",      disabled=True, width="medium"),
        "Class":    st.column_config.TextColumn("Class",     disabled=True, width="small"),
        "Spec":     st.column_config.TextColumn("Spec",      disabled=True, width="medium"),
        "Role":     st.column_config.SelectboxColumn("Role", options=["Tank","Healer","DPS"], width="small"),
        "Group":    st.column_config.SelectboxColumn("Group", options=group_options, width="large"),
        "SG":       st.column_config.SelectboxColumn("SG",   options=[1,2], width="small",
                        help="1 = Caster subgroup, 2 = Melee subgroup"),
        "✅ Confirmed Days": st.column_config.TextColumn("✅ Confirmed Days", disabled=True, width="medium"),
    }, key="player_editor")

edited_groups: dict = {k:[] for k in group_options}
for _,row in edited_df.iterrows():
    g = row.get("Group",bench_key)
    if g not in edited_groups: g = bench_key
    edited_groups[g].append(row.to_dict())

# ── Validation + Score
st.markdown('<div class="sh">🔍 Live Validation</div>', unsafe_allow_html=True)
all_valid     = True
val_cols      = st.columns(max(len(raid_keys),1))
_active_parse = st.session_state.get("enable_parse_group", False)
_parse_label  = st.session_state.get("parse_group_sel", "") if _active_parse else ""
_parse_boost  = st.session_state.get("parse_boost_val", 0)  if _active_parse else 0

for ci,label in enumerate(raid_keys):
    g     = edited_groups.get(label,[])
    tanks = sum(1 for p in g if p.get("Role")=="Tank")
    heals = sum(1 for p in g if p.get("Role")=="Healer")
    dps   = sum(1 for p in g if p.get("Role")=="DPS")
    total = len(g)
    valid = tanks==1 and heals==2 and dps==7 and total==10
    if not valid: all_valid = False

    orig     = results.get(label,[])
    sc       = group_score(orig) if orig else 0
    sl,sc_col = score_label(sc)
    o_cls    = [p.class_name.lower() for p in orig]
    o_specs  = [(p.class_name.lower(), p.spec.lower()) for p in orig]
    has_shaman  = "shaman"  in o_cls
    has_pal     = "paladin" in o_cls
    has_druid   = "druid"   in o_cls
    has_mage    = "mage"    in o_cls
    has_wl      = "warlock" in o_cls
    has_spr     = any(c=="priest" and "shadow" in s for c,s in o_specs)
    is_parse = label == _parse_label

    def _c(val,need,icon):
        col="#50c050" if val==need else "#e06040"
        return f'<span class="chip" style="color:{col};border-color:{col}30;background:{col}18">{icon} {val}/{need}</span>'

    with val_cols[ci % len(val_cols)]:
        bc       = "#30a040" if valid else "#c04020"
        pg_badge = '<span style="font-size:.65rem;color:#c9a84c;font-family:Cinzel,serif">🏆 Parse Group &nbsp;</span>' if is_parse else ""
        def _cls_chip(present, label, critical=False):
            if present:
                c = "#50c050"
                return f'<span class="chip" style="color:{c};border-color:{c}30;background:{c}18">✓ {label}</span> '
            elif critical:
                c = "#e06040"
                return f'<span class="chip" style="color:{c};border-color:{c}30;background:{c}18">✗ {label}</span> '
            else:
                c = "#5a4a28"
                return f'<span class="chip" style="color:{c};border-color:{c}30;background:{c}18">✗ {label}</span> '

        # Row 2: class buffs + SPriest bonus
        warn  = _cls_chip(has_shaman, "Shaman", critical=True)
        warn += _cls_chip(has_pal,    "Paladin")
        warn += _cls_chip(has_druid,  "Druid")
        warn += _cls_chip(has_mage,   "Mage")
        warn += _cls_chip(has_wl,     "Warlock")
        warn += '<span style="color:#3a2e18;padding:0 .3rem">|</span>'
        warn += _cls_chip(has_spr,    "SPriest")
        st.markdown(f"""
        <div style="background:#0d0d18;border:1px solid {bc};border-radius:6px;padding:.65rem .8rem;margin-bottom:.5rem">
          <div style="font-family:'Cinzel',serif;font-size:.88rem;color:#f0c060;margin-bottom:.35rem">{pg_badge}{'✅' if valid else '⚠️'} {label}</div>
          <div class="chips">{_c(tanks,1,'🛡️')}{_c(heals,2,'💚')}{_c(dps,7,'⚔️')}
            <span class="chip" style="color:#a09060;border-color:#4a3a2030;background:#4a3a2018">📊 {total}/10</span>
            <span class="chip" style="color:{sc_col};border-color:{sc_col}30;background:{sc_col}18">{sl} {sc}pts</span>
          </div>
          {f'<div class="chips" style="margin-top:.2rem">{warn}</div>' if warn else ''}
        </div>""", unsafe_allow_html=True)

if not all_valid:
    _issues = []
    for _lbl in raid_keys:
        _g = edited_groups.get(_lbl, [])
        _t = sum(1 for p in _g if p.get("Role")=="Tank")
        _h = sum(1 for p in _g if p.get("Role")=="Healer")
        _d = sum(1 for p in _g if p.get("Role")=="DPS")
        _parts = []
        if _t != 1: _parts.append(f"{_t}/1T")
        if _h != 2: _parts.append(f"{_h}/2H")
        if _d != 7: _parts.append(f"{_d}/7D")
        if _parts: _issues.append(f"<b>{_lbl}</b>: {', '.join(_parts)}")
    st.markdown(f'<div class="wb">⚠️ Composition issues — {" · ".join(_issues)}</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="sb">✅ All groups valid <b>1-2-7</b>!</div>', unsafe_allow_html=True)

# Buddy unmatched warning — check edited_groups so manual moves are reflected
if buddy_groups:
    # Build name→group map from edited_groups (reflects manual changes)
    all_assigned_edited = {}
    for lbl in raid_keys:
        for row in edited_groups.get(lbl, []):
            all_assigned_edited[row.get("Name","").lower().strip()] = lbl
    unmatched_buddies = []
    for bset in buddy_groups:
        assigned_groups = {all_assigned_edited.get(n) for n in bset if n in all_assigned_edited}
        assigned_groups.discard(None)
        if len(assigned_groups) > 1:
            unmatched_buddies.append(", ".join(sorted(bset)).title())
    if unmatched_buddies:
        pairs_str = " · ".join(f"<b>{b}</b>" for b in unmatched_buddies)
        st.markdown(f'<div class="ib" style="color:#d4aa55">👥 Buddy groups split: {pairs_str}</div>', unsafe_allow_html=True)

# Balance indicator
all_scores = [group_score(results.get(k,[])) for k in raid_keys if results.get(k)]
if len(all_scores) >= 2:
    diff = max(all_scores) - min(all_scores)
    if diff < 200:
        st.markdown(f'<div class="sb">⚖️ Well balanced — score spread: {diff} pts</div>', unsafe_allow_html=True)
    elif diff < 400:
        st.markdown(f'<div class="ib" style="color:#d4aa55">⚖️ Reasonably balanced — score spread: {diff} pts</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="wb">⚖️ Score imbalance detected ({diff} pts) — consider manual adjustments</div>', unsafe_allow_html=True)


# ── STEP 4 — Raid Overview + Discord Export
st.markdown('<div class="sh" style="margin-top:1rem">📋 Step 4 — Raid Overview & Discord Export</div>', unsafe_allow_html=True)

def _class_color(cls: str) -> str:
    return CLASS_COLOR.get(cls.lower(), "#888888")

def _role_icon(role: str) -> str:
    return {"Tank":"🛡️","Healer":"💚","DPS":"⚔️"}.get(role,"⚔️")

keys_to_export = raid_keys+([bench_key] if edited_groups.get(bench_key) else [])
if keys_to_export:
    tabs = st.tabs(keys_to_export)
    for tab,label in zip(tabs,keys_to_export):
        with tab:
            if label == bench_key:
                export_players = results.get(label, [])
                # Simple bench list
                if export_players:
                    bench_html = '<div style="display:flex;flex-wrap:wrap;gap:.4rem;margin-top:.5rem">' 
                    for p in export_players:
                        col = _class_color(p.class_name)
                        bench_html += (f'<div style="background:#0d0d18;border:1px solid {col}40;' +
                                       f'border-radius:5px;padding:.3rem .6rem;font-family:Cinzel,serif;' +
                                       f'font-size:.72rem;color:{col}">' +
                                       f'{_role_icon(p.role)} {p.name}</div>')
                    bench_html += '</div>'
                    st.markdown(bench_html, unsafe_allow_html=True)
                else:
                    st.markdown('<div class="sb">✅ No players on bench!</div>', unsafe_allow_html=True)
            else:
                class _EP:
                    def __init__(self, d):
                        self.name       = d.get("Name", "?")
                        self.class_name = d.get("Class", "").lower()
                        self.spec       = d.get("Spec", "—")
                        self.role       = d.get("Role", "DPS")
                        self.subgroup   = int(d.get("SG", 1))
                export_players = [_EP(r) for r in edited_groups.get(label, [])]

                # ── Visual group cards (SG1 | SG2)
                sg1 = [p for p in export_players if p.subgroup == 1]
                sg2 = [p for p in export_players if p.subgroup == 2]

                # Determine labels based on tank type
                tank_p = next((p for p in export_players if p.role=="Tank"), None)
                is_pala_tank = tank_p and tank_p.class_name.lower()=="paladin"
                sg1_title = "🔷 Group 1 — Casters" if is_pala_tank else "🔷 Group 1 — Melee"
                sg2_title = "🔶 Group 2 — Melee"   if is_pala_tank else "🔶 Group 2 — Casters"

                col1, col2 = st.columns(2)
                for col, sg, sg_title in [(col1, sg1, sg1_title), (col2, sg2, sg2_title)]:
                    with col:
                        st.markdown(f'<div style="font-family:Cinzel,serif;font-size:.82rem;color:#c9a84c;margin-bottom:.4rem">{sg_title}</div>', unsafe_allow_html=True)
                        for role in ["Tank","Healer","DPS"]:
                            for p in [x for x in sg if x.role==role]:
                                col_c = _class_color(p.class_name)
                                spec  = p.spec if p.spec and p.spec != "—" else p.class_name.title()
                                # If role was manually changed, fall back to class icon
                                # Always use spec icon — if role was manually changed,
                                # fall back to class icon since spec may no longer match
                                orig_p = next((x for x in results.get(label,[])
                                               if x.name_lower == p.name.lower().strip()), None)
                                role_changed = orig_p and orig_p.role != p.role
                                if role_changed:
                                    icon_url = CLASS_ICON_URL.get(p.class_name.lower(),
                                               f"{ICON_BASE}/class_warrior.jpg")
                                else:
                                    icon_url = spec_icon_url(p.class_name, spec)
                                st.markdown(
                                    f'<div style="display:flex;align-items:center;gap:.5rem;' +
                                    f'background:#0d0d18;border-left:3px solid {col_c};' +
                                    f'border-radius:0 4px 4px 0;padding:.3rem .5rem;' +
                                    f'margin-bottom:.25rem">' +
                                    f'<img src="{icon_url}" style="width:28px;height:28px;border-radius:3px;flex-shrink:0">' +
                                    f'<span style="font-family:Cinzel,serif;font-size:.78rem;color:{col_c};font-weight:600">{p.name}</span>' +
                                    f'<span style="font-size:.7rem">{_role_icon(role)}</span>' +
                                    f'</div>',
                                    unsafe_allow_html=True
                                )

                # ── Discord Export (secondary — collapsible)
                with st.expander("📋 Discord Export", expanded=False):
                    st.code(discord_block(label, export_players), language=None)
                    st.caption("Click the copy icon (top-right) to copy.")

# ── STEP 5 Push
st.markdown('<div class="sh" style="margin-top:1rem">🔄 Step 5 — Sync to Raid-Helper</div>', unsafe_allow_html=True)

st.markdown('<div class="ib">Pushes compositions <b>incl. subgroup assignments</b> to Raid-Helper. Cannot be undone.</div>', unsafe_allow_html=True)
if st.button("🚀  Push Compositions to Raid-Helper", type="primary", width='stretch'):
        st.session_state["push_confirm"] = True

if st.session_state.get("push_confirm"):
        st.warning("⚠️ **Are you sure?** This overwrites all event compositions in Raid-Helper.")
        c1,c2 = st.columns(2)
        with c1:
            if st.button("✅  Yes, push all", width='stretch'):
                st.session_state["push_confirm"] = False
                errors, successes, comp_links = [], [], []
                for i,label in enumerate([k for k in edited_groups if "Bench" not in k]):
                    if i >= len(sel_events): break
                    eid = str(sel_events[i].get("id",""))
                    # Use edited_groups so manual changes are reflected in push
                    pdicts = [{
                                  "name":       r.get("Name", ""),
                                  "class_name": r.get("Class", "").lower(),
                                  "spec":       r.get("Spec", ""),
                                  "subgroup":   int(r.get("SG", 1)),
                              } for r in edited_groups.get(label, [])]
                    ok,msg = push_composition(eid, api_key_sess, pdicts)
                    if ok:
                        successes.append(label)
                        comp_links.append((label, eid))
                    else:
                        errors.append(f"{label}: {msg}")
                if successes:
                    st.markdown(f'<div class="sb">✅ Pushed: {", ".join(successes)}</div>', unsafe_allow_html=True)
                    for lbl, eid in comp_links:
                        comp_url = f"https://raid-helper.dev/comp/{eid}"
                        st.markdown(
                            f'<div class="ib">🔗 <b>{lbl}</b> &nbsp;—&nbsp;' +
                            f'<a href="{comp_url}" target="_blank" ' +
                            f'style="color:#c9a84c;text-decoration:underline">' +
                            f'Open in Raid-Helper Comp Tool →</a></div>',
                            unsafe_allow_html=True
                        )
                for err in errors:
                    st.markdown(f'<div class="wb">❌ {err}</div>', unsafe_allow_html=True)
        with c2:
            if st.button("❌  Cancel", width='stretch'):
                st.session_state["push_confirm"] = False
                st.rerun()
