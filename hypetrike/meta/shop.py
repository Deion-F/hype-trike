"""Meta-shop catalogue (spec §6.3). Unlocks are sidegrades and options, not
raw power (decision Q8): vehicles trade strengths, starting kits are single
modest upgrades, and liveries and themes are cosmetic."""
from bike import VEHICLES
from run.upgrades import UPGRADES
from ui.art import LIVERIES, THEMES

# kind -> profile list key
KIND_KEY = {"vehicle": "vehicles", "livery": "liveries", "kit": "start_upgrades", "theme": "themes"}

PRICES = {
    "vehicle": {"dirt": 0, "trike": 300, "scrambler": 450, "sprinter": 650},
    "livery": {"flame": 0, "ocean": 60, "lime": 60, "violet": 90, "gold": 150, "ghost": 220},
    "kit": {"cool_head": 140, "gyro": 140, "soft_shocks": 180, "track_boots": 120,
            "radiator": 140, "sponsor": 200, "all_terrain": 160},
    "theme": {"valley": 0, "desert": 100, "night": 150, "stadium": 200},
}


def catalogue(kind):
    items = []
    for item_id, price in PRICES[kind].items():
        if kind == "vehicle":
            name, desc = VEHICLES[item_id]["name"], VEHICLES[item_id]["desc"]
        elif kind == "livery":
            name, desc = LIVERIES[item_id]["name"], "Paint job"
        elif kind == "kit":
            up = UPGRADES[item_id]
            name, desc = up.name, "Start every run with: " + up.desc
        else:
            name, desc = THEMES[item_id]["name"], "Track theme pack for runs and quick races"
        items.append({"id": item_id, "name": name, "desc": desc, "price": price})
    return items


def buy(profile, kind, item_id):
    """Spend coins and unlock. Returns True on success."""
    key = KIND_KEY[kind]
    if item_id in profile.data[key]:
        return False
    price = PRICES[kind][item_id]
    if not profile.spend(price):
        return False
    profile.unlock(key, item_id)
    profile.save()
    return True


def is_selected(profile, kind, item_id):
    sel = profile.selected
    if kind == "vehicle":
        return sel["vehicle"] == item_id
    if kind == "livery":
        return sel["livery"] == item_id
    if kind == "kit":
        return sel.get("start_upgrade") == item_id
    return item_id in profile.data.get("theme_rotation", profile.themes)


def select(profile, kind, item_id):
    key = KIND_KEY[kind]
    if item_id not in profile.data[key]:
        return False
    sel = profile.data["selected"]
    if kind == "vehicle":
        sel["vehicle"] = item_id
    elif kind == "livery":
        sel["livery"] = item_id
    elif kind == "kit":
        sel["start_upgrade"] = None if sel.get("start_upgrade") == item_id else item_id
    else:
        rot = profile.data.setdefault("theme_rotation", list(profile.themes))
        if item_id in rot and len(rot) > 1:
            rot.remove(item_id)
        elif item_id not in rot:
            rot.append(item_id)
    profile.save()
    return True


def active_themes(profile):
    rot = [t for t in profile.data.get("theme_rotation", profile.themes) if t in profile.themes]
    return rot or ["valley"]
