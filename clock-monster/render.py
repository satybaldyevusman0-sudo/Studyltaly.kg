#!/usr/bin/env python3
"""
Clock Monster - 18 second vertical (9:16) 2D cartoon animation.

Timeline
  0-3 s   clock hands spin extremely fast, then slam to a stop at midnight
  3-8 s   a normal wall clock, calmly ticking
  8-14 s  it transforms into a creepy clock monster with one giant eye
  14-18 s the clock opens its mouth and swallows the camera

Everything is drawn procedurally in flat 2D (Pillow + NumPy), the soundtrack
is synthesised with NumPy, and ffmpeg encodes the result.

Usage:  python3 render.py [output.mp4]
"""
import math
import os
import random
import subprocess
import sys
import wave
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont

W, H, FPS, DUR = 1080, 1920, 30, 18.0
SS = 2                      # supersampling factor (anti-aliasing)
NF = int(FPS * DUR)
T_STOP = 2.3                # moment the hands slam to 12:00
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
TAU = math.tau

# ----------------------------------------------------------------- palette
INK = (28, 20, 34)
WALL_A, WALL_C = (58, 66, 120), (72, 14, 30)
STRIPE_A, STRIPE_C = (50, 57, 108), (56, 8, 22)
WAIN_A, WAIN_C = (78, 50, 56), (40, 10, 16)
MOLD_A, MOLD_C = (120, 80, 70), (70, 20, 26)
WOOD_A, WOOD_C = (176, 104, 52), (86, 30, 32)
WOODD_A, WOODD_C = (122, 68, 36), (48, 14, 20)
FACE_A, FACE_C = (252, 243, 216), (198, 212, 128)
BRASS = (232, 184, 72)
TOOTH = (250, 246, 224)


# ----------------------------------------------------------------- helpers
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def lerp(a, b, t):
    return a + (b - a) * t


def seg(t, a, b):
    return clamp((t - a) / (b - a))


def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def ease_in(x):
    x = clamp(x)
    return x * x * x


def back_out(x, s=1.7):
    x = clamp(x) - 1
    return x * x * ((s + 1) * x + s) + 1


def mix(c1, c2, t):
    return tuple(int(round(lerp(a, b, t))) for a, b in zip(c1, c2))


def rgba(c, a):
    return (c[0], c[1], c[2], int(clamp(a, 0, 255)))


def ell(cx, cy, rx, ry, n=96, a0=0.0, a1=TAU):
    closed = abs(a1 - a0 - TAU) < 1e-9
    m = n if closed else n + 1
    return [(cx + rx * math.cos(a0 + (a1 - a0) * i / n),
             cy + ry * math.sin(a0 + (a1 - a0) * i / n)) for i in range(m)]


def keyframes(t, keys):
    """keys: [(time, (x, y)), ...] smooth-stepped interpolation."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            e = smooth(seg(t, t0, t1))
            return tuple(lerp(a, b, e) for a, b in zip(v0, v1))
    return keys[-1][1]


class Painter:
    """Draws polygons/lines given in some local space through a mapping fn."""

    def __init__(self, img, fn, k, off=(0, 0)):
        self.img, self.fn, self.k, self.off = img, fn, k, off
        self.d = ImageDraw.Draw(img, "RGBA")

    def pts(self, ps):
        ox, oy = self.off
        out = []
        for x, y in ps:
            sx, sy = self.fn(x, y)
            out.append((sx - ox, sy - oy))
        return out

    def lw(self, w):
        return max(1, int(round(w * self.k)))

    def poly(self, ps, fill=None, outline=INK, w=0.025):
        pp = self.pts(ps)
        if fill is not None:
            self.d.polygon(pp, fill=fill)
        if outline is not None and w > 0:
            self.d.line(pp + [pp[0], pp[1]], fill=outline, width=self.lw(w), joint="curve")

    def line(self, ps, color=INK, w=0.025, caps=True):
        pp = self.pts(ps)
        lw = self.lw(w)
        self.d.line(pp, fill=color, width=lw, joint="curve")
        if caps:
            r = lw / 2
            for x, y in (pp[0], pp[-1]):
                self.d.ellipse([x - r, y - r, x + r, y + r], fill=color)

    def circle(self, c, r, fill=None, outline=INK, w=0.025, ry=None, n=96):
        self.poly(ell(c[0], c[1], r, r if ry is None else ry, n), fill, outline, w)


def clipped(img, fn, k, mask_local, draw_cb):
    """Run draw_cb(painter) on a layer clipped to the polygon mask_local."""
    pts = [fn(x, y) for x, y in mask_local]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, y0 = max(0, int(min(xs)) - 2), max(0, int(min(ys)) - 2)
    x1, y1 = min(img.width, int(max(xs)) + 3), min(img.height, int(max(ys)) + 3)
    if x1 <= x0 or y1 <= y0:
        return
    layer = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    draw_cb(Painter(layer, fn, k, off=(x0, y0)))
    mask = Image.new("L", layer.size, 0)
    ImageDraw.Draw(mask).polygon([(x - x0, y - y0) for x, y in pts], fill=255)
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
    img.paste(layer, (x0, y0), layer)


_FONTS = {}


def font(size):
    size = max(4, int(size))
    if size not in _FONTS:
        _FONTS[size] = ImageFont.truetype(FONT_BOLD, size)
    return _FONTS[size]


def stamp_text(img, txt, cx, cy, size, fill, stroke=INK, angle=0.0, alpha=1.0):
    if size < 6 or alpha <= 0.01:
        return
    f = font(size)
    sw = max(2, int(size) // 12)
    bb = f.getbbox(txt, stroke_width=sw)
    tw, th = bb[2] - bb[0] + sw * 2 + 8, bb[3] - bb[1] + sw * 2 + 8
    layer = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((tw / 2, th / 2), txt, font=f, fill=fill,
                               stroke_width=sw, stroke_fill=stroke, anchor="mm")
    if angle:
        layer = layer.rotate(angle, resample=Image.BICUBIC, expand=True)
    if alpha < 1:
        layer.putalpha(layer.getchannel("A").point(lambda v: int(v * alpha)))
    img.paste(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)), layer)


# --------------------------------------------------------- static randomness
_rng = random.Random(7)
CRACKS = []
for _ in range(7):
    a = _rng.uniform(0, TAU)
    r = 1.0
    pts = [(r * math.sin(a), -r * math.cos(a))]
    for _ in range(6):
        r -= _rng.uniform(0.05, 0.11)
        a += _rng.uniform(-0.18, 0.18)
        pts.append((r * math.sin(a), -r * math.cos(a)))
    CRACKS.append(pts)

VEINS = []
for i in range(16):
    a = i / 16 * TAU + _rng.uniform(-0.15, 0.15)
    r = 1.05
    pts = [(r * math.cos(a), r * math.sin(a))]
    for _ in range(6):
        r -= _rng.uniform(0.06, 0.1)
        a += _rng.uniform(-0.2, 0.2)
        pts.append((r * math.cos(a), r * math.sin(a)))
    VEINS.append(pts)

STARS = [(_rng.uniform(85, 315), _rng.uniform(145, 465), _rng.uniform(2, 4.5), _rng.uniform(0, TAU))
         for _ in range(16)]

_yy, _xx = np.mgrid[0:H, 0:W].astype(np.float32)
_d = np.sqrt(((_xx - W / 2) / (W / 2)) ** 2 * 0.75 + ((_yy - H / 2) / (H / 2)) ** 2 * 0.75)
VIG = (np.clip((_d - 0.45) / 0.75, 0, 1) ** 1.6)[..., None]


# ------------------------------------------------------------------ camera
class Cam:
    pass


def camera(t):
    c = Cam()
    c.z = (1.0 + 0.04 * smooth(seg(t, 0, T_STOP))
           + 0.08 * smooth(seg(t, 3, 8)) + 0.08 * smooth(seg(t, 8, 14))
           + 0.15 * ease_in(seg(t, 15.3, 16.7)))
    if t >= T_STOP:
        c.z += 0.06 * math.exp(-(t - T_STOP) * 5)
    c.x = 540.0
    c.y = lerp(960, 905, smooth(seg(t, 3, 8)))
    a = 0.0
    if 0.3 < t < T_STOP:
        a += 4 * seg(t, 0.3, T_STOP)
    if t >= T_STOP:
        a += 30 * math.exp(-(t - T_STOP) * 7)
    if 8 < t < 14:
        a += 2 + 8 * seg(t, 8, 9) * (1 - 0.7 * seg(t, 9.6, 10.6))
    if t >= 9.35:
        a += 24 * math.exp(-(t - 9.35) * 6)
    if 12.1 < t < 13.6:
        a += 7 * math.sin(math.pi * seg(t, 12.1, 13.6))
    if 14 < t < 15.3:
        a += 5
    if 15.3 <= t < 17.3:
        a += 6 + 16 * seg(t, 15.3, 16.7)
    if t >= 17.3:
        a += 45 * math.exp(-(t - 17.3) * 8)
    c.shx = a * (0.6 * math.sin(t * 97.3) + 0.4 * math.sin(t * 151.7 + 1))
    c.shy = a * (0.6 * math.sin(t * 83.1 + 2) + 0.4 * math.sin(t * 133.9))
    return c


# ------------------------------------------------------------------ hands
def g_spin(u, a=0.18):
    u = clamp(u)
    v = u * u / (2 * a) if u < a else u - a / 2
    return v / (1 - a / 2)


def hand_angles(t):
    """minute, hour, second angles (radians, 0 = 12 o'clock, clockwise)."""
    if t < T_STOP:
        g = g_spin(t / T_STOP)
        m0, h0, s0 = TAU * 0.42, TAU * 0.62, TAU * 0.1
        return (m0 + (TAU * 16 - m0) * g, h0 + (TAU * 3 - h0) * g, s0 + (TAU * 45 - s0) * g)
    d = t - T_STOP
    wob = math.sin(d * 32) * math.exp(-d * 7)
    m, h, s = 0.35 * wob, 0.22 * wob, 0.5 * wob
    six = math.radians(6)
    if t >= 3.3:
        n = int(math.floor(t - T_STOP))
        frac = (t - T_STOP) - n
        if n <= 4:
            s += six * ((n - 1) + back_out(frac / 0.12))
        elif n == 5:                                   # creepy: ticks BACKWARD
            s += six * (4 - back_out(frac / 0.25))
        else:
            s += six * 3
        if t > 7.4:
            s += 0.05 * math.sin(t * 70) * seg(t, 7.4, 8)
    if t > 8:
        s += 0.25 * math.sin(t * 37) * seg(t, 8, 9)
        m -= TAU * 2 * smooth(seg(t, 8.3, 9.3)) + 0.1 * math.sin(t * 23) * seg(t, 8, 8.4)
        h += TAU * smooth(seg(t, 8.3, 9.3))
    return m, h, s


def hand_pts(px, py, a, L, w, tail=0.16):
    dx, dy = math.sin(a), -math.cos(a)
    nx, ny = math.cos(a), math.sin(a)
    prof = [(-tail * L, -w), (0.72 * L, -w * 0.75), (0.74 * L, -w * 2.0), (L, 0),
            (0.74 * L, w * 2.0), (0.72 * L, w * 0.75), (-tail * L, w)]
    return [(px + u * dx + v * nx, py + u * dy + v * ny) for u, v in prof]


def sector(a0, a1, r0, r1, n=24):
    outer = [(r1 * math.sin(lerp(a0, a1, i / n)), -r1 * math.cos(lerp(a0, a1, i / n))) for i in range(n + 1)]
    inner = [(r0 * math.sin(lerp(a1, a0, i / n)), -r0 * math.cos(lerp(a1, a0, i / n))) for i in range(n + 1)]
    return outer + inner


# ------------------------------------------------------------------ mouth
M_CY, M_W0, M_HU, M_HL = 0.55, 0.6, 0.24, 0.48


def mouth_geom(o, wfrac):
    w = (M_W0 + 0.2 * o) * max(wfrac, 1e-3)

    def s_of(x):
        return math.sqrt(max(0.0, 1 - (x / w) ** 2))

    def y0(x):
        return M_CY - 0.15 * (x / w) ** 2

    def yu(x):
        return y0(x) - o * M_HU * s_of(x)

    def yl(x):
        return y0(x) + o * M_HL * s_of(x)
    return w, s_of, yu, yl


def draw_mouth(img, fn, k, t, o, wfrac, mcol):
    if wfrac <= 0.01:
        return
    p = Painter(img, fn, k)
    w, s_of, yu, yl = mouth_geom(o, wfrac)
    n = 48
    xs = [lerp(-w, w, i / n) for i in range(n + 1)]
    upper = [(x, yu(x)) for x in xs]
    lower = [(x, yl(x)) for x in reversed(xs)]
    shape = upper + lower[1:-1]
    mcx, mcy = 0.0, (yu(0) + yl(0)) / 2

    if o > 0.01:
        def inside(lp):
            lp.poly(shape, fill=(112, 10, 26), outline=None)
            for j in range(9):                     # throat tunnel
                f = j / 8
                r = lerp(0.62, 0.07, f) * (0.4 + 0.6 * o)
                lp.circle((mcx, mcy + 0.02), r * 1.15, ry=r * 0.8,
                          fill=mix((112, 10, 26), (18, 0, 6), f ** 0.8), outline=None)
            # tongue
            ty = yl(0) - 0.02
            lp.circle((0, ty), 0.42, ry=0.17 * o + 0.02, fill=(214, 72, 104), outline=INK, w=0.02)
            lp.line([(0, ty - 0.12 * o), (0, ty - 0.02)], color=(160, 40, 70), w=0.018)
            # uvula
            uy = yu(0)
            ul = 0.16 * o
            lp.poly([(-0.05, uy), (0.05, uy), (0.035, uy + ul * 0.7), (0, uy + ul),
                     (-0.035, uy + ul * 0.7)], fill=(222, 84, 110), outline=INK, w=0.014)
        clipped(img, fn, k, shape, inside)

    tooth = mix(TOOTH, (232, 222, 168), smooth(seg(t, 14, 16)))
    nu, nl = 8, 7
    span = w * 0.94
    bw = span * 2 / nu / 2
    for i in range(nu):
        xc = lerp(-span + bw, span - bw, i / (nu - 1))
        L = 0.15 * (0.45 + 0.55 * s_of(xc)) * (1.45 if i in (1, nu - 2) else 1.0)
        p.poly([(xc - bw, yu(xc - bw)), (xc + bw, yu(xc + bw)), (xc, yu(xc) + L)],
               fill=tooth, outline=INK, w=0.014)
    bl = span * 2 / nu / 2
    for i in range(nl):
        xc = lerp(-span + 2 * bl, span - 2 * bl, i / (nl - 1))
        L = 0.13 * (0.45 + 0.55 * s_of(xc))
        p.poly([(xc - bl, yl(xc - bl)), (xc + bl, yl(xc + bl)), (xc, yl(xc) - L)],
               fill=tooth, outline=INK, w=0.014)
    if o > 0.01:
        p.poly(shape, fill=None, outline=INK, w=0.03)
    else:
        p.line([(x, yu(x)) for x in xs], color=INK, w=0.025)

    if t > 13.0 and o < 0.95:                       # drool
        dl = 0.28 * smooth(seg(t, 13.0, 14.2)) + 0.03 * math.sin(t * 5)
        x0 = w * 0.62
        yb = yu(x0) + 0.02
        dp = [(x0 - 0.025, yb), (x0 + 0.025, yb), (x0 + 0.02, yb + dl * 0.8),
              (x0 + 0.035, yb + dl), (x0, yb + dl + 0.05), (x0 - 0.035, yb + dl),
              (x0 - 0.02, yb + dl * 0.8)]
        p.poly(dp, fill=(180, 235, 200, 200), outline=INK, w=0.01)


# ------------------------------------------------------------------ eye
def draw_eye(img, fn, k, t, slit, eo, m):
    p = Painter(img, fn, k)
    ecx, ecy = 0.0, -0.08
    rx = 0.64 * slit
    ry = 0.48 * eo
    if slit <= 0.01:
        return
    glow = 0.5 + 0.5 * math.sin(t * 7)
    for j in range(5):                              # red glow around the eye
        g = (5 - j) / 5
        p.circle((ecx, ecy), rx + 0.05 + 0.06 * g, ry=max(ry, 0.02) + 0.05 + 0.06 * g,
                 fill=(255, 30, 30, int(18 * m * (0.6 + 0.4 * glow))), outline=None)
    if ry < 0.025:
        p.line([(ecx - rx, ecy), (ecx + rx, ecy)], color=INK, w=0.035)
        p.line([(ecx - rx * 0.8, ecy), (ecx + rx * 0.8, ecy)], color=(255, 60, 40), w=0.012)
        return
    shape = ell(ecx, ecy, rx, ry, 96)
    white = mix((250, 248, 236), (242, 228, 190), smooth(seg(t, 10.5, 12.5)))

    gaze = keyframes(t, [(10.3, (0, 0)), (10.6, (-0.75, 0.15)), (11.0, (-0.75, 0.15)),
                         (11.25, (0.75, -0.1)), (11.6, (0.75, -0.1)), (11.85, (0, 0))])
    gx = gaze[0] + 0.03 * math.sin(t * 53) * seg(t, 11.9, 12.2)
    gy = gaze[1]
    contract = smooth(seg(t, 11.8, 12.15))
    veins = smooth(seg(t, 10.6, 12.6))

    def inside(lp):
        lp.poly(shape, fill=white, outline=None)
        # shading on the upper part of the eyeball
        lp.circle((ecx, ecy - ry * 0.9), rx * 1.1, ry=ry * 0.55, fill=(120, 60, 60, 60), outline=None)
        nv = int(len(VEINS) * veins + 0.999) if veins > 0 else 0
        for v in VEINS[:nv]:
            cut = max(2, int(len(v) * min(1.0, veins * 1.3)))
            pts = [(ecx + rx * u, ecy + ry * q) for u, q in v[:cut]]
            lp.line(pts, color=(205, 30, 45, 220), w=0.012)
        ic = (ecx + gx * rx * 0.42, ecy + gy * ry * 0.35)
        ir = 0.27
        lp.circle(ic, ir + 0.03, fill=(200, 40, 20), outline=INK, w=0.02)
        lp.circle(ic, ir, fill=(255, 150, 30), outline=None)
        lp.circle(ic, ir * 0.72, fill=(255, 212, 60), outline=None)
        for j in range(14):                         # iris streaks
            a = j / 14 * TAU
            lp.line([(ic[0] + math.cos(a) * ir * 0.35, ic[1] + math.sin(a) * ir * 0.35),
                     (ic[0] + math.cos(a) * ir * 0.9, ic[1] + math.sin(a) * ir * 0.9)],
                    color=(220, 110, 20, 160), w=0.01, caps=False)
        prx = lerp(0.12, 0.04, contract)
        lp.circle(ic, prx, ry=0.2, fill=(12, 6, 14), outline=None)
        lp.circle((ic[0] - 0.09, ic[1] - 0.1), 0.055, fill=(255, 255, 255, 235), outline=None)
        lp.circle((ic[0] + 0.07, ic[1] + 0.09), 0.025, fill=(255, 255, 255, 200), outline=None)
        # eyelid shadow
        lp.poly(ell(ecx, ecy - ry, rx * 1.05, ry * 0.25, 48), fill=(60, 20, 30, 70), outline=None)
    clipped(img, fn, k, shape, inside)
    p.poly(shape, fill=None, outline=INK, w=0.035)
    # creepy bags under the eye
    bag = smooth(seg(t, 10.5, 11.5))
    if bag > 0:
        for j, (s_, y_) in enumerate(((0.55, 0.12), (0.4, 0.2))):
            pts = ell(ecx, ecy + ry * 0.2, rx * s_ + 0.08, ry * 0.8 + y_, 24, 0.25 * math.pi, 0.75 * math.pi)
            p.line(pts, color=rgba(INK, 200 * bag), w=0.016)


# ------------------------------------------------------------------ scene
def draw_background(img, t, cam, m, glow_pos):
    z = 1 + (cam.z - 1) * 0.6

    def fn(x, y):
        return (((x - cam.x) * z + W / 2 + cam.shx * 0.6) * SS,
                ((y - cam.y) * z + H / 2 + cam.shy * 0.6) * SS)
    p = Painter(img, fn, z * SS)
    stripe = mix(STRIPE_A, STRIPE_C, m)
    for kx in range(-8, 22):
        x0 = kx * 84
        p.poly([(x0, -900), (x0 + 42, -900), (x0 + 42, 2900), (x0, 2900)], fill=stripe, outline=None)
    dot = mix((70, 80, 140), (90, 20, 40), m)
    for kx in range(-8, 22):
        for ky in range(-6, 22):
            cx, cy = kx * 84 + 63, ky * 120 + (60 if kx % 2 else 0)
            if cy < 1470:
                p.poly([(cx, cy - 9), (cx + 7, cy), (cx, cy + 9), (cx - 7, cy)], fill=dot, outline=None)

    # window with moon
    wood = mix((112, 72, 48), (60, 20, 22), m)
    p.poly([(50, 110), (350, 110), (350, 500), (50, 500)], fill=wood, outline=INK, w=5)
    p.poly([(75, 135), (325, 135), (325, 475), (75, 475)], fill=mix((22, 28, 72), (46, 4, 14), m), outline=INK, w=4)
    for sx, sy, sr, ph in STARS:
        tw = 0.5 + 0.5 * math.sin(t * 4 + ph)
        p.circle((sx, sy), sr, fill=(255, 248, 220, int(120 + 120 * tw * (1 - m))), outline=None, n=12)
    moon = mix((255, 244, 200), (232, 52, 40), m)
    for j in range(4):
        p.circle((245, 225), 52 + 14 * (4 - j), fill=rgba(moon, 14), outline=None)
    p.circle((245, 225), 52, fill=moon, outline=None)
    p.circle((228, 212), 11, fill=mix((235, 220, 170), (190, 30, 30), m), outline=None)
    p.circle((262, 240), 7, fill=mix((235, 220, 170), (190, 30, 30), m), outline=None)
    p.poly([(194, 135), (206, 135), (206, 475), (194, 475)], fill=wood, outline=None)
    p.poly([(75, 299), (325, 299), (325, 311), (75, 311)], fill=wood, outline=None)
    p.poly([(35, 495), (365, 495), (365, 522), (35, 522)], fill=wood, outline=INK, w=5)

    # wainscoting
    p.poly([(-900, 1490), (1980, 1490), (1980, 2900), (-900, 2900)], fill=mix(WAIN_A, WAIN_C, m), outline=None)
    panel = mix((62, 38, 44), (28, 6, 10), m)
    for kx in range(-4, 8):
        x0 = kx * 270 + 40
        p.poly([(x0, 1560), (x0 + 210, 1560), (x0 + 210, 2500), (x0, 2500)], fill=None, outline=panel, w=8)
    p.poly([(-900, 1465), (1980, 1465), (1980, 1500), (-900, 1500)], fill=mix(MOLD_A, MOLD_C, m), outline=INK, w=4)

    # glow behind the clock
    gx, gy = glow_pos
    warm = (255, 214, 150)
    red = (255, 40, 30)
    pulse = 0.75 + 0.25 * math.sin(t * 6)
    gcol = mix(warm, red, m)
    ga = lerp(10, 16 * pulse, m)
    for j in range(7):
        p.circle((gx, gy), 720 - j * 50, fill=rgba(gcol, ga), outline=None, n=72)


def draw_clock(img, t, cam, m):
    # ---- transform of the clock body
    pos = [540.0, 860.0]
    s = 330.0
    stx = sty = 1.0
    rot = 0.0
    if t < T_STOP:
        rot = 0.025 * math.sin(t * 70) * seg(t, 0.3, T_STOP)
    else:
        d = t - T_STOP
        sq = 0.12 * math.sin(d * 25) * math.exp(-d * 6)
        stx, sty = 1 + sq, 1 - sq
    if t > 8:
        s *= 1 + 0.018 * math.sin(t * 6) * m
        rot += 0.045 * math.sin(t * 3.1) * m
    o = 0.0
    if t >= 14:
        o = 0.72 * back_out(seg(t, 14.0, 14.9), 1.2)
        o = lerp(o, 0.85, smooth(seg(t, 14.9, 15.3)))
        o = lerp(o, 1.0, smooth(seg(t, 15.3, 15.8)))
        sty *= 1 + 0.1 * o
        s *= lerp(1, 0.92, smooth(seg(t, 14.9, 15.3)))          # anticipation
        e = seg(t, 15.3, 17.3)
        s *= 13.0 ** (e * e * 1.25 if e < 0.7 else 0.6125 + (e - 0.7) * 0.6)
        rot *= 1 - smooth(seg(t, 15.3, 15.9))
        w_, s_of, yu, yl = mouth_geom(o, 1)
        mc_y = (yu(0) + yl(0)) / 2 * sty
        a2 = smooth(seg(t, 15.3, 16.1))
        pos = [lerp(pos[0], cam.x, a2), lerp(pos[1], cam.y - s * mc_y, a2)]

    cr, sr = math.cos(rot), math.sin(rot)

    def fn(x, y):
        x *= stx
        y *= sty
        x, y = x * cr - y * sr, x * sr + y * cr
        wx, wy = pos[0] + s * x, pos[1] + s * y
        return (((wx - cam.x) * cam.z + W / 2 + cam.shx) * SS,
                ((wy - cam.y) * cam.z + H / 2 + cam.shy) * SS)
    k = s * cam.z * SS * math.sqrt(stx * sty)
    p = Painter(img, fn, k)

    wood = mix(WOOD_A, WOOD_C, m)
    woodd = mix(WOODD_A, WOODD_C, m)
    face = mix(FACE_A, FACE_C, m)
    ink_num = mix(INK, (120, 10, 20), m)

    # ---- shadow, hanger, horns
    if t < 15.3:
        p.circle((0.07, 0.09), 1.2, fill=(10, 5, 20, 70), outline=None)
        p.line([(-0.5, -1.06), (0, -1.42), (0.5, -1.06)], color=(60, 50, 50), w=0.02)
        p.circle((0, -1.42), 0.045, fill=BRASS, outline=INK, w=0.015)
    hp = back_out(seg(t, 10.4, 11.3), 1.5)
    if hp > 0:
        for sgn in (-1, 1):
            ba = sgn * math.radians(36)
            bx, by = 1.0 * math.sin(ba), -1.0 * math.cos(ba)
            rx_, ry_ = 0.55 * math.sin(ba), -0.55 * math.cos(ba) - 0.45   # mostly upward
            ln = math.hypot(rx_, ry_)
            rx_, ry_ = rx_ / ln, ry_ / ln
            ox, oy = -ry_ * sgn, rx_ * sgn                  # sideways, away from centre
            ox, oy = (ox, oy) if ox * sgn > 0 else (-ox, -oy)
            n = 12
            left, right = [], []
            for i in range(n + 1):
                f = i / n
                cx_ = bx + rx_ * 0.62 * hp * f + ox * 0.14 * hp * f * f
                cy_ = by + ry_ * 0.62 * hp * f + oy * 0.14 * hp * f * f
                tx = rx_ * 0.62 + ox * 0.28 * f
                ty = ry_ * 0.62 + oy * 0.28 * f
                tl = math.hypot(tx, ty)
                nx_, ny_ = -ty / tl, tx / tl
                wdt = 0.15 * (1 - f) ** 0.9
                left.append((cx_ + nx_ * wdt, cy_ + ny_ * wdt))
                right.append((cx_ - nx_ * wdt, cy_ - ny_ * wdt))
            pts, inner = left, right[::-1]
            p.poly(pts + inner, fill=(96, 28, 36), outline=INK, w=0.025)

    # ---- rim and face
    p.circle((0, 0), 1.18, fill=wood, outline=INK, w=0.035)
    p.line(ell(0, 0, 1.12, 1.12, 40, math.radians(190), math.radians(260)), color=mix((220, 150, 90), (130, 50, 50), m), w=0.035)
    p.circle((0, 0), 1.05, fill=woodd, outline=INK, w=0.02)
    for a in (0, 90, 180, 270):
        ar = math.radians(a)
        p.circle((1.115 * math.sin(ar), -1.115 * math.cos(ar)), 0.035, fill=mix(BRASS, (150, 60, 40), m), outline=INK, w=0.012)
    p.circle((0, 0), 1.0, fill=face, outline=INK, w=0.025)
    if m > 0.05:                                     # sickly blotches
        for bx, by, br in ((-0.55, 0.45, 0.2), (0.6, 0.3, 0.14), (0.35, -0.7, 0.12)):
            p.circle((bx, by), br, fill=rgba((140, 170, 70), 90 * m), outline=None, n=32)

    # ---- tick marks and numbers
    jit = seg(t, 8, 9) * (1 - 0.5 * seg(t, 10, 11))
    for i in range(60):
        a = i / 60 * TAU + (0.03 * math.sin(t * 41 + i) * jit)
        major = i % 5 == 0
        r1, r0 = 0.94, (0.82 if major else 0.89)
        p.line([(r0 * math.sin(a), -r0 * math.cos(a)), (r1 * math.sin(a), -r1 * math.cos(a))],
               color=ink_num, w=0.03 if major else 0.012, caps=False)
    fsize = 0.19 * k
    if fsize > 6:
        d = ImageDraw.Draw(img, "RGBA")
        f = font(fsize)
        for n in range(1, 13):
            a = n / 12 * TAU
            r = 0.68
            jx = 0.03 * math.sin(t * 33 + n * 1.7) * jit
            jy = 0.03 * math.cos(t * 29 + n) * jit + 0.12 * m * smooth(seg(t, 10 + n * 0.08, 11.5 + n * 0.08)) * (0.3 + 0.7 * (n % 3 == 0))
            sx, sy = fn(r * math.sin(a) + jx, -r * math.cos(a) + jy)
            d.text((sx, sy), str(n), font=f, fill=ink_num, anchor="mm")

    # ---- cracks
    cp = smooth(seg(t, 8.6, 10.2))
    if cp > 0:
        for c in CRACKS:
            cut = max(2, int(len(c) * cp + 0.5))
            p.line(c[:cut], color=INK, w=0.016)

    mn, hr, sc = hand_angles(t)

    # ---- motion smears while spinning
    if t < T_STOP + 0.05:
        pm, ph, ps_ = hand_angles(max(0, t - 1.0 / FPS))
        for a_now, a_prev, L, al in ((sc, ps_, 0.88, 35), (mn, pm, 0.78, 80), (hr, ph, 0.5, 90)):
            span = min(a_now - a_prev, TAU * 0.96)
            if span > 0.05:
                p.poly(sector(a_now - span, a_now, 0.06, L * 0.97), fill=(40, 30, 60, al), outline=None)

    # ---- mouth (closed grin from 12 s, opens from 14 s)
    mw = smooth(seg(t, 12.0, 12.5))
    if mw > 0:
        draw_mouth(img, fn, k, t, o, mw, None)

    # ---- the giant eye
    slit = smooth(seg(t, 8.8, 9.3))
    eo = 0.0 if t < 9.35 else back_out(seg(t, 9.35, 10.1), 2.2)
    if 12.9 < t < 13.25:
        eo *= abs(math.cos(math.pi * seg(t, 12.9, 13.25)))
    eo *= lerp(1, 0.7, smooth(seg(t, 14.0, 14.6)))
    draw_eye(img, fn, k, t, slit, eo, m)

    # ---- hands (become eyebrows)
    bp = back_out(seg(t, 9.7, 10.4), 1.4)
    bob = 0.07 * math.sin(t * 9) * seg(t, 10.4, 10.8)
    raise_ = smooth(seg(t, 14.0, 14.6))
    hand_col = mix(INK, (40, 6, 12), m)
    # hour hand -> left brow
    h_piv = (lerp(0, -0.1, bp), lerp(0, -0.52 - 0.06 * raise_, bp))
    h_ang = lerp(hr, -1.15 - bob - 0.25 * raise_, bp)
    p.poly(hand_pts(h_piv[0], h_piv[1], h_ang, lerp(0.5, 0.62, bp), lerp(0.045, 0.06, bp)),
           fill=hand_col, outline=hand_col, w=0.012)
    # minute hand -> right brow
    m_piv = (lerp(0, 0.1, bp), lerp(0, -0.52 - 0.06 * raise_, bp))
    m_ang = lerp(mn, 1.15 + bob + 0.25 * raise_, bp)
    p.poly(hand_pts(m_piv[0], m_piv[1], m_ang, lerp(0.78, 0.62, bp), lerp(0.035, 0.06, bp)),
           fill=hand_col, outline=hand_col, w=0.012)
    # second hand (falls off)
    if t < 11.2:
        piv = (0.0, 0.0)
        sa = sc
        if t > 9.5:
            dd = t - 9.5
            piv = (0.18 * dd, 3.6 * dd * dd)
            sa = sc + 4.5 * dd
        dx, dy = math.sin(sa), -math.cos(sa)
        p.line([(piv[0] - dx * 0.2, piv[1] - dy * 0.2), (piv[0] + dx * 0.88, piv[1] + dy * 0.88)],
               color=(206, 40, 40), w=0.014)
        p.circle((piv[0] - dx * 0.16, piv[1] - dy * 0.16), 0.04, fill=(206, 40, 40), outline=None, n=24)
    if slit < 0.05:
        p.circle((0, 0), 0.065, fill=INK, outline=None, n=32)
        p.circle((0, 0), 0.035, fill=BRASS, outline=None, n=32)

    # ---- glass glint
    glint = 1 - smooth(seg(t, 8, 9))
    if glint > 0:
        p.poly(sector(math.radians(-80), math.radians(-30), 0.8, 0.92, 20), fill=(255, 255, 255, int(70 * glint)), outline=None)
        p.poly(sector(math.radians(-25), math.radians(-15), 0.8, 0.92, 6), fill=(255, 255, 255, int(70 * glint)), outline=None)

    # ---- speed lines while spinning
    if 0.15 < t < T_STOP:
        r = random.Random(int(t * FPS))
        inten = seg(t, 0.15, 0.8)
        for _ in range(int(30 * inten)):
            a = r.uniform(0, TAU)
            r0 = r.uniform(1.28, 1.6)
            r1 = r0 + r.uniform(0.2, 0.55)
            p.line([(r0 * math.sin(a), -r0 * math.cos(a)), (r1 * math.sin(a), -r1 * math.cos(a))],
                   color=(255, 255, 240, 170), w=0.018)
    # impact burst at the stop
    if T_STOP <= t < T_STOP + 0.5:
        e = seg(t, T_STOP, T_STOP + 0.5)
        for i in range(16):
            a = i / 16 * TAU + 0.1
            r0 = 1.3 + 0.9 * e
            r1 = r0 + 0.45 * (1 - e)
            p.line([(r0 * math.sin(a), -r0 * math.cos(a)), (r1 * math.sin(a), -r1 * math.cos(a))],
                   color=(255, 230, 90, int(255 * (1 - e))), w=0.04)
    return pos, s


def draw_inside_jaws(img, t):
    """Overlay: jaws closing over the camera from top and bottom."""
    jp = ease_in(seg(t, 16.7, 17.3))
    if jp <= 0:
        return
    d = ImageDraw.Draw(img, "RGBA")
    S = SS

    def rect(x0, y0, x1, y1, fill):
        d.polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], fill=fill)
    half = H / 2
    top_edge = lerp(-260, half, jp)
    bot_edge = lerp(H + 260, half, jp)
    tw, tl = 135, 190
    gum = (150, 20, 44)
    # upper jaw
    rect(0, -10, W * S, (top_edge - 30) * S, (8, 0, 4))
    rect(0, (top_edge - 70) * S, W * S, top_edge * S, gum)
    for i in range(-1, 10):
        x = i * tw + tw / 2
        d.polygon([((x - tw / 2) * S, top_edge * S), ((x + tw / 2) * S, top_edge * S), (x * S, (top_edge + tl) * S)],
                  fill=TOOTH, outline=INK, width=6 * S)
    d.line([(0, top_edge * S), (W * S, top_edge * S)], fill=INK, width=6 * S)
    # lower jaw
    rect(0, (bot_edge + 30) * S, W * S, H * S + 10, (8, 0, 4))
    rect(0, bot_edge * S, W * S, (bot_edge + 70) * S, gum)
    for i in range(-1, 10):
        x = i * tw
        d.polygon([((x - tw / 2) * S, bot_edge * S), ((x + tw / 2) * S, bot_edge * S), (x * S, (bot_edge - tl) * S)],
                  fill=TOOTH, outline=INK, width=6 * S)
    d.line([(0, bot_edge * S), (W * S, bot_edge * S)], fill=INK, width=6 * S)


def render_frame(i):
    t = i / FPS
    m = smooth(seg(t, 8.0, 11.0))                    # "monster-ness"
    cam = camera(t)

    if t >= 17.3:
        out = Image.new("RGB", (W, H), (0, 0, 0))
    else:
        wall = mix(WALL_A, WALL_C, m)
        img = Image.new("RGB", (W * SS, H * SS), wall)
        draw_background(img, t, cam, m, (540, 860))
        draw_clock(img, t, cam, m)
        if t >= 15.3:                                # zoom lines during the lunge
            d = ImageDraw.Draw(img, "RGBA")
            r = random.Random(i * 13)
            inten = seg(t, 15.3, 15.8) * (1 - seg(t, 16.5, 16.9))
            for _ in range(int(40 * inten)):
                a = r.uniform(0, TAU)
                r0 = r.uniform(620, 900)
                r1 = r0 + r.uniform(250, 700)
                cx, cy = W / 2, H / 2
                d.line([((cx + r0 * math.cos(a)) * SS, (cy + r0 * math.sin(a)) * SS),
                        ((cx + r1 * math.cos(a)) * SS, (cy + r1 * math.sin(a)) * SS)],
                       fill=(255, 230, 230, 150), width=5 * SS)
        draw_inside_jaws(img, t)
        out = img.reduce(SS)

    # ---- post processing
    arr = np.asarray(out, dtype=np.float32)
    bright = 1.0
    if 7.2 < t < 8.7:                                # lights flicker
        r = random.Random(int(t * 12))
        if r.random() < 0.45:
            bright = r.uniform(0.35, 0.7)
    vig = 0.35 + 0.35 * m + 0.25 * seg(t, 14, 16.5)
    arr *= bright
    arr *= (1 - vig * VIG)
    flash = 0.0
    fcol = np.array([255, 255, 255], np.float32)
    if t >= T_STOP:
        flash = 0.85 * math.exp(-(t - T_STOP) * 12)
    if t >= 9.35 and t < 10.5:
        flash = max(flash, 0.55 * math.exp(-(t - 9.35) * 8))
        fcol = np.array([255, 40, 30], np.float32)
    if flash > 0.005:
        arr = arr * (1 - flash) + fcol * flash
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

    # ---- onomatopoeia
    if T_STOP <= t < 3.2:
        e = back_out(seg(t, T_STOP, T_STOP + 0.22), 2.5)
        stamp_text(out, "DONG!", 540, 270, 175 * e, (255, 214, 60), angle=-8,
                   alpha=1 - seg(t, 2.9, 3.2))
        stamp_text(out, "12:00", 540, 1640, 110 * e, (255, 255, 255), angle=3,
                   alpha=1 - seg(t, 2.9, 3.2))
    if 3.3 <= t < 8.0:
        n = int(math.floor(t - T_STOP))
        lt = (t - T_STOP) - n
        if n <= 5:
            word = ("tick", "tock")[(n - 1) % 2] if n < 5 else "kcit?"
            x = 860 if n % 2 else 220
            stamp_text(out, word, x, 1330 - 70 * lt, 80, (255, 250, 230), angle=10 if n % 2 else -10,
                       alpha=(1 - seg(lt, 0.5, 0.95)) * seg(lt, 0, 0.08))
    if 12.2 <= t < 13.8:
        a = seg(t, 12.2, 12.4) * (1 - seg(t, 13.4, 13.8))
        stamp_text(out, "GRRRR...", 540 + 6 * math.sin(t * 60), 1660 + 6 * math.cos(t * 47), 110,
                   (230, 40, 40), angle=-4, alpha=a)
    if 17.3 <= t < 17.75:
        e = back_out(seg(t, 17.3, 17.45), 2.5)
        stamp_text(out, "CHOMP!", 540, 960, 190 * e, (255, 255, 255), angle=-6,
                   alpha=1 - seg(t, 17.6, 17.75))
    if t >= 17.7:
        stamp_text(out, "gulp.", 540, 980, 90, (150, 20, 30), stroke=(0, 0, 0),
                   alpha=seg(t, 17.7, 17.85) * (1 - 0.6 * seg(t, 17.9, 18.0)))
    return out.tobytes()


# ------------------------------------------------------------------ audio
SR = 44100


def synth_audio(path):
    n = int(SR * DUR)
    buf = np.zeros(n, np.float64)
    rng = np.random.default_rng(3)

    def add(sig, start, gain=1.0):
        i0 = int(start * SR)
        if i0 >= n:
            return
        j = min(n, i0 + len(sig))
        buf[i0:j] += sig[: j - i0] * gain

    def tt(d):
        return np.arange(int(d * SR)) / SR

    def band(x, lo, hi):
        X = np.fft.rfft(x)
        f = np.fft.rfftfreq(len(x), 1 / SR)
        X[(f < lo) | (f > hi)] = 0
        return np.fft.irfft(X, len(x))

    def click(freq, d=0.03, decay=180):
        x = tt(d)
        return (np.sin(TAU * freq * x) * 0.7 + rng.normal(0, 0.3, len(x))) * np.exp(-x * decay)

    def thump(freq=55, d=0.5, decay=8):
        x = tt(d)
        f = freq * (1 + 1.5 * np.exp(-x * 30))
        return np.sin(TAU * np.cumsum(f) / SR) * np.exp(-x * decay)

    def saw(freq_arr):
        ph = np.cumsum(freq_arr) / SR
        return 2 * (ph % 1.0) - 1

    # 0-2.3 s  frantic ticking + whoosh
    tcur, k = 0.05, 0
    while tcur < T_STOP:
        rate = lerp(8, 45, clamp(tcur / 1.6))
        add(click(2600 if k % 2 else 1900), tcur, 0.35)
        tcur += 1 / rate
        k += 1
    x = tt(T_STOP)
    wh = band(rng.normal(0, 1, len(x)), 300, 3500)
    wh /= np.max(np.abs(wh)) + 1e-9
    spin_rate = lerp(2, 7, np.clip(x / 0.6, 0, 1))
    env = np.clip(x / 1.5, 0, 1) * (0.55 + 0.45 * np.sin(TAU * np.cumsum(spin_rate) / SR))
    add(wh * env, 0, 0.35)
    # 2.3 s  DONG
    x = tt(4.0)
    bell = np.zeros_like(x)
    for ratio, amp, dec in ((0.5, 0.5, 0.7), (1.0, 1.0, 0.9), (2.0, 0.6, 1.3), (2.4, 0.45, 1.8),
                            (3.0, 0.35, 2.2), (4.2, 0.25, 3.0), (5.4, 0.15, 4.0)):
        bell += amp * np.sin(TAU * 196 * ratio * x) * np.exp(-x * dec)
    bell *= np.minimum(1, x / 0.004)
    add(bell, T_STOP, 0.32)
    add(thump(60, 0.6, 7), T_STOP, 0.8)
    x = tt(0.6)
    add(np.sin(TAU * np.cumsum(320 + 120 * np.sin(TAU * 12 * x)) / SR) * np.exp(-x * 7), T_STOP + 0.03, 0.15)
    # 3-8 s  calm tick-tock (and one backward tick)
    for j, ts in enumerate((3.3, 4.3, 5.3, 6.3)):
        add(click(3000 if j % 2 == 0 else 1700, 0.05, 120), ts, 0.45)
        add(click(800, 0.05, 90), ts, 0.25)
    x = tt(0.25)
    add(click(900, 0.05, 60)[::-1], 7.3, 0.3)          # reversed "kcit"
    # flicker buzz
    x = tt(1.5)
    gate = np.repeat(rng.random(int(1.5 * 12) + 1) < 0.5, SR // 12 + 1)[: len(x)]
    add(saw(np.full(len(x), 120.0)) * gate * 0.5, 7.2, 0.12)
    # 8-14 s  drone, cracks, eye squelch, heartbeat, growl
    x = tt(10.0)
    drone = (saw(np.full(len(x), 55.0)) + saw(np.full(len(x), 55.6)) + 0.6 * saw(np.full(len(x), 82.6)))
    drone = band(drone, 30, 600)
    drone /= np.max(np.abs(drone)) + 1e-9
    denv = np.clip(x / 2.5, 0, 1) * (0.8 + 0.2 * np.sin(TAU * 0.7 * x))
    denv[x > 9.3] *= np.clip((10 - x[x > 9.3]) / 0.7, 0, 1)
    add(drone * denv, 8.0, 0.3)
    for ts in np.linspace(8.6, 10.1, 7):
        cr = band(rng.normal(0, 1, int(0.12 * SR)), 1500, 9000)
        add(cr / (np.max(np.abs(cr)) + 1e-9) * np.exp(-tt(0.12) * 30), ts + rng.uniform(-0.05, 0.05), 0.25)
    x = tt(0.7)
    sq = band(rng.normal(0, 1, len(x)), 200, 2000)
    sq = sq / (np.max(np.abs(sq)) + 1e-9) * np.exp(-x * 5) * 0.5
    sq += np.sin(TAU * np.cumsum(np.linspace(500, 90, len(x))) / SR) * np.exp(-x * 4)
    add(sq, 9.3, 0.4)
    add(thump(40, 1.2, 3), 9.35, 0.9)                 # stinger boom
    beat_t = 9.8
    while beat_t < 14.0:
        add(thump(48, 0.4, 10), beat_t, 0.5)
        add(thump(44, 0.4, 12), beat_t + 0.22, 0.35)
        beat_t += lerp(0.9, 0.55, clamp((beat_t - 9.8) / 4))
    x = tt(0.4)
    add(np.sin(TAU * 4200 * x) * np.exp(-x * 9) + 0.5 * np.sin(TAU * 6300 * x) * np.exp(-x * 12), 12.0, 0.12)
    x = tt(1.6)
    gr = saw(np.full(len(x), 72.0) + 6 * np.sin(TAU * 3 * x)) * (0.6 + 0.4 * np.sign(np.sin(TAU * 24 * x)))
    gr += band(rng.normal(0, 1, len(x)), 80, 700) * 0.6
    genv = np.sin(np.pi * np.clip(x / 1.6, 0, 1))
    add(band(gr, 40, 1200) * genv, 12.15, 0.55)
    # 14-18 s  creak, roar, lunge whoosh, CHOMP, gulp
    x = tt(1.0)
    add(saw(np.linspace(220, 70, len(x)) + 20 * np.sin(TAU * 18 * x)) * np.exp(-x * 1.2) * 0.6, 14.0, 0.25)
    x = tt(2.1)
    roar = saw(np.linspace(95, 55, len(x))) + 0.7 * saw(np.linspace(142, 80, len(x)))
    roar = roar * (0.7 + 0.3 * np.sin(TAU * 31 * x)) + band(rng.normal(0, 1, len(x)), 100, 2500) * 1.2
    roar = band(roar, 40, 2200)
    roar /= np.max(np.abs(roar)) + 1e-9
    renv = np.clip(x / 0.3, 0, 1) * np.clip((2.1 - x) / 0.2, 0, 1)
    add(roar * renv, 15.2, 0.6)
    x = tt(1.6)
    wh = band(rng.normal(0, 1, len(x)), 200, 5000)
    wh /= np.max(np.abs(wh)) + 1e-9
    add(wh * (x / 1.6) ** 2, 15.7, 0.35)
    add(thump(50, 0.8, 6), 17.3, 1.0)
    cr = band(rng.normal(0, 1, int(0.25 * SR)), 300, 6000)
    add(cr / (np.max(np.abs(cr)) + 1e-9) * np.exp(-tt(0.25) * 14), 17.3, 0.6)
    x = tt(0.35)
    add(np.sin(TAU * np.cumsum(np.linspace(340, 70, len(x))) / SR) * np.sin(np.pi * x / 0.35), 17.65, 0.45)
    add(click(2600, 0.04, 150), 17.92, 0.12)             # ...tick.

    buf = np.tanh(buf * 1.2)
    buf /= np.max(np.abs(buf)) + 1e-9
    buf *= 0.9
    fade = np.ones(n)
    fade[-int(0.03 * SR):] = np.linspace(1, 0, int(0.03 * SR))
    pcm = (buf * fade * 32767).astype(np.int16)
    stereo = np.stack([pcm, pcm], axis=1)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(stereo.tobytes())


# ------------------------------------------------------------------ main
def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "clock_monster.mp4")
    if len(sys.argv) > 2 and sys.argv[2] == "--stills":
        for ts in [float(v) for v in sys.argv[3:]]:
            Image.frombytes("RGB", (W, H), render_frame(int(ts * FPS))).save(f"{out}_{ts:05.2f}.png")
        return
    wav = out + ".wav"
    synth_audio(wav)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav,
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(os.cpu_count()) as pool:
        for j, frame in enumerate(pool.imap(render_frame, range(NF), chunksize=4)):
            proc.stdin.write(frame)
            if j % 60 == 0:
                print(f"frame {j}/{NF}", flush=True)
    proc.stdin.close()
    proc.wait()
    os.remove(wav)
    print("wrote", out)


if __name__ == "__main__":
    main()
