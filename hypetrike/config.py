"""Global constants: timing, layout, physics tuning, colours.

Physics numbers follow the spec's "feel contract" (§3.1):
  speed: integer units, 0 .. ~46 on A, cap 48 on B; +1/step on A, +2/step on B
  temperature: starts 8, settles at 17 holding A, overheats at 32
"""

TITLE = "Hype Trike"

# --- timing -----------------------------------------------------------------
FPS = 60                    # fixed simulation rate (ticks per second)

# --- layout (logical pixels; height is fixed, width follows screen aspect) ---
VIEW_H = 360
DEFAULT_VIEW_W = 640
MIN_VIEW_W = 560
MAX_VIEW_W = 860

TILE_W = 80                 # one track column, 8 per 640 px view
LANES = 4
LANE_SPACING = 20
LANE_BASE_Y = 236           # ground line of lane 0 (back); lane 3 is the front
BIKE_SCREEN_X = 170         # bike stays put, the track scrolls

def lane_y(lane_pos: float) -> float:
    """Screen y of the ground line for a (possibly fractional) lane."""
    return LANE_BASE_Y + lane_pos * LANE_SPACING

# --- speed --------------------------------------------------------------------
SPEED_TO_PX = 0.125         # px per tick per speed unit (46 -> 5.75 px/tick)
SPEED_MAX_A = 46
SPEED_MAX_B = 48
ACCEL_INTERVAL = 4          # ticks per acceleration step
COAST_INTERVAL = 5          # ticks per -1 speed when off throttle
OVERSPEED_INTERVAL = 3      # ticks per -1 when above the held button's max
AIR_DRAG_INTERVAL = 30      # ticks per -1 speed while airborne

# --- temperature ---------------------------------------------------------------
TEMP_START = 8.0
TEMP_STABLE_A = 17.0
TEMP_OVERHEAT = 32.0
HEAT_A = 0.06               # per tick while below 17 on A
HEAT_B = 0.07               # per tick on B (no ceiling until overheat)
COOL_A = 0.03               # per tick when above 17 on A
COOL_COAST = 0.05           # per tick when off throttle
OVERHEAT_TICKS = 150        # engine stall duration

# --- air / landing ---------------------------------------------------------------
GRAVITY = 0.20              # px / tick^2
PITCH_RATE = 2.2            # deg / tick while holding tilt in the air
AIR_NOSE_DROP = 0.35        # deg / tick natural nose-down drift in the air
GROUND_ANGLE_LERP = 0.5
LAND_PERFECT = 5.0          # |angle error| for a "perfect" landing
LAND_TOLERANCE = 14.0       # |angle error| that still keeps all speed
LAND_ROUGH = 38.0           # nose-high error up to this = rough landing (speed loss)
ROUGH_SPEED_KEEP = 0.5
ROUGH_WOBBLE_TICKS = 24
MICRO_HOP_TICKS = 14         # hops shorter than this never crash
MICRO_HOP_SPEED_KEEP = 0.8
MUD_SPEED = 18              # speed limit on mud
DEBRIS_SAFE_SPEED = 10      # hitting debris at or below this only stops you
DEBRIS_CLEAR_H = 12         # air height that clears debris

# --- lanes -----------------------------------------------------------------------
LANE_CHANGE_RATE = 0.125    # lanes per tick

# --- crash -------------------------------------------------------------------------
CRASH_TICKS = 130           # thrown off + jog back

# --- race ------------------------------------------------------------------------------
COUNTDOWN_TICKS = 180
START_X = TILE_W * 0.5      # bike starts half a column into the start tile

# --- colours (base palette; themes override) ------------------------------------
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
INK = (24, 20, 37)
HUD_BG = (24, 20, 37)
HUD_FG = (244, 240, 232)
ACCENT = (255, 196, 0)
DANGER = (232, 59, 59)
COOL = (64, 200, 255)
GOOD = (90, 220, 110)
