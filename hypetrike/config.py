"""Global constants: timing, layout, physics tuning, colours.

Physics numbers follow the spec's "feel contract" (§3.1):
  speed: integer units, 0 .. ~46 on A, cap 48 on B; +1/step on A, +2/step on B
  temperature: starts 8, settles at 17 holding A, overheats at 32
"""

TITLE = "Hype Trike"

# --- timing -----------------------------------------------------------------
FPS = 60                    # fixed simulation rate (ticks per second)

# --- layout (logical pixels; height is fixed, width follows screen aspect) ---
# ZOOM: the logical canvas is this much bigger than the 360 px-tall design, so
# the world (art drawn pixel for pixel) shows smaller and more of the track
# fits on screen. The world band (designed for 360 px) sits WORLD_DY px down;
# the extra height is more sky above it and a foreground strip below.
ZOOM = 1.25
DESIGN_H = 360
VIEW_H = round(DESIGN_H * ZOOM)
WORLD_DY = (VIEW_H - DESIGN_H) * 2 // 3
DEFAULT_VIEW_W = round(640 * ZOOM)
MIN_VIEW_W = round(560 * ZOOM)
MAX_VIEW_W = round(860 * ZOOM)

TILE_W = 80                 # one track column, 8 per 640 px view
LANES = 4
LANE_SPACING = 20
LANE_BASE_Y = 236 + WORLD_DY  # ground line of lane 0 (back); lane 3 is the front
BIKE_SCREEN_X = round(170 * ZOOM)  # bike stays put, the track scrolls

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
# One-button throttle (setting "throttle_mode" = "one"): heat IS the throttle.
# Holding heats the engine, letting go cools it, and speed follows the heat
# through four zones, each a step riskier and faster than the last:
#   COLD      0 .. ONE_BOOST_AT       speed ramps 0 .. A top speed (warming up)
#   WARM      .. ONE_HOT_AT           turbo top speed; heat climbs slowly (WARM_HEAT_MULT):
#                                     a wide, safe band to sit in
#   HOT       .. ONE_OVERHEAT_AT      +HOT_SPEED_K x super_extra top speed, quicker accel;
#                                     heat climbs at the full rate
#   OVERHEAT  .. TEMP_OVERHEAT        far more speed and accel, but the bike burns: heat
#                                     climbs faster still, the landing window shrinks, and
#                                     reaching the top blows the bike up
# The engine starts cold; a crash zeroes the heat.
ONE_COLD_HEAT_MULT = 1.6    # heat_a multiplier below the warm band
# Heat is shown as HEAT_BARS segments (the arc over the rider); pads and zones are
# measured in whole bars so they read straight off the gauge.
HEAT_BARS = 16
HEAT_BAR = TEMP_OVERHEAT / HEAT_BARS   # heat per bar (2.0)
ONE_BOOST_AT = 2 * HEAT_BAR            # = 4: cold -> warm (2 bars of cold)
ONE_HOT_AT = 10 * HEAT_BAR             # = 20: warm -> hot (8 bars of warm, half the gauge)
ONE_OVERHEAT_AT = 13 * HEAT_BAR        # = 26: hot -> overheating, where the bike catches fire
ONE_SUPER_AT = ONE_HOT_AT              # old name: where the boost band ends (hot and up)
SUPER_BARS = HEAT_BARS - 10            # hot + overheating bars
WARM_HEAT_MULT = 0.75       # heating rate in the warm band (x heat_b): a longer, safer window
HOT_HEAT_MULT = 1.0         # ... in the hot band
OVERHEAT_HEAT_MULT = 1.35   # ... and while overheating (it runs away from you)
# Pads are HEAT pads in one-button mode, in three sizes: +1 / +2 / +3 bars
# (track.tiles.PAD_BARS). Speed, but risk.
ONE_ROUGH_HEAT_LOSS = 6.0   # rough landings dump this much heat (lost boost / speed)
RED_AT = 27.0               # classic mode's red zone on the gauge (turbo nearly overheating)
VENT_DROP = 4.0             # Radiator vent (one-button): heat drops to this far below the red
SUPER_BOOST_EXTRA = 3       # bike stat super_extra: the unit of hot / overheat top speed
# Hot band: top speed over turbo, acceleration and air rotation.
HOT_SPEED_K = 1.0           # +1 x super_extra (+3)
HOT_ACCEL = 0.2             # acceleration interval x (1 - this): 20% quicker
HOT_TURN = 1.1
# Overheating zone (heat ONE_OVERHEAT_AT..blow-up) scales with depth:
OVERHEAT_SPEED_LO = 2.5     # top speed over turbo at the zone's edge, x super_extra (+7.5) ...
OVERHEAT_SPEED_HI = 3.5     # ... rising to this at the very top (+10.5)
OVERHEAT_ACCEL = 0.45       # acceleration 45% quicker anywhere in the zone
OVERHEAT_TURN = 1.25        # air rotation 25% faster anywhere in the zone
OVERHEAT_LAND = 0.75        # ... but the safe landing window is 25% narrower (the bike is on fire)
EXPLODE_EXTRA_TICKS = 100   # explosion lasts this much longer than a normal crash
EXPLODE_DROP_AT = 0.82      # fraction of the explosion when the new bike touches down
# Water puddles (any theme but Volcano): a splash that cools the engine and slows you.
WATER_COOL = 6.0            # heat lost (one-button: also speed, since heat is speed)
WATER_SPEED_KEEP = 0.75     # speed kept through the splash
# Volcano theme ("lava" level): the air is hot, so heat rises faster and drains
# slower, and water puddles are lava pits: a big speed kick and a lot of heat.
LAVA_THEME = "lava"
LAVA_HEAT_MULT = 1.35       # heating rate multiplier on the Volcano theme
LAVA_COOL_MULT = 0.55       # cooling rate multiplier on the Volcano theme
LAVA_PIT_HEAT = 3 * HEAT_BAR  # heat added by a lava pit (3 bars, like a large pad)
LAVA_PIT_SPEED = 8          # instant speed over the current cap (bleeds off at the overspeed rate)
THROTTLE_GRACE_TICKS = 36   # 0.6 s after letting go: speed holds (A cap), temp frozen
OVERHEAT_TICKS = 150        # engine stall duration

# --- speed feel (visual only) ---------------------------------------------------
# Boost and super boost ease in a "speed feel" that scrolls the backdrop faster,
# pushes the camera ahead of the rider, draws screen-wide speed lines and (super
# only) shakes the view a little. Physics never sees any of this.
FX_EASE = 0.05              # per tick, how fast the feel follows the boost level
FX_BG_BOOST = 0.9           # extra backdrop scroll speed at full boost (x normal)
FX_BG_SUPER = 1.2           # ... and on top of that at full super boost
FX_CAM_LEAD = 12            # px the camera runs ahead at full boost
FX_CAM_LEAD_SUPER = 12      # ... and on top of that at full super boost
FX_SHAKE = 1.5              # px of horizontal shake at full super boost

# In-race bike + rider sprites are drawn at this scale, so the rider on the bike
# matches the thrown / jogging rider after a crash (the garage shows full size).
SPRITE_SCALE = 0.7
# How the smaller sprites are made: "native" redraws the art's shapes at that size
# (crisp pixels); True = filtered resample (blurry); False = nearest (drops rows).
SPRITE_SMOOTH = "native"
CAM_JUMP_PX = 30            # the bike moving more than this in one frame is a respawn jump ...
CAM_SCROLL_EASE = 0.88      # ... the camera scrolls over to it (offset kept per frame)
# Heat gauge: a smooth curved bar worn over the rider's helmet (the only heat
# gauge): centre offset from the bike's ground contact point, inner radius, px.
FIRE_FROM = 0.0             # the bike catches fire this far into the overheating zone (0..1)
HEAT_ARC_DX = round(-3 * SPRITE_SCALE)
HEAT_ARC_DY = round(-44 * SPRITE_SCALE)
HEAT_ARC_R = 13

# --- air / landing ---------------------------------------------------------------
GRAVITY = 0.20              # px / tick^2
PITCH_RATE = 2.2            # deg / tick while holding tilt in the air
AIR_NOSE_DROP = 0.32        # deg / tick natural nose-down drift in the air
PRESS_START = 0.35          # mouse "button" scheme, button down mid-air: the nose-down push starts at
PRESS_GROW = 0.05           # ... this share of the pitch rate and grows this much per tick (full after 13)
RELEASE_GROW = 0.04         # ... button up mid-air: the nose lifts at the drift rate plus this share of
RELEASE_MAX = 0.8           # ... the pitch rate per tick free, up to this share
GROUND_ANGLE_LERP = 0.5
HOOP_R = 15.0               # flaming hoop: pass within this many px of its centre height ...
HOOP_BOOST = 10             # ... then land clean: this much speed past the cap ...
HOOP_PERFECT_EXTRA = 5      # ... and this much more for a PERFECT
HOOP_CHANCE = 0.35          # share of jumps that get a hoop on the generated tracks
PERFECT_GRACE_PX = 10.0     # lined up for a PERFECT this close above the ground ...
PERFECT_GRACE_TICKS = 6     # ... still counts for this many ticks (last-moment twitches)
LAND_PERFECT = 5.0          # |angle error| for a "perfect" landing
LAND_TOLERANCE = 14.0       # |angle error| that still keeps all speed
LAND_ROUGH = 38.0           # nose-high error up to this = rough landing (speed loss)
LAND_ROUGH_NOSE = 32.0      # nose-low error down to -this = rough landing too (a bit less forgiving)
ROUGH_SPEED_KEEP = 0.5
ROUGH_WOBBLE_TICKS = 24
MICRO_HOP_TICKS = 14         # hops shorter than this never crash
MICRO_HOP_SPEED_KEEP = 0.8
WALL_CATCH = 16             # px below a deck's far lip you can still scramble up (broken span)
MUD_SPEED = 18              # speed limit on mud
DEBRIS_SAFE_SPEED = 10      # hitting debris at or below this only stops you
DEBRIS_CLEAR_H = 12         # air height that clears debris

# --- slipstream ------------------------------------------------------------------
# Tucked in a small pocket right behind another rider in your lane (player only):
# a little more top speed, and in one-button mode the engine heats faster (heat is
# speed), so sitting in the draft reels the rider in. The Slipstream run upgrade
# makes the pocket longer and the speed bonus bigger.
SLIP_RANGE = 1.25 * 80      # px behind the rider ahead (just over a section)
SLIP_LANE = 0.45            # lanes either side of that rider's line
SLIP_SPEED = 0.05           # +5% top speed while drafting
SLIP_HEAT_MULT = 1.4        # one-button: heating rate x this while drafting and holding

# --- lanes -----------------------------------------------------------------------
LANE_CHANGE_RATE = 0.125    # lanes per tick
CLIMB_SLOPE = 0.1            # uphill steeper than this (~6 deg): no heat gained
LANE_STEP_MAX = 4.0         # px: a lane change can't climb onto ground higher than this

# --- crash -------------------------------------------------------------------------
CRASH_TICKS = 130           # thrown off + jog back
RESPAWN_CLEAR_COLS = 3      # a hazard within this many tiles of a respawn: respawn past it instead
RESPAWN_MAX_SKIP = 10       # ... but never move a respawn more than this many tiles

# --- race ------------------------------------------------------------------------------
COUNTDOWN_TICKS = 180
START_X = TILE_W * 0.5      # bike starts half a column into the start tile
START_LINE_DX = 24          # the drawn start line sits this far ahead of START_X (front tyres touch it)

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
