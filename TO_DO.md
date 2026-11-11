1. Add in CPU players similar to the original game. They player should be able to run sideways into them with the logic being:
    - if the players back wheel touches the CPUs front wheel, the CPU falls and the player gets some reward (coins, points, whatever makes the mose sense for progression)
    - if the player runs into the CPU sideways, both of them fall (maybe add powerups to allow for a shield or a certain number of free tackles into other players)
    - if the CPUs back tire runs into the players front tire, the player falls and maybe the CPU is marked as a rival that if the player can make them fall before the heat is over, they get some bonus or they get something back that the CPU stole

## To discuss later: mouse controls (from recording review, 2026-11-10)

2. **Re-anchoring without losing throttle.** Moving the anchor means letting go of both buttons, which costs speed (in the third recording, speed sat at 0 for ~2 s around 0:35 while repositioning). Trying first: a 0.6 s throttle grace period (speed holds briefly after release). Idea if that's not enough: middle-click / scroll-wheel click drops a new anchor while throttle stays held. Concern: keep the controls simple.
3. ~~**Accidental wheelies in whoops.**~~ Done 2026-11-10: new "Mouse wheelie" setting, default "Ramps only" (flat-ground side movement slides home; lean switches on at ramps).
4. **Starts.** Throttle started after GO in the recording (1st to 4th within 0.5 s). Holding the left button through the countdown also sets the anchor early. Maybe hint at this on the heat intro or during the countdown.
5. ~~**Coolant pads in one-button mode.**~~ Done 2026-11-10: pads are heat pads in one-button mode.
6. **Crash resets heat to 0 only in one-button mode.** In throttle + boost mode heat is purely bad, so zeroing it on a crash would be a reward. Revisit if the modes should share this rule.

## Rival difficulty (2026-11-10)

7. **Test: higher-tier upgrades push rival difficulty up faster.** Rival difficulty is now `rival_level = round / 5` (0 → 1 over a run; see `rival_setup` in `hypetrike/race.py`). Idea: each higher-tier upgrade the player takes adds a little to the level for the rest of the run, so a strong build meets stronger rivals sooner. Needs upgrade tiers first (upgrades currently have categories and stack caps, no tiers).
