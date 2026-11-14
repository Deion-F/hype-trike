"""Mouse "button" control scheme: one button is throttle on the ground and leans
forward in the air. The mouse itself only picks lanes (hover).

  Ground: button held = throttle / heat (left = A, right = B in classic mode).
  Air:    button held = nose down, gentle for a tap and winding up to the full
          rate over a hold (Controls.ramp). Released = the nose lifts, faster
          the longer it's free, so releasing is how you lean back.
          A button held up the ramp carries straight on into a forward lean at
          take-off (it winds up from gentle): you leave a ramp nose-up, so
          leaning forward right away is what most jumps want.
          Throttle is frozen for the whole flight: in one-button mode heat
          neither rises nor falls while you pitch; in classic mode the
          throttle you had at take-off carries on.

Pure logic (no pygame) so the race input and the tuning tools' simulated
player share it exactly.
"""


class ButtonAir:
    def __init__(self):
        self.reset()

    def reset(self):
        self._ground_ab = (False, False)

    def apply(self, c, held_a, held_b, bike, one_button):
        """Fold the button state into Controls `c` (keys already in it)."""
        held = held_a or held_b
        air = bike is not None and bike.airborne and bike.state == "ride"
        if air:
            c.right = c.right or held
            c.ramp = True                          # push winds up, the free nose lifts faster
            if one_button:
                c.a, c.b = True, False             # holding in the air keeps heat: frozen
            else:
                c.a, c.b = self._ground_ab
        else:
            c.a = c.a or held_a
            c.b = c.b or held_b
            self._ground_ab = (c.a, c.b)
        return c
