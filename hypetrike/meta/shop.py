"""Meta-shop catalogue (spec §6.3). Vehicles trade strengths and liveries are
cosmetic (sidegrades, decision Q8). The Starter Kit is the one place coins buy
lasting power: small levelled steps (meta/kit.py) that apply to every run. Biomes (track themes) aren't sold:
a run tours them all, and quick races and the editor can use any of them."""
from bike import VEHICLES
from meta.kit import KIT, MAX_LEVEL
from ui.art import LIVERIES, BOOSTS

# kind -> profile list key
# Rider colours share ownership with bike paints: buy a scheme once, use it on either.
KIND_KEY = {"vehicle": "vehicles", "livery": "liveries", "rider": "liveries", "boost": "boosts"}
SELECT_KEY = {"vehicle": "vehicle", "livery": "livery", "rider": "rider", "boost": "boost"}

PRICES = {
    "vehicle": {"dirt": 0, "trike": 300, "scrambler": 450, "sprinter": 650},
    "livery": {"flame": 0, "ocean": 60, "lime": 60, "violet": 90, "gold": 150, "ghost": 220},
    "boost": {"flame": 0, "plasma": 100, "toxic": 100, "neon": 120, "gold": 160, "ghost": 200},
}
PRICES["rider"] = PRICES["livery"]
# What the one-off starting upgrades used to cost; saves that bought them are refunded once.
OLD_KIT_PRICES = {"cool_head": 140, "gyro": 140, "soft_shocks": 180, "track_boots": 120,
                  "radiator": 140, "sponsor": 200, "all_terrain": 160, "quick_steer": 150}
# What the theme packs used to cost; saves that bought them are refunded once.
OLD_THEME_PRICES = {"desert": 100, "night": 150, "stadium": 200, "lava": 250}


def kit_level(profile, item_id):
    return int(profile.data.get("kit_levels", {}).get(item_id, 0))


def catalogue(kind, mode="one"):
    if kind == "kit":
        return [{"id": it.id, "name": it.name, "category": it.category, "desc": it.describe(MAX_LEVEL),
                 "price": None} for it in KIT.values()]
    items = []
    for item_id, price in PRICES[kind].items():
        if kind == "vehicle":
            name, desc = VEHICLES[item_id]["name"], VEHICLES[item_id]["desc"]
        elif kind == "livery":
            name, desc = LIVERIES[item_id]["name"], "Bike paint. Also unlocks these colours for your rider."
        elif kind == "rider":
            name, desc = LIVERIES[item_id]["name"], "Rider suit and helmet. Shares unlocks with bike paints."
        else:
            name, desc = BOOSTS[item_id]["name"], "Colour of your heat flame, boost sparks and hot speed lines."
        items.append({"id": item_id, "name": name, "desc": desc, "price": price})
    return items


def buy_kit_level(profile, item_id):
    """Spend coins on the next Starter Kit level. Returns True on success."""
    level = kit_level(profile, item_id)
    price = KIT[item_id].price(level)
    if price is None or not profile.spend(price):
        return False
    profile.data.setdefault("kit_levels", {})[item_id] = level + 1
    profile.save()
    return True


def buy_tune_level(profile, vehicle, stat_id):
    """Spend coins on the next tuning level of one stat of one owned vehicle."""
    from meta.bike_tune import price
    if vehicle not in profile.data["vehicles"]:
        return False
    levels = profile.bike_levels(vehicle)
    cost = price(vehicle, stat_id, levels.get(stat_id, 0))
    if cost is None or not profile.spend(cost):
        return False
    levels[stat_id] = levels.get(stat_id, 0) + 1
    profile.save()
    return True


def buy(profile, kind, item_id):
    """Spend coins and unlock. Returns True on success."""
    if kind == "kit":
        return buy_kit_level(profile, item_id)
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
    if kind == "rider":
        return sel.get("rider", sel.get("livery")) == item_id
    return sel.get(SELECT_KEY.get(kind, kind), "flame" if kind == "boost" else None) == item_id


def select(profile, kind, item_id):
    if kind not in KIND_KEY:
        return False
    key = KIND_KEY[kind]
    if item_id not in profile.data[key]:
        return False
    profile.data["selected"][SELECT_KEY[kind]] = item_id
    profile.save()
    return True
