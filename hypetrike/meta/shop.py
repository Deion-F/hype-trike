"""Meta-shop catalogue (spec §6.3). Coins only buy cosmetics: bike paints, rider
colours and boost colours. Power comes from each bike's own XP (meta/bike_tune.py),
and new vehicles unlock as runs get deeper (VEHICLE_UNLOCKS). Biomes (track
themes) aren't sold: a run tours them all, and quick races and the editor can use
any of them."""
from bike import VEHICLES
from ui.art import LIVERIES, BOOSTS

# kind -> profile list key
# Rider colours share ownership with bike paints: buy a scheme once, use it on either.
KIND_KEY = {"vehicle": "vehicles", "livery": "liveries", "rider": "liveries", "boost": "boosts"}
SELECT_KEY = {"vehicle": "vehicle", "livery": "livery", "rider": "rider", "boost": "boost"}
COSMETIC_KINDS = ("livery", "rider", "boost")

PRICES = {
    "livery": {"flame": 0, "ocean": 60, "lime": 60, "violet": 90, "gold": 150, "ghost": 220},
    "boost": {"flame": 0, "plasma": 100, "toxic": 100, "neon": 120, "gold": 160, "ghost": 200},
}
PRICES["rider"] = PRICES["livery"]
# Vehicles unlock by clearing biomes in a run (profile "best_biome"), not with coins.
VEHICLE_UNLOCKS = {"dirt": 0, "trike": 1, "scrambler": 2, "sprinter": 3}
# What the one-off starting upgrades used to cost; saves that bought them are refunded once.
OLD_KIT_PRICES = {"cool_head": 140, "gyro": 140, "soft_shocks": 180, "track_boots": 120,
                  "radiator": 140, "sponsor": 200, "all_terrain": 160, "quick_steer": 150}
# What the theme packs used to cost; saves that bought them are refunded once.
OLD_THEME_PRICES = {"desert": 100, "night": 150, "stadium": 200, "lava": 250}


def unlock_text(vehicle):
    from run.manager import BIOMES
    from ui.art import THEMES
    n = VEHICLE_UNLOCKS[vehicle]
    if n <= 0:
        return ""
    return f"Clear the {THEMES[BIOMES[n - 1]]['name']} in a run to unlock"


def check_vehicle_unlocks(profile):
    """Unlock every vehicle the profile's best run has earned. Returns the new ones."""
    new = []
    for v, need in VEHICLE_UNLOCKS.items():
        if need <= profile.data.get("best_biome", 0) and v not in profile.data["vehicles"]:
            profile.unlock("vehicles", v)
            new.append(v)
    return new


def catalogue(kind):
    items = []
    if kind == "vehicle":
        for v in VEHICLES:
            items.append({"id": v, "name": VEHICLES[v]["name"], "desc": VEHICLES[v]["desc"], "price": None})
        return items
    for item_id, price in PRICES[kind].items():
        if kind == "livery":
            name, desc = LIVERIES[item_id]["name"], "Bike paint. Also unlocks these colours for your rider."
        elif kind == "rider":
            name, desc = LIVERIES[item_id]["name"], "Rider suit and helmet. Shares unlocks with bike paints."
        else:
            name, desc = BOOSTS[item_id]["name"], "Colour of your heat flame, boost sparks and hot speed lines."
        items.append({"id": item_id, "name": name, "desc": desc, "price": price})
    return items


def upgrade_price(profile, vehicle, up_id):
    """XP for the next level of a bike upgrade (None when maxed). 0 with the
    testing setting "Free bike upgrades" on."""
    from meta.bike_tune import price
    cost = price(vehicle, up_id, profile.bike_levels(vehicle).get(up_id, 0))
    if cost is not None and profile.settings.get("free_upgrades", False):
        return 0
    return cost


def buy_upgrade(profile, vehicle, up_id):
    """Spend a bike's XP on the next level of one of its upgrades."""
    if vehicle not in profile.data["vehicles"]:
        return False
    levels = profile.bike_levels(vehicle)
    cost = upgrade_price(profile, vehicle, up_id)
    if cost is None or not profile.spend_xp(vehicle, cost):
        return False
    levels[up_id] = levels.get(up_id, 0) + 1
    profile.save()
    return True


def buy(profile, kind, item_id):
    """Spend coins on a cosmetic and unlock it. Returns True on success."""
    if kind not in COSMETIC_KINDS:
        return False
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
