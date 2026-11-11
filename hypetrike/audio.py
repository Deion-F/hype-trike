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
        self.engine_loops = []
        self._engine_bucket = None
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
            self.ch_engine = pygame.mixer.Channel(0)
            self.ch_music = pygame.mixer.Channel(1)
            pygame.mixer.set_reserved(2)
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
        self.ch_engine.set_volume(self.sfx_vol)
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
            "bike_drop": S(mix(noise(0.12, 0.35, 2500), osc(110, 0.12, "tri", 0.4, f_end=55))),
        }
        # engine: pulse loops at rising pitch; whole cycles so loops don't click
        self.engine_loops = []
        for b in range(12):
            f = 38 + b * 11
            cyc = SR / f
            n_cyc = max(4, int(0.12 * f))
            n = int(round(cyc * n_cyc))
            loop = []
            for i in range(n):
                ph = (i / cyc) % 1.0
                v = (0.22 if ph < 0.3 else -0.22) + (0.08 if (2 * ph) % 1.0 < 0.5 else -0.08)
                loop.append(v)
            self.engine_loops.append(self._sound(loop, 0.35))

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
        b = int(bike.speed / 4.5)
        if bike.state == "ride":
            b += getattr(bike, "boost_level", 1 if ctl.b else 0)
        b = max(0, min(len(self.engine_loops) - 1, b))
        if b != self._engine_bucket or not self.ch_engine.get_busy():
            self._engine_bucket = b
            self.ch_engine.play(self.engine_loops[b], loops=-1)
            self.ch_engine.set_volume(self.sfx_vol)

    def stop_engine(self):
        if self.enabled:
            self.ch_engine.stop()
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
        """Call once per frame: builds music a slice at a time, then loops it."""
        if not self.enabled:
            return
        if self._music is None:
            if self._music_gen is None:
                self._music_gen = self._build_music()
            try:
                next(self._music_gen)
            except StopIteration as done:
                self._music = done.value
                self._music.set_volume(MUSIC_BASE_VOL * self.music_vol)
            return
        if self._want_music and self.music_on and not self._music_playing:
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
