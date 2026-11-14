"""Chiptune audio synthesized in code (decision Q12: original chiptune; I.5).

No audio files: every sound is generated as 16-bit PCM with the stdlib and
handed to pygame.mixer. Music is generated incrementally (a slice per frame)
so phones don't stall at startup. If the mixer can't start (no sound device,
browser autoplay policy), every call quietly does nothing.
"""
import math
import random
from array import array

import pygame

SR = 22050
MUSIC_BASE_VOL = 0.36     # music Sound volume at 100% on the settings slider
NOTE = {n: i for i, n in enumerate(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])}


def hz(name):
    """'A4' -> 440.0"""
    pitch, octave = name[:-1], int(name[-1])
    return 440.0 * 2 ** ((NOTE[pitch] + 12 * (octave + 1) - 69) / 12)


def _on_wsl():
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def pre_init():
    """Call before pygame.init(): open the mixer in the format the game's audio is
    generated in (SR mono 16-bit), so nothing is resampled in Python, and with a
    buffer that suits the platform. WSL (WSLg's PulseAudio bridge to Windows)
    stutters with small buffers, so it gets a bigger one and a PulseAudio latency
    target. Override with HYPE_AUDIO_BUFFER (samples) / PULSE_LATENCY_MSEC."""
    import os
    wsl = _on_wsl()
    if wsl:
        os.environ.setdefault("PULSE_LATENCY_MSEC", "40")
    try:
        buf = int(os.environ.get("HYPE_AUDIO_BUFFER", 1024 if wsl else 512))
    except ValueError:
        buf = 512
    try:
        pygame.mixer.pre_init(SR, -16, 1, buf, allowedchanges=0)
    except TypeError:
        pygame.mixer.pre_init(SR, -16, 1, buf)


# --- synthesis helpers (lists of floats in -1..1) -----------------------------------
def osc(freq, dur, wave="square", vol=0.3, duty=0.5, f_end=None, attack=0.004, decay=True,
        vib=0.0, sr=SR):
    n = int(sr * dur)
    out = [0.0] * n
    ph = 0.0
    f_end = freq if f_end is None else f_end
    a_n = max(1, int(sr * attack))
    for i in range(n):
        k = i / n
        f = freq + (f_end - freq) * k
        if vib:
            f *= 1 + vib * math.sin(i / sr * 2 * math.pi * 6)
        ph = (ph + f / sr) % 1.0
        if wave == "square":
            v = 1.0 if ph < duty else -1.0
        elif wave == "tri":
            v = 4 * ph - 1 if ph < 0.5 else 3 - 4 * ph
        elif wave == "saw":
            v = 2 * ph - 1
        else:
            v = math.sin(2 * math.pi * ph)
        env = min(1.0, i / a_n)
        if decay:
            env *= (1 - k) ** 1.5
        out[i] = v * env * vol
    return out


def noise(dur, vol=0.3, rate=8000, decay=True, sr=SR, seed=1, rate_end=None):
    r = random.Random(seed)
    n = int(sr * dur)
    out = [0.0] * n
    v = 0.0
    acc = 0.0
    rate_end = rate if rate_end is None else rate_end
    for i in range(n):
        k = i / n
        acc += (rate + (rate_end - rate) * k) / sr
        if acc >= 1.0:
            acc -= 1.0
            v = r.uniform(-1, 1)
        out[i] = v * vol * ((1 - k) ** 2 if decay else 1.0)
    return out


def mix(*parts, offsets=None):
    offsets = offsets or [0.0] * len(parts)
    n = max(int(o * SR) + len(p) for p, o in zip(parts, offsets))
    out = [0.0] * n
    for p, o in zip(parts, offsets):
        s = int(o * SR)
        for i, v in enumerate(p):
            out[s + i] += v
    return out


def _onepole_lp(x, fc, sr=SR):
    """One-pole low-pass, run circularly (two passes) so a loop wraps seamlessly."""
    a = math.exp(-2 * math.pi * fc / sr)
    y = x[-1]
    out = [0.0] * len(x)
    for _ in range(2):
        for i, v in enumerate(x):
            y = v + a * (y - v)
            out[i] = y
    return out


def _onepole_hp(x, fc, sr=SR):
    lp = _onepole_lp(x, fc, sr)
    return [v - l for v, l in zip(x, lp)]


ENGINE_STEPS = 16
ENGINE_HZ = (15.0, 82.0)      # four-stroke single firing rate: ~1800 rpm idle .. ~9800 rpm


def engine_hz(step):
    lo, hi = ENGINE_HZ
    return lo * (hi / lo) ** (step / (ENGINE_STEPS - 1))


def engine_loop(fire_hz, dur=0.6, seed=7, sr=SR):
    g = engine_loop_gen(fire_hz, dur, seed, sr)
    try:
        while True:
            next(g)
    except StopIteration as done:
        return done.value


def engine_loop_gen(fire_hz, dur=0.6, seed=7, sr=SR):
    """A seamless loop of a single-cylinder four-stroke at `fire_hz` firings per second.

    Each firing is a soft-edged exhaust thump: a low resonant 'body' tone plus a
    breath of noise, decaying before the next one. Firings wobble a little in
    timing, strength and tone (real engines never fire identically), and the
    whole loop is low-passed so there is no buzz or whine on top.
    """
    r = random.Random(seed)
    n_fire = max(3, round(fire_hz * dur))
    n = int(round(n_fire * sr / fire_hz))
    period = n / n_fire
    out = [0.0] * n
    tau = max(0.005, min(0.022, 0.32 / fire_hz))            # pulse decay
    plen = int(sr * tau * 5)
    att = 0.0012 * sr
    body = 105 + 1.5 * fire_hz                              # exhaust note (bark), ~130-230 Hz
    for k in range(n_fire):
        start = k * period + r.uniform(-0.035, 0.035) * period
        amp = (1.0 if k % 2 == 0 else 0.86) * r.uniform(0.85, 1.12)
        fr = body * r.uniform(0.93, 1.07)
        f2 = fr * r.uniform(2.6, 2.9)
        ns = r.uniform(0.45, 0.65)
        lp_n = 0.0
        base = int(start)
        for j in range(plen):
            t = j / sr
            env = math.exp(-t / tau) * (1 - math.exp(-j / att))
            w = 2 * math.pi * t
            lp_n += (r.uniform(-1, 1) - lp_n) * 0.35           # roughly low-passed noise
            v = (math.sin(w * fr) + 0.3 * math.sin(w * f2) * math.exp(-t / (tau * 0.5)) + ns * lp_n)
            out[(base + j) % n] += v * env * amp
        if k % 6 == 5:
            yield None                                       # built a slice per frame
    yield None
    out = _onepole_hp(out, 28, sr)                           # no DC thump at the loop seam
    yield None
    fc = 520 + 11 * fire_hz
    out = _onepole_lp(out, fc, sr)
    yield None
    out = _onepole_lp(out, fc, sr)                           # 12 dB/oct: kills the fizz
    yield None
    peak = max(1e-6, max(abs(v) for v in out))
    return [v / peak * 0.85 for v in out]


def seq(notes, step, **kw):
    """notes: list of names or None (rest). Each note lasts `step` seconds."""
    parts, offs = [], []
    for i, nm in enumerate(notes):
        if nm:
            parts.append(osc(hz(nm), step * 0.95, **kw))
            offs.append(i * step)
    return mix(*parts, offsets=offs) if parts else [0.0] * int(len(notes) * step * SR)


class Audio:
    def __init__(self, enabled=True):
        self.enabled = False
        self.sound_on = True
        self.music_on = True
        self.sfx_vol = 1.0
        self.music_vol = 1.0
        self.sounds = {}
        self.engine_loops = [None] * ENGINE_STEPS
        self._engine_gen = None
        self._engine_bucket = None
        self._engine_x = 0.0
        self._engine_ch = 0
        self._tick_n = 0
        self._music_gen = None
        self._music = None
        self._music_playing = False
        self._want_music = False
        if not enabled:
            return
        try:
            if not pygame.mixer.get_init():
                try:   # ask SDL to convert to the device format for us (no Python resampling)
                    pygame.mixer.init(SR, -16, 1, 512, allowedchanges=0)
                except TypeError:
                    pygame.mixer.init(SR, -16, 1, 512)
            freq, size, ch = pygame.mixer.get_init()
            self.sr, self.channels = freq, ch
            pygame.mixer.set_num_channels(12)
            # two engine channels so pitch steps crossfade instead of cutting over
            self.ch_engines = (pygame.mixer.Channel(0), pygame.mixer.Channel(2))
            self.ch_music = pygame.mixer.Channel(1)
            pygame.mixer.set_reserved(3)
            self._build_sfx()
            self.enabled = True
        except Exception:
            self.enabled = False

    def configure(self, sound, music, sfx_vol=1.0, music_vol=1.0):
        self.sfx_vol = max(0.0, min(1.0, float(sfx_vol)))
        self.music_vol = max(0.0, min(1.0, float(music_vol)))
        self.sound_on = bool(sound) and self.sfx_vol > 0
        self.music_on = bool(music) and self.music_vol > 0
        if not self.enabled:
            return
        for ch in self.ch_engines:
            ch.set_volume(self.sfx_vol)
        if self._music is not None:
            self._music.set_volume(MUSIC_BASE_VOL * self.music_vol)
        if not self.sound_on:
            self.stop_engine()
        if not self.music_on:
            self.ch_music.stop()
            self._music_playing = False

    # -- buffers ------------------------------------------------------------------
    def _sound(self, samples, vol=1.0):
        if self.sr != SR:     # resample by nearest neighbour if the device rate differs
            k = SR / self.sr
            samples = [samples[min(len(samples) - 1, int(i * k))] for i in range(int(len(samples) / k))]
        a = array("h", (max(-32767, min(32767, int(v * 32767))) for v in samples))
        if self.channels == 2:
            st = array("h", [0]) * (len(a) * 2)
            st[0::2] = a
            st[1::2] = a
            a = st
        snd = pygame.mixer.Sound(buffer=a.tobytes())
        snd.set_volume(vol)
        return snd

    def _build_sfx(self):
        S = self._sound
        self.sounds = {
            "takeoff": S(osc(220, 0.12, "square", 0.25, 0.25, f_end=520)),
            "land": S(mix(noise(0.10, 0.35, 2500), osc(90, 0.1, "tri", 0.4, f_end=60))),
            "perfect": S(seq(["E5", "G#5", "B5", "E6"], 0.055, wave="square", vol=0.22, duty=0.25)),
            "rough": S(mix(noise(0.16, 0.35, 1800), osc(140, 0.16, "square", 0.18, f_end=70))),
            "bounce": S(osc(160, 0.05, "square", 0.12, 0.5, f_end=120)),
            "crash": S(mix(noise(0.55, 0.5, 6000, rate_end=500), osc(300, 0.4, "square", 0.2, f_end=50))),
            "forgiven": S(seq(["C5", "E5", "G5"], 0.06, wave="tri", vol=0.4)),
            "coolant": S(mix(noise(0.25, 0.18, 9000), osc(400, 0.25, "sine", 0.25, f_end=1200))),
            "heatpad": S(mix(noise(0.3, 0.22, 4000, rate_end=9000), osc(180, 0.3, "saw", 0.22, f_end=700))),
            "overheat": S(mix(seq(["A5", None, "A5", None, "A5"], 0.09, wave="square", vol=0.2),
                              noise(0.6, 0.15, 12000))),
            "cooled": S(osc(300, 0.2, "tri", 0.3, f_end=600)),
            "beep": S(osc(hz("A4"), 0.14, "square", 0.25, 0.5, decay=False)),
            "go": S(osc(hz("A5"), 0.35, "square", 0.25, 0.5)),
            "lap": S(seq(["C6", "G5"], 0.08, wave="square", vol=0.22, duty=0.25)),
            "finish": S(seq(["C5", "E5", "G5", "C6", None, "G5", "C6"], 0.09, wave="square", vol=0.24, duty=0.25)),
            "bump": S(osc(110, 0.08, "square", 0.25, f_end=60)),
            "click": S(osc(880, 0.03, "square", 0.15, 0.5)),
            "upgrade": S(seq(["G4", "C5", "E5", "G5", "C6"], 0.05, wave="square", vol=0.2, duty=0.25)),
            "buy": S(seq(["E5", "B5"], 0.07, wave="square", vol=0.22, duty=0.25)),
            "deny": S(osc(150, 0.16, "square", 0.22, 0.5, f_end=110)),
            "explode": S(mix(noise(1.1, 0.6, 5000, rate_end=250), osc(160, 0.9, "square", 0.25, f_end=30),
                             osc(70, 0.7, "sine", 0.45, f_end=25))),
            "splash": S(mix(noise(0.3, 0.3, 7000, rate_end=2500), osc(500, 0.18, "sine", 0.18, f_end=180))),
            "lava": S(mix(noise(0.45, 0.3, 2500, rate_end=800), osc(90, 0.4, "saw", 0.25, f_end=260))),
            "vent": S(mix(noise(0.5, 0.25, 11000, rate_end=4000), osc(600, 0.3, "sine", 0.15, f_end=250))),
            "bike_drop": S(mix(noise(0.12, 0.35, 2500), osc(110, 0.12, "tri", 0.4, f_end=55))),
        }
        self._engine_gen = self._build_engine()

    ENGINE_VOL = 0.42

    def _build_engine(self):
        """Engine loops, built a slice at a time from tick()."""
        order = [0, ENGINE_STEPS - 1]
        gap = ENGINE_STEPS
        while len(order) < ENGINE_STEPS:          # spread out: any step has a near neighbour early
            gap //= 2
            order += [b for b in range(gap, ENGINE_STEPS, gap) if b not in order]
        for b in order:
            samples = yield from engine_loop_gen(engine_hz(b), seed=11 + b)
            self.engine_loops[b] = self._sound(samples, self.ENGINE_VOL)
            yield None

    # -- public API --------------------------------------------------------------------
    def event(self, kind):
        if not (self.enabled and self.sound_on):
            return
        s = self.sounds.get(kind)
        if s:
            ch = s.play()
            if ch:     # play() resets the channel volume, so apply the slider each time
                ch.set_volume(self.sfx_vol)

    def ui(self, kind="click"):
        self.event(kind)

    def engine(self, bike, ctl):
        if not (self.enabled and self.sound_on):
            return
        if bike.state in ("crash", "done") or (bike.state == "overheat" and bike.speed <= 0):
            self.stop_engine()
            return
        x = bike.speed / 50.0
        if bike.state == "ride":
            x += 0.08 * getattr(bike, "boost_level", 1 if ctl.b else 0)
        x = max(0.0, min(1.0, x)) * (ENGINE_STEPS - 1)
        b = self._engine_bucket
        if b is None or abs(x - b) > 0.7:           # hysteresis: no flutter between two steps
            b = int(x + 0.5)
        if self.engine_loops[b] is None:          # still being built: use the nearest that is
            built = [i for i, s in enumerate(self.engine_loops) if s is not None]
            if not built:
                return
            b = min(built, key=lambda i: abs(i - b))
        cur = self.ch_engines[self._engine_ch]
        if b != self._engine_bucket or not cur.get_busy():
            first = self._engine_bucket is None or not cur.get_busy()
            if not first:
                cur.fadeout(110)
                self._engine_ch ^= 1
                cur = self.ch_engines[self._engine_ch]
            self._engine_bucket = b
            cur.play(self.engine_loops[b], loops=-1, fade_ms=110 if not first else 60)
            cur.set_volume(self.sfx_vol)

    def stop_engine(self):
        if self.enabled:
            for ch in self.ch_engines:
                ch.fadeout(80)
        self._engine_bucket = None

    # -- music ---------------------------------------------------------------------------------
    def music(self, name="title"):
        """Request menu music (name=None stops it)."""
        self._want_music = name is not None
        if not self.enabled:
            return
        if name is None:
            self.ch_music.fadeout(300)
            self._music_playing = False

    def tick(self):
        """Call once per frame: builds engine loops and music a slice at a time
        (alternating frames, so neither waits on the other), then loops the music."""
        if not self.enabled:
            return
        self._tick_n += 1
        if self._engine_gen is not None and (self._music is not None or self._tick_n % 2):
            try:
                next(self._engine_gen)
            except StopIteration:
                self._engine_gen = None
        elif self._music is None:
            if self._music_gen is None:
                self._music_gen = self._build_music()
            try:
                next(self._music_gen)
            except StopIteration as done:
                self._music = done.value
                self._music.set_volume(MUSIC_BASE_VOL * self.music_vol)
            return
        if self._music is not None and self._want_music and self.music_on and not self._music_playing:
            self.ch_music.play(self._music, loops=-1, fade_ms=600)
            self._music_playing = True

    def _build_music(self):
        """Compose, then convert to device PCM in small slices (no frame spikes)."""
        samples = yield from self._compose()
        k = SR / self.sr
        n_out = int(len(samples) / k)
        out = array("h", [0]) * (n_out * self.channels)
        chunk = 6000
        for start in range(0, n_out, chunk):
            for i in range(start, min(n_out, start + chunk)):
                v = samples[min(len(samples) - 1, int(i * k))]
                v = max(-32767, min(32767, int(v * 32767)))
                if self.channels == 2:
                    out[2 * i] = v
                    out[2 * i + 1] = v
                else:
                    out[i] = v
            yield None
        return pygame.mixer.Sound(buffer=out.tobytes())

    def _compose(self):
        """An original 8-bar loop at 132 bpm: lead, bass, drums."""
        step = 60 / 132 / 2       # eighth notes
        lead = ("E5 - G5 A5 - G5 E5 D5 | E5 - G5 A5 - C6 B5 A5 | G5 - E5 D5 - E5 G5 - | A5 G5 E5 D5 C5 - D5 - |"
                " E5 - G5 A5 - G5 E5 D5 | E5 - G5 A5 - C6 D6 C6 | B5 - A5 G5 - E5 D5 E5 | A5 - - - G5 - - - ")
        bass = ("A2 A2 A3 A2 A2 A3 A2 G2 | F2 F2 F3 F2 F2 F3 F2 G2 | C3 C3 C4 C3 C3 C4 C3 B2 | G2 G2 G3 G2 G2 G3 B2 G2 |"
                " A2 A2 A3 A2 A2 A3 A2 G2 | F2 F2 F3 F2 F2 F3 F2 G2 | C3 C3 C4 C3 G2 G2 G3 G2 | A2 A2 E3 E3 A2 - - - ")
        L = [t for t in lead.split() if t != "|"]
        B = [t for t in bass.split() if t != "|"]
        n = len(L)
        total = int(n * step * SR)
        out = [0.0] * total
        kick = osc(110, 0.12, "sine", 0.5, f_end=40)
        hat = noise(0.04, 0.12, 14000)
        snare = noise(0.14, 0.22, 7000)
        for i in range(n):
            s = int(i * step * SR)
            parts = []
            if L[i] != "-":
                dur = step
                j = i + 1
                while j < n and L[j] == "-":
                    dur += step
                    j += 1
                parts.append(osc(hz(L[i]), dur * 0.92, "square", 0.13, 0.25, vib=0.004))
            if B[i] != "-":
                parts.append(osc(hz(B[i]), step * 0.9, "tri", 0.3, decay=False))
            if i % 4 == 0:
                parts.append(kick)
            if i % 4 == 2:
                parts.append(snare)
            parts.append(hat)
            for p in parts:
                for k, v in enumerate(p):
                    if s + k < total:
                        out[s + k] += v
            yield None
        return out
