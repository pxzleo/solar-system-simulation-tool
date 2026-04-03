from __future__ import annotations

import argparse
import math
import os
import random
import sys
import time as pytime
from pathlib import Path
from typing import Any, Callable, Sequence, cast

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from panda3d.core import AlphaTestAttrib, Point2, Point3, SamplerState, Texture, TextureStage, TransparencyAttrib, loadPrcFileData
from ursina import AmbientLight, EditorCamera, Entity, Mesh, PointLight, Text, Ursina, Vec2, Vec3, application, camera, color, destroy, held_keys, invoke, lerp, load_texture, mouse, scene, window


ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent if not getattr(sys, 'frozen', False) else Path(sys.executable).resolve().parent))
ASSET_DIR = ROOT / 'assets'
RNG = random.Random(20260401)


def resolve_ui_font_reference() -> str:
    relative_candidates = [
        'msyh.ttc',
        'msyh.ttf',
        'OpenSans-Regular.ttf',
    ]
    candidate_paths = [
        ASSET_DIR / 'msyh.ttc',
        ASSET_DIR / 'msyh.ttf',
        ROOT / 'msyh.ttc',
        ROOT / 'msyh.ttf',
    ]
    windows_drive = os.environ.get('SystemDrive', 'C:')
    windows_dir = Path(f'{windows_drive}\\Windows')
    candidate_paths.extend([
        windows_dir / 'Fonts' / 'msyh.ttc',
        windows_dir / 'Fonts' / 'msyh.ttf',
        windows_dir / 'Fonts' / 'msyhbd.ttc',
    ])

    for candidate in relative_candidates:
        if (ASSET_DIR / candidate).exists() or (ROOT / candidate).exists():
            return candidate

    for candidate in candidate_paths:
        if candidate.exists():
            candidate_str = str(candidate)
            drive, tail = os.path.splitdrive(candidate_str)
            if drive:
                drive_letter = drive[0].lower()
                normalized_tail = tail.replace('\\', '/')
                return f'/{drive_letter}{normalized_tail}'
            return candidate.as_posix()
    return 'OpenSans-Regular.ttf'


def load_label_font(font_reference: str, size: int) -> Any:
    if font_reference.startswith('/') and len(font_reference) > 2 and font_reference[2] == '/':
        font_reference = f'{font_reference[1].upper()}:{font_reference[2:]}'
    reference_path = Path(font_reference)
    candidate_paths = [reference_path] if reference_path.is_absolute() else [ASSET_DIR / font_reference, ROOT / font_reference]

    for candidate in candidate_paths:
        if candidate.exists():
            try:
                return ImageFont.truetype(str(candidate), size)
            except OSError:
                continue

    try:
        return ImageFont.truetype(font_reference, size)
    except OSError:
        return ImageFont.load_default()


def clamp_channel(value: float, low: int = 0, high: int = 255) -> int:
    return max(low, min(high, int(value)))


def mix(c1: Sequence[int], c2: Sequence[int], t: float) -> tuple[int, int, int]:
    return (
        clamp_channel(c1[0] + (c2[0] - c1[0]) * t),
        clamp_channel(c1[1] + (c2[1] - c1[1]) * t),
        clamp_channel(c1[2] + (c2[2] - c1[2]) * t),
    )


def palette_color(palette: Sequence[Sequence[int]], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    if t <= 0:
        return int(palette[0][0]), int(palette[0][1]), int(palette[0][2])
    if t >= 1:
        return int(palette[-1][0]), int(palette[-1][1]), int(palette[-1][2])
    scaled = t * (len(palette) - 1)
    idx = int(scaled)
    frac = scaled - idx
    return mix(palette[idx], palette[idx + 1], frac)


def banded_texture(path: Path, palette: Sequence[Sequence[int]], seed: int, size: int = 768, storm: bool = False) -> None:
    if path.exists():
        return
    img = Image.new('RGBA', (size, size))
    pixels = img.load()
    if pixels is None:
        raise RuntimeError(f'Failed to create pixel access for {path}')
    phase = seed * 0.71
    for y in range(size):
        ny = y / size
        band = 0.5 + 0.28 * math.sin(ny * 12.0 * math.pi + phase)
        band += 0.14 * math.sin(ny * 26.0 * math.pi + phase * 0.3)
        band = max(0.0, min(1.0, band))
        for x in range(size):
            nx = x / size
            wave = 0.05 * math.sin(nx * 14.0 * math.pi + ny * 7.0 * math.pi + phase)
            wave += 0.03 * math.sin(nx * 36.0 * math.pi + phase * 1.7)
            color_rgb = palette_color(palette, max(0.0, min(1.0, band + wave)))
            shade = 0.9 + 0.1 * math.sin((nx + ny) * math.pi * 3.0 + phase)
            pixels[x, y] = (
                clamp_channel(color_rgb[0] * shade),
                clamp_channel(color_rgb[1] * shade),
                clamp_channel(color_rgb[2] * shade),
                255,
            )

    if storm:
        draw = ImageDraw.Draw(img, 'RGBA')
        cx = int(size * 0.72)
        cy = int(size * 0.58)
        draw.ellipse((cx - 70, cy - 38, cx + 70, cy + 38), fill=(210, 120, 90, 180))
        draw.ellipse((cx - 48, cy - 22, cx + 48, cy + 22), fill=(240, 160, 120, 220))

    img = img.filter(ImageFilter.GaussianBlur(radius=0.6))
    img.save(path)


def rocky_texture(path: Path, base_palette: Sequence[Sequence[int]], seed: int, size: int = 768, crater_count: int = 80, cloud_layer: bool = False) -> None:
    if path.exists():
        return
    rnd = random.Random(seed)
    img = Image.new('RGBA', (size, size))
    pixels = img.load()
    if pixels is None:
        raise RuntimeError(f'Failed to create pixel access for {path}')
    for y in range(size):
        ny = y / size
        for x in range(size):
            nx = x / size
            noise = 0.5 + 0.22 * math.sin(nx * 9.0 * math.pi + ny * 5.0 * math.pi + seed)
            noise += 0.18 * math.sin(nx * 23.0 * math.pi - ny * 11.0 * math.pi + seed * 0.37)
            noise += 0.08 * math.cos((nx + ny) * 17.0 * math.pi + seed * 0.11)
            noise = max(0.0, min(1.0, noise))
            rgb = palette_color(base_palette, noise)
            polar = 0.92 - abs(0.5 - ny) * 0.18
            pixels[x, y] = (
                clamp_channel(rgb[0] * polar),
                clamp_channel(rgb[1] * polar),
                clamp_channel(rgb[2] * polar),
                255,
            )

    draw = ImageDraw.Draw(img, 'RGBA')
    light_tone = palette_color(base_palette, 0.82)
    cloud_tone = palette_color(base_palette, 0.9)
    for _ in range(crater_count):
        r = rnd.randint(size // 70, size // 18)
        cx = rnd.randint(0, size)
        cy = rnd.randint(0, size)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(30, 20, 20, 255), width=max(1, r // 8))
        draw.ellipse((cx - r // 2, cy - r // 2, cx + r // 2, cy + r // 2), fill=(light_tone[0], light_tone[1], light_tone[2], 255))

    if cloud_layer:
        for _ in range(95):
            w = rnd.randint(size // 15, size // 7)
            h = rnd.randint(size // 28, size // 14)
            cx = rnd.randint(0, size)
            cy = rnd.randint(0, size)
            brightness = rnd.randint(-8, 10)
            draw.ellipse(
                (cx - w, cy - h, cx + w, cy + h),
                fill=(
                    clamp_channel(cloud_tone[0] + brightness),
                    clamp_channel(cloud_tone[1] + brightness),
                    clamp_channel(cloud_tone[2] + brightness),
                    255,
                ),
            )

    img = img.filter(ImageFilter.GaussianBlur(radius=0.8))
    img.save(path)


def earth_texture(path: Path, size: int = 1024) -> None:
    if path.exists():
        return
    img = Image.new('RGBA', (size, size), (20, 78, 150, 255))
    draw = ImageDraw.Draw(img, 'RGBA')

    for y in range(size):
        ny = y / size
        for x in range(size):
            nx = x / size
            ocean_noise = 0.6 + 0.16 * math.sin(nx * 14 * math.pi + ny * 3 * math.pi)
            ocean_noise += 0.09 * math.cos(nx * 30 * math.pi - ny * 9 * math.pi)
            ocean = (clamp_channel(18 + ocean_noise * 25), clamp_channel(68 + ocean_noise * 40), clamp_channel(145 + ocean_noise * 50), 255)
            img.putpixel((x, y), ocean)

    continents = [
        [(0.18, 0.34), (0.28, 0.22), (0.34, 0.36), (0.28, 0.52), (0.16, 0.48)],
        [(0.53, 0.22), (0.69, 0.18), (0.76, 0.31), (0.69, 0.46), (0.56, 0.44), (0.48, 0.31)],
        [(0.57, 0.58), (0.67, 0.55), (0.72, 0.65), (0.66, 0.82), (0.55, 0.78), (0.51, 0.67)],
        [(0.82, 0.71), (0.89, 0.74), (0.86, 0.83), (0.79, 0.79)],
    ]
    for poly in continents:
        scaled = [(x * size, y * size) for x, y in poly]
        draw.polygon(scaled, fill=(62, 128, 66, 255))
        for _ in range(25):
            cx, cy = scaled[RNG.randrange(len(scaled))]
            draw.ellipse((cx - 18, cy - 12, cx + 18, cy + 12), fill=(86, 144, 74, 180))

    for _ in range(130):
        w = RNG.randint(size // 28, size // 12)
        h = RNG.randint(size // 48, size // 24)
        cx = RNG.randint(0, size)
        cy = RNG.randint(0, size)
        draw.ellipse((cx - w, cy - h, cx + w, cy + h), fill=(255, 255, 255, RNG.randint(28, 72)))

    img = img.filter(ImageFilter.GaussianBlur(radius=0.9))
    img.save(path)


def earth_clouds_texture(path: Path, size: int = 1024) -> None:
    if path.exists():
        return
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, 'RGBA')
    rnd = random.Random(2201)

    for _ in range(240):
        w = rnd.randint(size // 30, size // 11)
        h = rnd.randint(size // 45, size // 18)
        cx = rnd.randint(0, size)
        cy = rnd.randint(0, size)
        alpha = rnd.randint(18, 92)
        draw.ellipse((cx - w, cy - h, cx + w, cy + h), fill=(255, 255, 255, alpha))

    for _ in range(80):
        x1 = rnd.randint(0, size)
        y1 = rnd.randint(0, size)
        x2 = x1 + rnd.randint(size // 20, size // 8)
        y2 = y1 + rnd.randint(-size // 40, size // 40)
        draw.line((x1, y1, x2, y2), fill=(255, 255, 255, rnd.randint(18, 48)), width=rnd.randint(4, 10))

    img = img.filter(ImageFilter.GaussianBlur(radius=3.2))
    img.save(path)


def earth_night_texture(path: Path, size: int = 1024) -> None:
    if path.exists():
        return
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, 'RGBA')
    rnd = random.Random(3307)

    city_bands = [
        (0.22, 0.24, 0.34, 0.42),
        (0.50, 0.20, 0.72, 0.34),
        (0.54, 0.50, 0.72, 0.70),
        (0.18, 0.56, 0.30, 0.72),
    ]
    for left, top, right, bottom in city_bands:
        for _ in range(320):
            x = rnd.randint(int(left * size), int(right * size))
            y = rnd.randint(int(top * size), int(bottom * size))
            radius = rnd.randint(1, 3)
            glow = rnd.randint(90, 180)
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(255, 210, 110, glow))

    for _ in range(80):
        x1 = rnd.randint(0, size)
        y1 = rnd.randint(0, size)
        x2 = x1 + rnd.randint(size // 40, size // 10)
        draw.line((x1, y1, x2, y1 + rnd.randint(-3, 3)), fill=(255, 190, 90, rnd.randint(32, 85)), width=rnd.randint(1, 3))

    img = img.filter(ImageFilter.GaussianBlur(radius=1.8))
    img.save(path)


def nebula_texture(path: Path, size: int = 2048) -> None:
    if path.exists():
        return
    img = Image.new('RGBA', (size, size), (4, 6, 14, 255))
    draw = ImageDraw.Draw(img, 'RGBA')
    rnd = random.Random(4104)

    for y in range(size):
        for x in range(size):
            nx = x / size
            ny = y / size
            base = 0.24 + 0.12 * math.sin(nx * 5.4 * math.pi) + 0.08 * math.cos(ny * 4.8 * math.pi)
            dust = 0.06 * math.sin((nx + ny) * 12.0 * math.pi) + 0.04 * math.cos((nx - ny) * 17.0 * math.pi)
            shade = max(0.0, min(1.0, base + dust))
            img.putpixel((x, y), (
                clamp_channel(5 + shade * 16),
                clamp_channel(7 + shade * 22),
                clamp_channel(16 + shade * 44),
                255,
            ))

    for palette in [
        ((80, 120, 255, 16), (60, 40, 160, 0)),
        ((200, 70, 150, 12), (100, 40, 110, 0)),
        ((90, 180, 220, 10), (40, 80, 120, 0)),
    ]:
        for _ in range(8):
            cx = rnd.randint(size // 8, size - size // 8)
            cy = rnd.randint(size // 8, size - size // 8)
            rx = rnd.randint(size // 10, size // 4)
            ry = rnd.randint(size // 14, size // 5)
            draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=palette[0])

    for _ in range(1500):
        x = rnd.randint(0, size - 1)
        y = rnd.randint(0, size - 1)
        alpha = rnd.randint(120, 255)
        color_shift = rnd.randint(-20, 30)
        img.putpixel((x, y), (
            clamp_channel(220 + color_shift),
            clamp_channel(225 + color_shift),
            clamp_channel(255),
            alpha,
        ))

    img = img.filter(ImageFilter.GaussianBlur(radius=1.2))
    img.save(path)


def sun_texture(path: Path, size: int = 1024) -> None:
    if path.exists():
        return
    img = Image.new('RGBA', (size, size))
    pixels = img.load()
    if pixels is None:
        raise RuntimeError(f'Failed to create pixel access for {path}')
    center = size / 2.0
    for y in range(size):
        for x in range(size):
            dx = (x - center) / center
            dy = (y - center) / center
            r = math.sqrt(dx * dx + dy * dy)
            swirl = 0.5 + 0.25 * math.sin((math.atan2(dy, dx) * 6.0) + r * 16.0)
            turbulence = 0.12 * math.sin(dx * 22.0 + dy * 19.0) + 0.08 * math.sin(dx * 41.0 - dy * 33.0)
            heat = max(0.0, min(1.0, 1.0 - r * 0.95 + swirl * 0.22 + turbulence))
            outer = max(0.0, 1.0 - r)
            red = clamp_channel(180 + heat * 75)
            green = clamp_channel(70 + heat * 125)
            blue = clamp_channel(10 + outer * 40)
            pixels[x, y] = (red, green, blue, 255)
    img = img.filter(ImageFilter.GaussianBlur(radius=1.3))
    img.save(path)


def radial_glow(path: Path, core_color: Sequence[int], edge_color: Sequence[int], size: int = 1024) -> None:
    if path.exists():
        return
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    pixels = img.load()
    if pixels is None:
        raise RuntimeError(f'Failed to create pixel access for {path}')
    center = size / 2.0
    for y in range(size):
        for x in range(size):
            dx = (x - center) / center
            dy = (y - center) / center
            r = min(1.0, math.sqrt(dx * dx + dy * dy))
            alpha = (1.0 - r) ** 2.4
            rgb = mix(core_color, edge_color, r)
            pixels[x, y] = (rgb[0], rgb[1], rgb[2], clamp_channel(alpha * 255))
    img.save(path)


def saturn_ring(path: Path, size: int = 1024) -> None:
    if path.exists():
        return
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    pixels = img.load()
    if pixels is None:
        raise RuntimeError(f'Failed to create pixel access for {path}')
    center = size / 2.0
    for y in range(size):
        for x in range(size):
            dx = (x - center) / center
            dy = (y - center) / center
            r = math.sqrt(dx * dx + dy * dy)
            if 0.35 < r < 0.92:
                bands = 0.65 + 0.25 * math.sin(r * 80.0)
                alpha = 0.75 * (1.0 - abs(r - 0.63) / 0.29)
                pixels[x, y] = (
                    clamp_channel(190 + bands * 38),
                    clamp_channel(170 + bands * 26),
                    clamp_channel(130 + bands * 20),
                    clamp_channel(alpha * 255),
                )
    img = img.filter(ImageFilter.GaussianBlur(radius=1.0))
    img.save(path)


def saturn_ring_back(path: Path, size: int = 1024) -> None:
    if path.exists():
        return
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    pixels = img.load()
    if pixels is None:
        raise RuntimeError(f'Failed to create pixel access for {path}')
    center = size / 2.0
    for y in range(size):
        for x in range(size):
            dx = (x - center) / center
            dy = (y - center) / center
            r = math.sqrt(dx * dx + dy * dy)
            if 0.34 < r < 0.94:
                bands = 0.55 + 0.22 * math.sin(r * 72.0 + 0.8)
                fade = max(0.0, 1.0 - abs(r - 0.67) / 0.31)
                pixels[x, y] = (
                    clamp_channel(125 + bands * 30),
                    clamp_channel(112 + bands * 24),
                    clamp_channel(92 + bands * 18),
                    clamp_channel(fade * 115),
                )
    img = img.filter(ImageFilter.GaussianBlur(radius=1.6))
    img.save(path)


def selection_bracket_texture(path: Path, size: int = 512) -> None:
    if path.exists():
        return
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, 'RGBA')
    margin = int(size * 0.17)
    inner = int(size * 0.11)
    thickness = max(3, int(size * 0.012))
    color_rgba = (110, 235, 255, 190)

    # top-left
    draw.rectangle((margin, margin, margin + inner, margin + thickness), fill=color_rgba)
    draw.rectangle((margin, margin, margin + thickness, margin + inner), fill=color_rgba)
    # top-right
    draw.rectangle((size - margin - inner, margin, size - margin, margin + thickness), fill=color_rgba)
    draw.rectangle((size - margin - thickness, margin, size - margin, margin + inner), fill=color_rgba)
    # bottom-left
    draw.rectangle((margin, size - margin - thickness, margin + inner, size - margin), fill=color_rgba)
    draw.rectangle((margin, size - margin - inner, margin + thickness, size - margin), fill=color_rgba)
    # bottom-right
    draw.rectangle((size - margin - inner, size - margin - thickness, size - margin, size - margin), fill=color_rgba)
    draw.rectangle((size - margin - thickness, size - margin - inner, size - margin, size - margin), fill=color_rgba)

    img = img.filter(ImageFilter.GaussianBlur(radius=size * 0.002))
    img.save(path)


def ensure_assets():
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    nebula_texture(ASSET_DIR / 'deep_space.png')
    sun_texture(ASSET_DIR / 'sun.png')
    radial_glow(ASSET_DIR / 'sun_glow.png', (255, 214, 110), (255, 92, 0))
    radial_glow(ASSET_DIR / 'halo.png', (255, 245, 210), (255, 128, 0))
    selection_bracket_texture(ASSET_DIR / 'selection_bracket.png')
    saturn_ring(ASSET_DIR / 'saturn_ring.png')
    saturn_ring_back(ASSET_DIR / 'saturn_ring_back.png')

    rocky_texture(ASSET_DIR / 'mercury.png', [(64, 62, 58), (114, 108, 103), (155, 149, 145)], 1)
    rocky_texture(ASSET_DIR / 'venus.png', [(145, 110, 54), (189, 145, 72), (222, 196, 126)], 2, crater_count=20, cloud_layer=True)
    earth_texture(ASSET_DIR / 'earth.png')
    earth_clouds_texture(ASSET_DIR / 'earth_clouds.png')
    earth_night_texture(ASSET_DIR / 'earth_night.png')
    rocky_texture(ASSET_DIR / 'moon.png', [(82, 82, 84), (118, 118, 120), (166, 166, 170)], 3, crater_count=120)
    rocky_texture(ASSET_DIR / 'mars.png', [(94, 42, 24), (156, 80, 50), (202, 118, 72)], 4, crater_count=55)
    rocky_texture(ASSET_DIR / 'phobos.png', [(58, 54, 50), (102, 96, 90), (132, 126, 120)], 5, crater_count=60)
    rocky_texture(ASSET_DIR / 'deimos.png', [(75, 71, 68), (118, 112, 108), (152, 146, 138)], 6, crater_count=48)

    banded_texture(ASSET_DIR / 'jupiter.png', [(128, 82, 58), (201, 146, 104), (230, 196, 160), (164, 110, 84)], 7, storm=True)
    banded_texture(ASSET_DIR / 'saturn.png', [(160, 140, 88), (208, 188, 136), (232, 218, 175), (173, 152, 112)], 8)
    banded_texture(ASSET_DIR / 'uranus.png', [(128, 180, 190), (158, 214, 222), (196, 240, 242)], 9)
    banded_texture(ASSET_DIR / 'neptune.png', [(32, 58, 132), (46, 92, 188), (90, 144, 234)], 10)
    rocky_texture(ASSET_DIR / 'io.png', [(182, 132, 60), (218, 184, 96), (226, 210, 120)], 11, crater_count=28)
    rocky_texture(ASSET_DIR / 'europa.png', [(168, 140, 104), (216, 198, 166), (238, 228, 198)], 12, crater_count=22)
    rocky_texture(ASSET_DIR / 'ganymede.png', [(86, 70, 58), (142, 118, 96), (190, 168, 138)], 13, crater_count=52)
    rocky_texture(ASSET_DIR / 'callisto.png', [(72, 58, 48), (124, 96, 78), (165, 138, 114)], 14, crater_count=64)
    rocky_texture(ASSET_DIR / 'titan.png', [(140, 102, 52), (190, 152, 86), (224, 194, 124)], 15, crater_count=15, cloud_layer=True)
    rocky_texture(ASSET_DIR / 'rhea.png', [(116, 108, 102), (164, 156, 148), (210, 204, 198)], 16, crater_count=50)
    rocky_texture(ASSET_DIR / 'titania.png', [(124, 140, 152), (174, 194, 204), (224, 240, 246)], 17, crater_count=45)
    rocky_texture(ASSET_DIR / 'triton.png', [(116, 140, 160), (154, 182, 200), (212, 228, 238)], 18, crater_count=36)


def selection_label_texture(text: str, font_path: str) -> Path:
    safe_name = ''.join(ch if ch.isalnum() else '_' for ch in text) or 'label'
    output_path = ASSET_DIR / f'selection_label_{safe_name}.png'

    canvas_width = 320
    canvas_height = 88
    img = Image.new('RGBA', (canvas_width, canvas_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, 'RGBA')
    draw.rounded_rectangle((6, 10, canvas_width - 6, canvas_height - 10), radius=18, fill=(10, 16, 26, 170), outline=(96, 220, 255, 80), width=2)
    try:
        font = load_label_font(font_path, 40)
    except OSError:
        font = ImageFont.load_default()
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    text_x = (canvas_width - text_width) // 2
    text_y = (canvas_height - text_height) // 2 - 4
    draw.text((text_x + 2, text_y + 2), text, font=font, fill=(0, 0, 0, 165))
    draw.text((text_x, text_y), text, font=font, fill=(120, 235, 255, 255))
    img.save(output_path)
    return output_path

def pick_texture(preferred_real: str, fallback_generated: str):
    real_path = ASSET_DIR / preferred_real
    if real_path.exists():
        return f'assets/{preferred_real}'
    return f'assets/{fallback_generated}'


def orbit_mesh(radius: float, segments: int = 160, eccentricity: float = 0.0) -> Mesh:
    vertices = []
    semi_major = radius
    semi_minor = radius * math.sqrt(max(0.0, 1.0 - eccentricity * eccentricity))
    focus_offset = semi_major * eccentricity
    for i in range(segments + 1):
        angle = (i / segments) * math.tau
        vertices.append(Vec3(math.cos(angle) * semi_major - focus_offset, 0, math.sin(angle) * semi_minor))
    return Mesh(vertices=vertices, mode='line', thickness=1, static=True)


PLANET_ORBIT_THICKNESS = 2
MOON_ORBIT_THICKNESS = 1


def scaled_orbit_speed(period_days: float, earth_speed: float = 10.0, exponent: float = 0.45) -> float:
    return earth_speed * ((365.256 / period_days) ** exponent)


def scaled_spin_speed(period_hours: float, earth_speed: float = 42.0, exponent: float = 0.3, retrograde: bool = False) -> float:
    speed = earth_speed * ((23.934 / abs(period_hours)) ** exponent)
    return speed if retrograde else -speed


def scaled_moon_orbit_speed(period_days: float, base_period_days: float = 27.321661, base_speed: float = 20.0, exponent: float = 0.35) -> float:
    return base_speed * ((base_period_days / period_days) ** exponent)


def projected_on_plane(vector: Vec3, normal: Vec3) -> Vec3:
    return vector - normal * vector.dot(normal)


def compute_spin_axis_heading(alpha_deg: float, delta_deg: float, orbit_normal: Vec3) -> float:
    alpha = math.radians(alpha_deg)
    delta = math.radians(delta_deg)
    pole_vector = Vec3(
        math.cos(delta) * math.cos(alpha),
        math.sin(delta),
        math.cos(delta) * math.sin(alpha),
    )
    plane_normal = orbit_normal.normalized()
    projected_pole = projected_on_plane(pole_vector, plane_normal)
    if projected_pole.length() < 1e-4:
        return 0.0
    projected_pole = projected_pole.normalized()

    reference_x = projected_on_plane(Vec3(1, 0, 0), plane_normal)
    if reference_x.length() < 1e-4:
        reference_x = projected_on_plane(Vec3(0, 0, 1), plane_normal)
    reference_x = reference_x.normalized()
    reference_y = plane_normal.cross(reference_x).normalized()
    heading = math.degrees(math.atan2(projected_pole.dot(reference_y), projected_pole.dot(reference_x)))
    return heading % 360.0


VISUAL_SCALE = {
    'sun_body_scale_factor': 0.00001,
    'planet_radius_factor': 1.35,
    'moon_radius_factor': 1.0,
    'min_planet_radius': 0.72,
    'min_moon_radius': 0.05,
    'planet_distance_factor': 19.0,
    'moon_distance_factor': 2.2,
    'planet_distance_exponent': 0.42,
    'moon_distance_exponent': 0.36,
}


PLANET_DATA: dict[str, dict[str, Any]] = {
    'Mercury': {'texture': lambda: pick_texture('mercury_real.jpg', 'mercury.png'), 'orbit_speed_days': 87.969, 'spin_hours': 1407.6, 'tilt': 0.03, 'orbit_tilt': 7.0, 'orbit_phase': 48, 'eccentricity': 0.2056, 'retrograde_spin': False, 'pole_ra': 281.01, 'pole_dec': 61.45},
    'Venus': {'texture': lambda: pick_texture('venus_real.jpg', 'venus.png'), 'orbit_speed_days': 224.701, 'spin_hours': 5832.5, 'tilt': 2.7, 'orbit_tilt': 3.4, 'orbit_phase': 92, 'eccentricity': 0.0068, 'retrograde_spin': True, 'pole_ra': 272.76, 'pole_dec': 67.16},
    'Earth': {'texture': lambda: pick_texture('earth_real.jpg', 'earth.png'), 'orbit_speed_days': 365.256, 'spin_hours': 23.934, 'tilt': 23.44, 'orbit_tilt': 0.0, 'orbit_phase': 140, 'eccentricity': 0.0167, 'retrograde_spin': False, 'pole_ra': 0.0, 'pole_dec': 90.0},
    'Mars': {'texture': lambda: pick_texture('mars_real.jpg', 'mars.png'), 'orbit_speed_days': 686.98, 'spin_hours': 24.623, 'tilt': 25.19, 'orbit_tilt': 1.85, 'orbit_phase': 210, 'eccentricity': 0.0934, 'retrograde_spin': False, 'pole_ra': 317.68, 'pole_dec': 52.89},
    'Jupiter': {'texture': lambda: pick_texture('jupiter_real.jpg', 'jupiter.png'), 'orbit_speed_days': 4332.59, 'spin_hours': 9.93, 'tilt': 3.13, 'orbit_tilt': 1.3, 'orbit_phase': 280, 'eccentricity': 0.0489, 'retrograde_spin': False, 'pole_ra': 268.06, 'pole_dec': 64.5},
    'Saturn': {'texture': lambda: pick_texture('saturn_real.jpg', 'saturn.png'), 'orbit_speed_days': 10759.22, 'spin_hours': 10.66, 'tilt': 26.7, 'orbit_tilt': 2.5, 'orbit_phase': 320, 'eccentricity': 0.0565, 'retrograde_spin': False, 'pole_ra': 40.72, 'pole_dec': 83.54},
    'Uranus': {'texture': lambda: pick_texture('uranus_real.jpg', 'uranus.png'), 'orbit_speed_days': 30688.5, 'spin_hours': 17.24, 'tilt': 97.77, 'orbit_tilt': 0.77, 'orbit_phase': 18, 'eccentricity': 0.0463, 'retrograde_spin': True, 'pole_ra': 257.31, 'pole_dec': -15.17},
    'Neptune': {'texture': lambda: pick_texture('neptune_real.jpg', 'neptune.png'), 'orbit_speed_days': 60182.0, 'spin_hours': 16.11, 'tilt': 28.32, 'orbit_tilt': 1.77, 'orbit_phase': 70, 'eccentricity': 0.0086, 'retrograde_spin': False, 'pole_ra': 299.36, 'pole_dec': -8.93},
}


PLANET_REAL: dict[str, dict[str, float]] = {
    'Sun': {'radius_km': 696340.0, 'orbit_au': 0.0},
    'Mercury': {'radius_km': 2439.4, 'orbit_au': 0.387098},
    'Venus': {'radius_km': 6051.8, 'orbit_au': 0.723332},
    'Earth': {'radius_km': 6371.0084, 'orbit_au': 1.0},
    'Mars': {'radius_km': 3389.5, 'orbit_au': 1.523679},
    'Jupiter': {'radius_km': 69911.0, 'orbit_au': 5.203366},
    'Saturn': {'radius_km': 58232.0, 'orbit_au': 9.53707},
    'Uranus': {'radius_km': 25362.0, 'orbit_au': 19.191281},
    'Neptune': {'radius_km': 24622.0, 'orbit_au': 30.068923},
}


MOON_DATA: dict[str, dict[str, Any]] = {
    'Moon': {'texture': lambda: pick_texture('moon_real.jpg', 'moon.png'), 'period_days': 27.321661, 'spin_hours': 27.321661 * 24.0 * 0.1, 'retrograde_spin': False, 'tilt': 1.5, 'orbit_tilt': 5.1, 'eccentricity': 0.0549, 'orbit_color': color.rgba(85, 100, 150, 80), 'orbit_phase': 35, 'synchronous_lock': True, 'texture_rotation_y': 180.0},
    'Phobos': {'texture': lambda: pick_texture('phobos_real.jpg', 'phobos.png'), 'period_days': 0.31891, 'spin_hours': 0.31891 * 24.0, 'retrograde_spin': False, 'tilt': 0.0, 'orbit_tilt': 1.1, 'orbit_phase': 10, 'eccentricity': 0.0151, 'orbit_color': color.rgba(120, 85, 65, 80)},
    'Deimos': {'texture': lambda: pick_texture('deimos_real.jpg', 'deimos.png'), 'period_days': 1.26244, 'spin_hours': 1.26244 * 24.0, 'retrograde_spin': False, 'tilt': 0.0, 'orbit_tilt': 1.5, 'orbit_phase': 200, 'eccentricity': 0.0002, 'orbit_color': color.rgba(120, 85, 65, 80)},
    'Io': {'texture': lambda: pick_texture('io_real.jpg', 'io.png'), 'period_days': 1.769, 'spin_hours': 1.769 * 24.0, 'retrograde_spin': False, 'tilt': 0.0, 'orbit_tilt': 0.04, 'orbit_phase': 40, 'eccentricity': 0.0041, 'orbit_color': color.rgba(135, 120, 80, 80)},
    'Europa': {'texture': lambda: pick_texture('europa_real.jpg', 'europa.png'), 'period_days': 3.551, 'spin_hours': 3.551 * 24.0, 'retrograde_spin': False, 'tilt': 0.0, 'orbit_tilt': 0.1, 'orbit_phase': 120, 'eccentricity': 0.0094, 'orbit_color': color.rgba(120, 125, 150, 80)},
    'Ganymede': {'texture': lambda: pick_texture('ganymede_real.jpg', 'ganymede.png'), 'period_days': 7.155, 'spin_hours': 7.155 * 24.0, 'retrograde_spin': False, 'tilt': 0.0, 'orbit_tilt': 0.3, 'orbit_phase': 210, 'eccentricity': 0.0013, 'orbit_color': color.rgba(110, 100, 88, 80)},
    'Callisto': {'texture': lambda: pick_texture('callisto_real.jpg', 'callisto.png'), 'period_days': 16.689, 'spin_hours': 16.689 * 24.0, 'retrograde_spin': False, 'tilt': 0.0, 'orbit_tilt': 0.3, 'orbit_phase': 300, 'eccentricity': 0.0074, 'orbit_color': color.rgba(100, 90, 82, 80)},
    'Titan': {'texture': lambda: pick_texture('titan_real.jpg', 'titan.png'), 'period_days': 15.945, 'spin_hours': 15.945 * 24.0, 'retrograde_spin': False, 'tilt': 0.0, 'orbit_tilt': 0.3, 'orbit_phase': 60, 'eccentricity': 0.0288, 'orbit_color': color.rgba(130, 112, 80, 80)},
    'Rhea': {'texture': lambda: pick_texture('rhea_real.jpg', 'rhea.png'), 'period_days': 4.518, 'spin_hours': 4.518 * 24.0, 'retrograde_spin': False, 'tilt': 0.0, 'orbit_tilt': 0.3, 'orbit_phase': 250, 'eccentricity': 0.0010, 'orbit_color': color.rgba(110, 110, 115, 80)},
    'Titania': {'texture': lambda: pick_texture('titania_real.jpg', 'titania.png'), 'period_days': 8.706, 'spin_hours': 8.706 * 24.0, 'retrograde_spin': False, 'tilt': 0.0, 'orbit_tilt': 0.25, 'orbit_phase': 135, 'eccentricity': 0.0011, 'orbit_color': color.rgba(85, 120, 140, 80)},
    'Triton': {'texture': lambda: pick_texture('triton_real.jpg', 'triton.png'), 'period_days': 5.877, 'spin_hours': 5.877 * 24.0, 'retrograde_spin': True, 'tilt': 0.0, 'orbit_tilt': 156.8, 'orbit_phase': 45, 'eccentricity': 0.0, 'orbit_color': color.rgba(70, 95, 140, 80), 'retrograde_orbit': True},
}


MOON_REAL: dict[str, dict[str, Any]] = {
    'Moon': {'parent': 'Earth', 'radius_km': 1737.4, 'semi_major_axis_km': 384400.0},
    'Phobos': {'parent': 'Mars', 'radius_km': 11.1, 'semi_major_axis_km': 9376.0},
    'Deimos': {'parent': 'Mars', 'radius_km': 6.2, 'semi_major_axis_km': 23460.0},
    'Io': {'parent': 'Jupiter', 'radius_km': 1821.6, 'semi_major_axis_km': 421700.0},
    'Europa': {'parent': 'Jupiter', 'radius_km': 1560.8, 'semi_major_axis_km': 671000.0},
    'Ganymede': {'parent': 'Jupiter', 'radius_km': 2634.1, 'semi_major_axis_km': 1070000.0},
    'Callisto': {'parent': 'Jupiter', 'radius_km': 2410.3, 'semi_major_axis_km': 1882700.0},
    'Titan': {'parent': 'Saturn', 'radius_km': 2575.0, 'semi_major_axis_km': 1221870.0},
    'Rhea': {'parent': 'Saturn', 'radius_km': 764.0, 'semi_major_axis_km': 527108.0},
    'Titania': {'parent': 'Uranus', 'radius_km': 789.4, 'semi_major_axis_km': 435910.0},
    'Triton': {'parent': 'Neptune', 'radius_km': 1353.4, 'semi_major_axis_km': 354800.0},
}


def scaled_body_radius(real_radius_km: float, factor: float) -> float:
    return real_radius_km * factor


def scaled_visual_radius(real_radius_km: float, factor: float, minimum: float) -> float:
    return max(minimum, math.sqrt(real_radius_km) * factor / 100.0)


def scaled_distance_km(real_distance_km: float, factor: float) -> float:
    return real_distance_km * factor


def scaled_planet_distance(orbit_au: float, factor: float, exponent: float) -> float:
    return (max(orbit_au, 0.0) ** exponent) * factor


def scaled_moon_distance(semi_major_axis_km: float, factor: float, exponent: float, base_distance_km: float = 384400.0) -> float:
    relative_distance = max(semi_major_axis_km, 1.0) / base_distance_km
    return (relative_distance ** exponent) * factor


def au_to_km(au: float) -> float:
    return au * 149_597_870.7


def soften_texture_edges(entity: Entity, *, repeat: bool = True, transparent_border: bool = False) -> None:
    if not hasattr(entity, 'model') or not entity.model:
        return
    if not hasattr(entity.model, 'setTexGen'):
        return
    texture = entity.texture
    if texture is None:
        return
    if repeat:
        texture.wrap_u = Texture.WM_repeat
        texture.wrap_v = Texture.WM_repeat
    if transparent_border:
        texture.wrap_u = Texture.WM_border_color
        texture.wrap_v = Texture.WM_border_color
        texture.border_color = (0.0, 0.0, 0.0, 0.0)
    texture.minfilter = SamplerState.FT_linear_mipmap_linear
    texture.magfilter = SamplerState.FT_linear
    texture.anisotropic_degree = 8


class OrbitalBody:
    def __init__(
        self,
        name: str,
        texture: str,
        distance: float,
        radius: float,
        orbit_speed: float,
        spin_speed: float,
        tilt: float = 0,
        orbit_tilt: float = 0,
        orbit_phase: float = 0,
        spin_axis_heading: float = 0,
        eccentricity: float = 0,
        parent=scene,
        orbit_color=color.rgba(90, 110, 140, 80),
        orbit_thickness: int = PLANET_ORBIT_THICKNESS,
        orbit_y: float = 0,
    ) -> None:
        self.name = name
        self.distance = distance
        self.orbit_speed = orbit_speed
        self.spin_speed = spin_speed
        self.eccentricity = eccentricity
        self.mean_anomaly = 0.0
        self.orbit_plane = Entity(parent=parent, rotation=(orbit_tilt, orbit_phase, 0), y=orbit_y)
        self.pivot = Entity(parent=self.orbit_plane, rotation_y=0)
        self.anchor = Entity(parent=self.pivot, x=distance)
        self.axis_heading = Entity(parent=self.anchor, rotation_y=spin_axis_heading)
        self.axis_tilt = Entity(parent=self.axis_heading, rotation_z=tilt)
        self.spin_pivot = Entity(parent=self.axis_tilt, rotation_y=0)
        self.visual_root = Entity(parent=self.spin_pivot)
        self.body = Entity(
            parent=self.visual_root,
            model='sphere',
            texture=texture,
            scale=radius,
            collider='sphere',
        )
        self.body.orbital_body = self
        soften_texture_edges(self.body, repeat=True)
        self.orbit = None
        self.moons = []
        if distance > 0:
            self.orbit = Entity(parent=self.orbit_plane, model=orbit_mesh(distance, eccentricity=eccentricity), texture='assets/orbit_light.png', color=orbit_color)
            if hasattr(self.orbit.model, 'thickness'):
                self.orbit.model.thickness = orbit_thickness

    def add_moon(self, moon: OrbitalBody) -> None:
        self.moons.append(moon)

    def update(self, dt: float, speed: float) -> None:
        if self.distance > 0:
            self.mean_anomaly = (self.mean_anomaly + math.radians(self.orbit_speed * dt * speed)) % math.tau
            eccentric_anomaly = self.mean_anomaly
            for _ in range(5):
                eccentric_anomaly -= (eccentric_anomaly - self.eccentricity * math.sin(eccentric_anomaly) - self.mean_anomaly) / max(0.2, 1.0 - self.eccentricity * math.cos(eccentric_anomaly))
            true_anomaly = 2.0 * math.atan2(
                math.sqrt(1.0 + self.eccentricity) * math.sin(eccentric_anomaly / 2.0),
                math.sqrt(max(1e-6, 1.0 - self.eccentricity)) * math.cos(eccentric_anomaly / 2.0),
            )
            orbital_radius = self.distance * (1.0 - self.eccentricity * math.cos(eccentric_anomaly))
            self.pivot.rotation_y = -math.degrees(true_anomaly)
            self.anchor.position = Vec3(orbital_radius, 0, 0)
        self.spin_pivot.rotation_y += self.spin_speed * dt * speed
        for moon in self.moons:
            moon.update(dt, speed)


def set_orbit_visibility(body: OrbitalBody, visible: bool) -> None:
    if body.orbit is not None:
        body.orbit.enabled = visible
    for moon in body.moons:
        set_orbit_visibility(moon, visible)


def add_starfield(count: int = 1400, spread: float = 1400) -> None:
    return


def add_deep_space_backdrop() -> None:
    return


def add_space_panorama() -> Entity:
    preferred_panorama = ASSET_DIR / 'space_bg_8k_dark.png'
    if preferred_panorama.exists():
        panorama_texture = 'assets/space_bg_8k_dark.png'
    else:
        panorama_texture = None
    panorama = Entity(
        parent=scene,
        model='sphere',
        texture=panorama_texture,
        position=camera.world_position,
        scale=3500,
        double_sided=True,
        color=color.white if panorama_texture is not None else color.black,
        unlit=True,
    )
    if panorama_texture is not None:
        soften_texture_edges(panorama, repeat=True)
    panorama.setDepthWrite(False)
    panorama.setBin('background', 0)
    panorama.texture_offset = Vec2(0.0012, 0)
    return panorama


def spawn_asteroid(parent: Entity, spawn_radius: float) -> dict[str, Any]:
    entry_direction = Vec3(RNG.uniform(-1.0, 1.0), RNG.uniform(-0.65, 0.65), RNG.uniform(-1.0, 1.0)).normalized()
    tangential = Vec3(-entry_direction.z, RNG.uniform(-0.42, 0.42), entry_direction.x)
    if tangential.length() < 0.001:
        tangential = Vec3(0.0, 0.24, 1.0)
    tangential = tangential.normalized()
    start_position = entry_direction * spawn_radius + tangential * RNG.uniform(-10.0, 10.0)
    target_position = Vec3(RNG.uniform(-18.0, 18.0), RNG.uniform(-6.0, 6.0), RNG.uniform(-18.0, 18.0))
    fly_direction = (target_position - start_position).normalized()
    base_scale = RNG.uniform(0.14, 0.34) * 0.5
    fast_pass = RNG.random() < 0.24
    speed = RNG.uniform(10.0, 17.0) if fast_pass else RNG.uniform(5.5, 11.5)
    asteroid = Entity(
        parent=parent,
        model='sphere',
        texture='assets/asteroid_real.jpg',
        scale=(base_scale * RNG.uniform(1.5, 2.4), base_scale * RNG.uniform(0.7, 1.1), base_scale * RNG.uniform(0.75, 1.2)),
        position=start_position,
        rotation=(RNG.uniform(0, 360), RNG.uniform(0, 360), RNG.uniform(0, 360)),
        color=color.rgba(140, 126, 110, RNG.randint(160, 220)),
    )
    soften_texture_edges(asteroid, repeat=True)
    tail = Entity(
        parent=asteroid,
        model='quad',
        texture='assets/sun_glow.png',
        scale=(base_scale * 2.8, base_scale * RNG.uniform(18.0, 26.0)),
        origin=(0, 0.5),
        position=(0, 0, -base_scale * 0.55),
        rotation_x=90,
        color=color.rgba(255, 255, 255, RNG.randint(92, 128)),
        double_sided=True,
    )
    soften_texture_edges(tail, repeat=False, transparent_border=True)
    tail.setTransparency(TransparencyAttrib.MAlpha)
    tail.setDepthWrite(False)
    tail.setBin('transparent', 2)
    return {
        'entity': asteroid,
        'tail': tail,
        'velocity': fly_direction * speed,
        'spin': Vec3(RNG.uniform(-110, 110), RNG.uniform(-130, 130), RNG.uniform(-90, 90)),
        'base_scale': base_scale,
        'fast_pass': fast_pass,
    }


def spawn_belt_asteroid(parent: Entity, inner_radius: float, outer_radius: float) -> dict[str, Any]:
    while True:
        orbit_t = RNG.random()
        weighted_t = orbit_t ** 0.78
        orbit_radius = inner_radius + (outer_radius - inner_radius) * weighted_t
        outer_gap_threshold = inner_radius + (outer_radius - inner_radius) * 0.82
        if orbit_radius > outer_gap_threshold and RNG.random() < 0.68:
            continue
        break
    orbit_angle = RNG.uniform(0.0, math.tau)
    belt_thickness = 2.2 + (orbit_radius - inner_radius) / max(1.0, outer_radius - inner_radius) * 0.9
    vertical_offset = RNG.uniform(-belt_thickness, belt_thickness)
    base_scale = RNG.uniform(0.04, 0.11) * 5.0 * 0.7 * 0.5
    asteroid = Entity(
        parent=parent,
        model='sphere',
        texture='assets/asteroid_real.jpg',
        scale=(base_scale * RNG.uniform(1.4, 2.3), base_scale * RNG.uniform(0.65, 1.1), base_scale * RNG.uniform(0.75, 1.35)),
        position=(math.cos(orbit_angle) * orbit_radius, vertical_offset, math.sin(orbit_angle) * orbit_radius),
        rotation=(RNG.uniform(0, 360), RNG.uniform(0, 360), RNG.uniform(0, 360)),
        color=color.rgba(RNG.randint(108, 150), RNG.randint(96, 132), RNG.randint(86, 116), RNG.randint(145, 210)),
    )
    soften_texture_edges(asteroid, repeat=True)
    return {
        'entity': asteroid,
        'orbit_radius': orbit_radius,
        'orbit_angle': orbit_angle,
        'vertical_offset': vertical_offset,
        'orbit_speed': RNG.uniform(0.5, 1.2) / max(orbit_radius, 1.0),
        'spin': Vec3(RNG.uniform(-90, 90), RNG.uniform(-120, 120), RNG.uniform(-70, 70)),
    }


def build_scene():
    dark_space = color.black
    ui_font = resolve_ui_font_reference()
    window.title = '太阳系模拟演示工具-flicube.com'
    window.color = dark_space
    window.fps_counter.enabled = True
    window.exit_button.visible = False
    camera.clip_plane_near = 0.01
    camera.clip_plane_far = 200000
    camera.color = dark_space
    camera.overlay.color = color.clear

    if application.base:
        application.base.setBackgroundColor(dark_space)
        display_region = application.base.camNode.get_display_region(0)
        display_region.set_clear_color_active(True)
        display_region.get_window().set_clear_color(dark_space)

    AmbientLight(color=color.rgba(145, 145, 165, 1))
    add_deep_space_backdrop()
    space_panorama = add_space_panorama()

    sun_radius = scaled_body_radius(PLANET_REAL['Sun']['radius_km'], VISUAL_SCALE['sun_body_scale_factor'])
    sun = OrbitalBody('Sun', pick_texture('sun_real.jpg', 'sun.png'), 0, sun_radius, 0, -6)
    PointLight(parent=sun.anchor, color=color.rgb(255, 225, 170), shadows=False)

    sun_shell_1 = Entity(
        parent=sun.anchor,
        model='sphere',
        texture='assets/sun_glow.png',
        scale=sun_radius * 1.045,
        color=color.rgba(255, 150, 55, 38),
        double_sided=False,
    )
    sun_shell_2 = Entity(
        parent=sun.anchor,
        model='sphere',
        texture='assets/sun_glow.png',
        scale=sun_radius * 1.112,
        color=color.rgba(255, 95, 18, 22),
        double_sided=False,
    )
    sun_shell_3 = Entity(
        parent=sun.anchor,
        model='sphere',
        texture='assets/sun_glow.png',
        scale=sun_radius * 1.198,
        color=color.rgba(255, 68, 0, 14),
        double_sided=False,
    )
    flame_roots = []
    flame_tongues = []
    flame_count = 32
    flame_ring_rotations = [(0, 0, 0), (62, 0, 18), (-58, 0, -22), (0, 58, 34), (28, -46, 12), (-24, 42, -14)]
    for ring_index, ring_rotation in enumerate(flame_ring_rotations):
        flame_root = Entity(parent=sun.anchor, rotation=ring_rotation)
        flame_roots.append(flame_root)
        for i in range(flame_count):
            angle = math.tau * (i / flame_count)
            tongue = Entity(
                parent=flame_root,
                model='quad',
        texture='assets/sun_glow.png',
                scale=(sun_radius * 0.12, sun_radius * 0.34),
                position=(math.cos(angle) * sun_radius * 0.44, math.sin(angle) * sun_radius * 0.44, 0),
                rotation_x=90,
                rotation_y=i * (360 / flame_count),
                rotation_z=i * (360 / flame_count),
                color=color.rgba(255, 132, 32, 34),
                double_sided=True,
            )
            flame_tongues.append((tongue, ring_index, i))
    halo = Entity(
        parent=sun.anchor,
        model='quad',
        texture='assets/halo.png',
        scale=0,
        color=color.rgba(255, 220, 170, 0),
        double_sided=False,
        enabled=False,
    )

    planet_bodies = {}
    for name in ('Mercury', 'Venus', 'Earth', 'Mars', 'Jupiter', 'Saturn', 'Uranus', 'Neptune'):
        data = PLANET_DATA[name]
        real = PLANET_REAL[name]
        texture_fn = cast(Callable[[], str], data['texture'])
        orbit_speed_days = float(data['orbit_speed_days'])
        spin_hours = float(data['spin_hours'])
        tilt = float(data['tilt'])
        orbit_tilt = float(data['orbit_tilt'])
        orbit_phase = float(data['orbit_phase'])
        eccentricity = float(data['eccentricity'])
        retrograde_spin = bool(data['retrograde_spin'])
        pole_ra = float(data['pole_ra'])
        pole_dec = float(data['pole_dec'])
        orbit_au = float(real['orbit_au'])
        radius_km = float(real['radius_km'])
        orbit_distance = scaled_planet_distance(orbit_au, VISUAL_SCALE['planet_distance_factor'], VISUAL_SCALE['planet_distance_exponent']) * 1.5
        minimum_orbit_distance = sun_radius * 0.9 + scaled_visual_radius(radius_km, VISUAL_SCALE['planet_radius_factor'], VISUAL_SCALE['min_planet_radius']) * 2.2
        body = OrbitalBody(
            name,
            texture_fn(),
            max(orbit_distance, minimum_orbit_distance),
            scaled_visual_radius(radius_km, VISUAL_SCALE['planet_radius_factor'], VISUAL_SCALE['min_planet_radius']),
            scaled_orbit_speed(orbit_speed_days),
            scaled_spin_speed(spin_hours, retrograde=retrograde_spin),
            tilt=tilt,
            orbit_tilt=orbit_tilt,
            orbit_phase=orbit_phase,
            spin_axis_heading=0,
            eccentricity=eccentricity,
            orbit_thickness=PLANET_ORBIT_THICKNESS,
        )
        body.axis_heading.rotation_y = compute_spin_axis_heading(pole_ra, pole_dec, body.orbit_plane.up)
        planet_bodies[name] = body

    mercury = planet_bodies['Mercury']
    venus = planet_bodies['Venus']
    earth = planet_bodies['Earth']
    mars = planet_bodies['Mars']
    jupiter = planet_bodies['Jupiter']
    saturn = planet_bodies['Saturn']
    uranus = planet_bodies['Uranus']
    neptune = planet_bodies['Neptune']

    earth_night = Entity(
        parent=earth.visual_root,
        model='sphere',
        texture='assets/earth_night.png',
        scale=1.02,
        color=color.rgba(255, 210, 120, 110),
        double_sided=True,
    )
    soften_texture_edges(earth_night, repeat=True, transparent_border=True)
    earth_night.setTransparency(TransparencyAttrib.MAlpha)
    earth_night.setDepthWrite(False)
    earth_night.setBin('transparent', 1)
    earth_clouds = Entity(
        parent=earth.visual_root,
        model='sphere',
        texture='assets/earth_clouds.png',
        scale=1.045,
        color=color.rgba(255, 255, 255, 122),
        double_sided=True,
    )
    soften_texture_edges(earth_clouds, repeat=True, transparent_border=True)
    earth_clouds.setTransparency(TransparencyAttrib.MAlpha)
    earth_clouds.setDepthWrite(False)
    earth_clouds.setBin('transparent', 2)
    earth_clouds.setAttrib(AlphaTestAttrib.make(AlphaTestAttrib.MGreaterEqual, 0.35))

    saturn_ring_back_entity = Entity(
        parent=saturn.axis_tilt,
        model='quad',
        texture='assets/saturn_ring_back.png',
        scale=saturn.body.scale_x * 2.32,
        rotation_x=90,
        rotation_z=0,
        color=color.rgba(255, 255, 255, 120),
        double_sided=True,
    )
    soften_texture_edges(saturn_ring_back_entity, repeat=False, transparent_border=True)
    saturn_ring_back_entity.setTransparency(TransparencyAttrib.MAlpha)
    saturn_ring_back_entity.setDepthWrite(False)
    saturn_ring_back_entity.setBin('transparent', 0)
    saturn_ring_back_entity.setAttrib(AlphaTestAttrib.make(AlphaTestAttrib.MGreaterEqual, 0.2))
    saturn_ring_entity = Entity(
        parent=saturn.axis_tilt,
        model='quad',
        texture='assets/saturn_ring.png',
        scale=saturn.body.scale_x * 2.32,
        rotation_x=90,
        rotation_z=0,
        color=color.rgba(255, 255, 255, 210),
        double_sided=True,
    )
    soften_texture_edges(saturn_ring_entity, repeat=False, transparent_border=True)
    saturn_ring_entity.setTransparency(TransparencyAttrib.MAlpha)
    saturn_ring_entity.setDepthWrite(False)
    saturn_ring_entity.setBin('transparent', 1)
    saturn_ring_entity.setAttrib(AlphaTestAttrib.make(AlphaTestAttrib.MGreaterEqual, 0.25))

    belt_inner_radius = mars.distance + (jupiter.distance - mars.distance) * 0.16
    belt_outer_radius = mars.distance + (jupiter.distance - mars.distance) * 0.66
    asteroid_belt_parent = Entity(parent=scene, rotation_x=RNG.uniform(-2.5, 2.5), rotation_z=RNG.uniform(-2.0, 2.0))
    asteroid_belt: list[dict[str, Any]] = [spawn_belt_asteroid(asteroid_belt_parent, belt_inner_radius, belt_outer_radius) for _ in range(320)]

    asteroid_spawn_radius = max(neptune.distance * 1.22, 120.0)
    asteroid_field: list[dict[str, Any]] = [spawn_asteroid(scene, asteroid_spawn_radius) for _ in range(7)]

    def add_scaled_moon(parent_body: OrbitalBody, moon_name: str, parent_transform, orbit_speed_sign: float = 1.0) -> OrbitalBody:
        moon_data = MOON_DATA[moon_name]
        moon_real = MOON_REAL[moon_name]
        parent_real = PLANET_REAL[parent_body.name]
        texture_fn = cast(Callable[[], str], moon_data['texture'])
        period_days = float(moon_data['period_days'])
        spin_hours = float(moon_data.get('spin_hours', period_days * 24.0))
        retrograde_spin = bool(moon_data.get('retrograde_spin', False))
        synchronous_lock = bool(moon_data.get('synchronous_lock', False))
        texture_rotation_y = float(moon_data.get('texture_rotation_y', 0.0))
        tilt = float(moon_data['tilt'])
        orbit_tilt = float(moon_data['orbit_tilt'])
        orbit_phase = float(moon_data['orbit_phase'])
        eccentricity = float(moon_data['eccentricity'])
        orbit_color = moon_data['orbit_color']
        semi_major_axis_km = float(moon_real['semi_major_axis_km'])
        radius_km = float(moon_real['radius_km'])
        orbit_distance = scaled_moon_distance(semi_major_axis_km, VISUAL_SCALE['moon_distance_factor'], VISUAL_SCALE['moon_distance_exponent'])
        if parent_body.name == 'Saturn':
            parent_radius_km = float(parent_real['radius_km'])
            parent_visual_radius = float(parent_body.body.scale_x) * 0.5
            realistic_ratio_distance = parent_visual_radius * (semi_major_axis_km / parent_radius_km)
            minimum_outside_rings = parent_visual_radius * 2.55
            orbit_distance = max(minimum_outside_rings, realistic_ratio_distance * 0.18)
        elif parent_body.name == 'Jupiter':
            parent_radius_km = float(parent_real['radius_km'])
            parent_visual_radius = float(parent_body.body.scale_x) * 0.5
            realistic_ratio_distance = parent_visual_radius * (semi_major_axis_km / parent_radius_km)
            minimum_clear_distance = parent_visual_radius * 1.65
            orbit_distance = max(minimum_clear_distance, realistic_ratio_distance * 0.22)
        moon = OrbitalBody(
            moon_name,
            texture_fn(),
            orbit_distance,
            scaled_visual_radius(radius_km, VISUAL_SCALE['moon_radius_factor'], VISUAL_SCALE['min_moon_radius']),
            scaled_moon_orbit_speed(period_days) * orbit_speed_sign,
            0.0 if synchronous_lock else scaled_spin_speed(spin_hours, retrograde=retrograde_spin),
            tilt=tilt,
            orbit_tilt=orbit_tilt,
            orbit_phase=orbit_phase,
            eccentricity=eccentricity,
            parent=parent_transform,
            orbit_color=orbit_color,
            orbit_thickness=MOON_ORBIT_THICKNESS,
        )
        moon.visual_root.rotation_y = texture_rotation_y
        parent_body.add_moon(moon)
        return moon

    add_scaled_moon(earth, 'Moon', earth.anchor)
    add_scaled_moon(mars, 'Phobos', mars.axis_tilt)
    add_scaled_moon(mars, 'Deimos', mars.axis_tilt)
    add_scaled_moon(jupiter, 'Io', jupiter.axis_tilt)
    add_scaled_moon(jupiter, 'Europa', jupiter.axis_tilt)
    add_scaled_moon(jupiter, 'Ganymede', jupiter.axis_tilt)
    add_scaled_moon(jupiter, 'Callisto', jupiter.axis_tilt)
    add_scaled_moon(saturn, 'Titan', saturn.axis_tilt)
    add_scaled_moon(saturn, 'Rhea', saturn.axis_tilt)
    add_scaled_moon(uranus, 'Titania', uranus.axis_tilt)
    add_scaled_moon(neptune, 'Triton', neptune.axis_tilt, orbit_speed_sign=-1.0)

    planets = [sun, mercury, venus, earth, mars, jupiter, saturn, uranus, neptune]
    add_starfield()

    hotkey_text = Text(
        text='0 全景 | 1 水星 | 2 金星 | 3 地球 | 4 火星 | 5 木星 | 6 土星 | 7 天王星 | 8 海王星 | WASD 移动/环绕 | 左键/右键/滚轮 | 空格 轨道 | P 暂停',
        x=-0.86,
        y=0.46,
        scale=0.72,
        color=color.rgba(255, 255, 255, 185),
        font=ui_font,
    )
    orbit_status_text = Text(
        text='轨道：显示 [空格]',
        x=0.54,
        y=0.46,
        scale=0.82,
        color=color.rgba(170, 255, 190, 235),
        font=ui_font,
    )
    target_status_text = Text(
        text='当前目标：全景',
        x=-0.86,
        y=0.40,
        scale=0.8,
        color=color.rgba(130, 210, 255, 235),
        font=ui_font,
    )

    editor_camera = EditorCamera(rotation_smoothing=0, rotate_key='right mouse', move_speed=0, pan_speed=(0, 0), zoom_speed=0, enabled=True)
    editor_camera.ignore = True
    held_key_state: Any = held_keys
    wasd_move_speed = 38
    earth_free_wasd_speed = 1.7

    simulation_speed = 1.45
    last_tick = pytime.perf_counter()
    pan_sensitivity = 1620
    camera_mode = 'overview'
    overview_position = Vec3(0, 18, -150)
    target_body = mercury
    follow_distances = {
        'Mercury': 8.0,
        'Venus': 10.0,
        'Earth': 12.8,
        'Mars': 10.4,
        'Jupiter': 22.0,
        'Saturn': 20.0,
        'Uranus': 14.4,
        'Neptune': 14.0,
    }
    earth_free_pan_sensitivity = 252
    earth_free_rotate_sensitivity = 110
    overview_rotate_sensitivity = 180
    orbits_visible = True
    paused = False
    selected_body: OrbitalBody | None = None
    selected_follow_offset = Vec3(0, 0, 0)
    selected_follow_up = Vec3(0, 1, 0)
    selected_transition_focus = Vec3(0, 0, 0)
    selected_focus_offset = Vec3(0, 0, 0)
    selected_follow_distance = 12.0
    selected_follow_yaw = 0.0
    selected_follow_pitch = 12.0
    selected_follow_pan_sensitivity = 270.0
    selected_follow_yaw_speed = 82.0
    selected_follow_pitch_speed = 58.0
    selection_label_position = Vec2(0.07, 0.03)
    mouse_press_position = Vec2(0, 0)
    click_candidate_active = False
    click_drag_threshold = 0.018
    follow_focus_point = mercury.anchor.world_position
    follow_up_vector = mercury.orbit_plane.up.normalized()
    transition_timer = 0.0
    transition_duration = 0.9
    selected_transition_duration = 1.05

    body_hotkeys = {
        '1': mercury,
        '2': venus,
        '3': earth,
        '4': mars,
        '5': jupiter,
        '6': saturn,
        '7': uranus,
        '8': neptune,
    }
    body_to_hotkey = {body.name: key for key, body in body_hotkeys.items()}
    body_display_names = {
        'Sun': '太阳',
        'Mercury': '水星',
        'Venus': '金星',
        'Earth': '地球',
        'Mars': '火星',
        'Jupiter': '木星',
        'Saturn': '土星',
        'Uranus': '天王星',
        'Neptune': '海王星',
        'Moon': '月球',
        'Phobos': '火卫一',
        'Deimos': '火卫二',
        'Io': '木卫一',
        'Europa': '木卫二',
        'Ganymede': '木卫三',
        'Callisto': '木卫四',
        'Titan': '土卫六',
        'Rhea': '土卫五',
        'Titania': '天卫三',
        'Triton': '海卫一',
    }
    selection_status_text = Text(
        text='',
        x=0,
        y=0,
        scale=0.62,
        color=color.rgba(120, 235, 255, 240),
        font=ui_font,
        enabled=False,
    )
    selection_reticle = Entity(
        parent=scene,
        model='quad',
        texture='assets/selection_bracket.png',
        scale=1,
        color=color.rgba(255, 255, 255, 255),
        billboard=True,
        double_sided=True,
        unlit=True,
        enabled=False,
    )
    selection_reticle.setTransparency(TransparencyAttrib.MAlpha)
    selection_reticle.setDepthWrite(False)
    selection_reticle.setBin('transparent', 25)
    selection_reticle_inner_clear_ratio = 0.44

    def refresh_selection_ui() -> None:
        if selected_body is None:
            selection_status_text.enabled = False
            selection_reticle.enabled = False
            selection_status_text.text = ''
            return
        selection_status_text.text = body_display_names.get(selected_body.name, selected_body.name)
        selection_status_text.enabled = True
        selection_reticle.parent = selected_body.anchor
        selection_reticle.position = Vec3(0, 0, 0)
        selection_reticle.scale = max(0.6, float(selected_body.body.scale_x) / selection_reticle_inner_clear_ratio)
        selection_reticle.enabled = True

    def attach_camera_to_overview_controls() -> None:
        nonlocal camera_mode
        if camera.parent != scene:
            camera.parent = scene
        world_position = Vec3(overview_position)
        camera.world_position = world_position
        camera.look_at(sun.anchor.world_position, up=Vec3(0, 1, 0))
        world_rotation = Vec3(camera.world_rotation)
        editor_camera.position = world_position
        editor_camera.rotation = world_rotation
        editor_camera.enabled = True
        camera.parent = editor_camera
        camera.position = Vec3(0, 0, 0)
        camera.rotation = Vec3(0, 0, 0)
        editor_camera.target_z = 0
        camera_mode = 'overview'

    def clear_selection(*, stop_follow: bool) -> None:
        nonlocal selected_body, selection_label_position, selected_focus_offset, camera_mode
        selected_body = None
        selected_focus_offset = Vec3(0, 0, 0)
        selection_label_position = Vec2(0.07, 0.03)
        refresh_selection_ui()
        if stop_follow:
            world_position = Vec3(camera.world_position)
            world_rotation = Vec3(camera.world_rotation)
            camera.parent = scene
            camera.world_position = world_position
            camera.world_rotation = world_rotation
            editor_camera.position = world_position
            editor_camera.rotation = world_rotation
            editor_camera.enabled = True
            camera.parent = editor_camera
            camera.position = Vec3(0, 0, 0)
            camera.rotation = Vec3(0, 0, 0)
            editor_camera.target_z = 0
            camera_mode = 'overview'
        refresh_target_ui()

    def begin_selected_follow(new_body: OrbitalBody) -> None:
        nonlocal camera_mode, target_body, selected_body, selected_follow_offset, selected_follow_up, selected_transition_focus, transition_timer
        nonlocal selected_follow_distance, selected_follow_yaw, selected_follow_pitch, selected_focus_offset
        world_position = Vec3(camera.world_position)
        editor_camera.enabled = False
        camera.parent = scene
        camera.world_position = world_position
        target_body = new_body
        selected_body = new_body
        selected_follow_offset = world_position - new_body.anchor.world_position
        if selected_follow_offset.length() < 0.001:
            selected_follow_offset = Vec3(0, 0, -max(4.0, float(new_body.body.scale_x) * 4.0))
        selected_follow_distance = max(2.5, selected_follow_offset.length())
        horizontal_length = math.sqrt(selected_follow_offset.x * selected_follow_offset.x + selected_follow_offset.z * selected_follow_offset.z)
        selected_follow_yaw = math.degrees(math.atan2(selected_follow_offset.x, selected_follow_offset.z))
        selected_follow_pitch = math.degrees(math.atan2(selected_follow_offset.y, max(0.001, horizontal_length)))
        selected_focus_offset = Vec3(0, 0, 0)
        selected_follow_up = camera_up_vector()
        selected_transition_focus = camera_focus_point()
        transition_timer = 0.0
        camera_mode = 'transition_selected_follow'
        camera.look_at(selected_transition_focus, up=selected_follow_up)
        refresh_selection_ui()
        refresh_target_ui()

    def resolve_clicked_body() -> OrbitalBody | None:
        hovered_entity = mouse.hovered_entity
        return cast(OrbitalBody | None, getattr(hovered_entity, 'orbital_body', None)) if hovered_entity is not None else None

    def camera_focus_point(distance: float = 40.0) -> Vec3:
        return camera.world_position + camera.forward * distance

    def camera_up_vector() -> Vec3:
        up = Vec3(camera.up)
        return up.normalized() if up.length() > 0.001 else Vec3(0, 1, 0)

    def world_to_ui_point(world_position: Vec3) -> Vec3 | None:
        if not application.base:
            return None
        relative_point = application.base.cam.getRelativePoint(
            application.base.render,
            Point3(world_position.x, world_position.y, world_position.z),
        )
        projected = Point2()
        if relative_point.y <= 0 or not application.base.camLens.project(relative_point, projected):
            return None
        return Vec3(projected.x, projected.y, relative_point.y)

    def refresh_orbit_status_text() -> None:
        orbit_status_text.text = f'轨道：{"显示" if orbits_visible else "隐藏"} [空格]'
        orbit_status_text.color = color.rgba(170, 255, 190, 235) if orbits_visible else color.rgba(255, 170, 170, 235)

    def refresh_target_ui() -> None:
        if camera_mode in ('overview', 'transition_overview'):
            selected_key = '0'
            target_status_text.text = '当前目标：全景（WASD移动，左键平移，右键旋转，滚轮缩放）'
            target_status_text.color = color.rgba(130, 210, 255, 235)
        elif camera_mode in ('selected_follow', 'transition_selected_follow') and selected_body is not None:
            selected_key = body_to_hotkey.get(selected_body.name)
            target_status_text.text = f'当前目标：{body_display_names.get(selected_body.name, selected_body.name)}（点选跟随：左键平移 右键旋转 滚轮缩放 WASD环绕）'
            target_status_text.color = color.rgba(120, 235, 255, 240)
        else:
            selected_key = body_to_hotkey.get(target_body.name)
            suffix = '（自由）' if camera_mode == 'earth_free' else ''
            target_status_text.text = f'当前目标：{body_display_names.get(target_body.name, target_body.name)}{suffix}'
            target_status_text.color = color.rgba(255, 225, 140, 235) if camera_mode != 'earth_free' else color.rgba(255, 190, 140, 235)

        hotkey_segments = []
        for key, label in [('0', '全景'), ('1', '水星'), ('2', '金星'), ('3', '地球'), ('4', '火星'), ('5', '木星'), ('6', '土星'), ('7', '天王星'), ('8', '海王星')]:
            hotkey_segments.append(f'[{key} {label}]' if key == selected_key else f'{key} {label}')
        hotkey_text.text = ' | '.join(hotkey_segments) + ' | WASD 移动/环绕 | 左键/右键/滚轮 | 空格 轨道 | P 暂停'

    def begin_follow_transition(new_body: OrbitalBody) -> None:
        nonlocal camera_mode, target_body, follow_focus_point, follow_up_vector, transition_timer
        clear_selection(stop_follow=False)
        world_position = Vec3(camera.world_position)
        focus_point = camera_focus_point()
        up_vector = camera_up_vector()
        editor_camera.enabled = False
        camera.parent = scene
        camera.world_position = world_position
        camera.look_at(focus_point, up=up_vector)
        camera_mode = 'transition_follow'
        target_body = new_body
        transition_timer = 0.0
        follow_focus_point = focus_point
        follow_up_vector = up_vector
        refresh_target_ui()

    def begin_overview_transition() -> None:
        nonlocal camera_mode, follow_focus_point, follow_up_vector, transition_timer
        clear_selection(stop_follow=False)
        world_position = Vec3(camera.world_position)
        focus_point = camera_focus_point()
        up_vector = camera_up_vector()
        editor_camera.enabled = False
        camera.parent = scene
        camera.world_position = world_position
        camera.look_at(focus_point, up=up_vector)
        camera_mode = 'transition_overview'
        transition_timer = 0.0
        follow_focus_point = focus_point
        follow_up_vector = up_vector
        refresh_target_ui()

    refresh_orbit_status_text()
    refresh_selection_ui()
    attach_camera_to_overview_controls()
    refresh_target_ui()

    def input(key):
        nonlocal camera_mode, target_body, orbits_visible, follow_focus_point, follow_up_vector, paused
        nonlocal mouse_press_position, click_candidate_active
        nonlocal selected_follow_distance
        cam_distance = max(4.0, (sun.anchor.world_position - camera.world_position).length() * 0.18)
        if key == 'left mouse down':
            mouse_press_position = Vec2(mouse.position[0], mouse.position[1])
            click_candidate_active = True
        elif key == 'left mouse up':
            current_mouse_position = Vec2(mouse.position[0], mouse.position[1])
            if click_candidate_active and (current_mouse_position - mouse_press_position).length() <= click_drag_threshold:
                clicked_body = resolve_clicked_body()
                if clicked_body is not None:
                    begin_selected_follow(clicked_body)
                elif selected_body is not None:
                    clear_selection(stop_follow=camera_mode in ('selected_follow', 'transition_selected_follow'))
            click_candidate_active = False
        elif key == 'scroll up' and camera_mode == 'overview':
            editor_camera.position += camera.forward * cam_distance
        elif key == 'scroll down' and camera_mode == 'overview':
            editor_camera.position -= camera.forward * cam_distance
        elif key == 'scroll up' and camera_mode == 'earth_free':
            camera.position += camera.forward * 2.5
        elif key == 'scroll up' and camera_mode == 'earth_follow':
            camera.position += camera.forward * 2.5
        elif key == 'scroll down' and camera_mode == 'earth_follow':
            camera_mode = 'earth_free'
            camera.position -= camera.forward * 2.5
            refresh_target_ui()
        elif key == 'scroll down' and camera_mode == 'earth_free':
            camera.position -= camera.forward * 2.5
        elif key == 'scroll up' and camera_mode in ('selected_follow', 'transition_selected_follow') and selected_body is not None:
            selected_follow_distance = max(max(1.8, float(selected_body.body.scale_x) * 1.2), selected_follow_distance - max(0.8, selected_follow_distance * 0.12))
        elif key == 'scroll down' and camera_mode in ('selected_follow', 'transition_selected_follow') and selected_body is not None:
            selected_follow_distance += max(0.8, selected_follow_distance * 0.12)
        elif key in body_hotkeys:
            begin_follow_transition(body_hotkeys[key])
        elif key == '0':
            begin_overview_transition()
        elif key == 'space':
            orbits_visible = not orbits_visible
            for body in planets:
                set_orbit_visibility(body, orbits_visible)
            refresh_orbit_status_text()
        elif key == 'p':
            paused = not paused

    globals()['input'] = input

    def update():
        nonlocal last_tick, camera_mode, follow_focus_point, follow_up_vector, transition_timer, selected_transition_focus
        nonlocal selection_label_position
        nonlocal selected_follow_distance, selected_follow_yaw, selected_follow_pitch, selected_focus_offset
        now = pytime.perf_counter()
        dt = min(now - last_tick, 0.05)
        last_tick = now

        if camera_mode == 'overview':
            if held_key_state.get('w', False):
                editor_camera.position += editor_camera.forward * wasd_move_speed * dt
            if held_key_state.get('s', False):
                editor_camera.position -= editor_camera.forward * wasd_move_speed * dt
            if held_key_state.get('a', False):
                editor_camera.position -= editor_camera.right * wasd_move_speed * dt
            if held_key_state.get('d', False):
                editor_camera.position += editor_camera.right * wasd_move_speed * dt
        elif camera_mode == 'earth_free':
            if held_key_state.get('w', False):
                camera.position += camera.forward * earth_free_wasd_speed * dt
            if held_key_state.get('s', False):
                camera.position -= camera.forward * earth_free_wasd_speed * dt
            if held_key_state.get('a', False):
                camera.position -= camera.right * earth_free_wasd_speed * dt
            if held_key_state.get('d', False):
                camera.position += camera.right * earth_free_wasd_speed * dt
        elif camera_mode in ('selected_follow', 'transition_selected_follow') and selected_body is not None:
            if held_key_state.get('a', False):
                selected_follow_yaw -= selected_follow_yaw_speed * dt
            if held_key_state.get('d', False):
                selected_follow_yaw += selected_follow_yaw_speed * dt
            if held_key_state.get('w', False):
                selected_follow_pitch = min(80, selected_follow_pitch + selected_follow_pitch_speed * dt)
            if held_key_state.get('s', False):
                selected_follow_pitch = max(-80, selected_follow_pitch - selected_follow_pitch_speed * dt)

        if mouse.left and camera_mode == 'overview':
            zoom_compensation = max(0.35, abs(editor_camera.target_z) * 0.08)
            editor_camera.position -= editor_camera.right * mouse.velocity[0] * pan_sensitivity * dt * zoom_compensation
            editor_camera.position -= editor_camera.up * mouse.velocity[1] * pan_sensitivity * dt * zoom_compensation
        elif mouse.right and camera_mode == 'overview':
            editor_camera.rotation_x = max(-89, min(89, editor_camera.rotation_x - mouse.velocity[1] * overview_rotate_sensitivity))
            editor_camera.rotation_y += mouse.velocity[0] * overview_rotate_sensitivity
        elif mouse.left and camera_mode == 'earth_free':
            camera.position -= camera.right * mouse.velocity[0] * earth_free_pan_sensitivity * dt
            camera.position -= camera.up * mouse.velocity[1] * earth_free_pan_sensitivity * dt
        elif mouse.left and camera_mode in ('selected_follow', 'transition_selected_follow') and selected_body is not None:
            pan_scale = max(0.01, selected_follow_distance * 0.018)
            selected_focus_offset -= camera.right * mouse.velocity[0] * selected_follow_pan_sensitivity * dt * pan_scale
            selected_focus_offset -= camera.up * mouse.velocity[1] * selected_follow_pan_sensitivity * dt * pan_scale
        elif mouse.right and camera_mode in ('selected_follow', 'transition_selected_follow') and selected_body is not None:
            selected_follow_yaw += mouse.velocity[0] * 240 * dt
            selected_follow_pitch = max(-80, min(80, selected_follow_pitch - mouse.velocity[1] * 180 * dt))

        if mouse.right and camera_mode == 'earth_free':
            camera.rotation_x -= mouse.velocity[1] * earth_free_rotate_sensitivity
            camera.rotation_y += mouse.velocity[0] * earth_free_rotate_sensitivity

        t = pytime.time()
        if not paused:
            current_sun_radius = float(sun.body.scale_x)
            flame_surface_radius = current_sun_radius * 0.5
            sun_shell_1.rotation_y += dt * 18
            sun_shell_1.texture_offset = Vec2(t * 0.015, t * 0.01)
            sun_shell_1.scale = current_sun_radius * (1.045 + math.sin(t * 3.9) * 0.018 + math.sin(t * 9.5) * 0.008)
            sun_shell_1.color = color.rgba(
                int(248 + math.sin(t * 2.1) * 7),
                int(132 + math.sin(t * 3.3 + 0.6) * 20),
                int(36 + math.sin(t * 5.1) * 14),
                int(34 + math.sin(t * 4.2) * 8),
            )

            sun_shell_2.rotation_y -= dt * 13
            sun_shell_2.texture_offset = Vec2(-t * 0.01, t * 0.013)
            sun_shell_2.scale = current_sun_radius * (1.112 + math.sin(t * 2.8 + 1.5) * 0.027 + math.sin(t * 7.3) * 0.012)
            sun_shell_2.color = color.rgba(
                int(255),
                int(82 + math.sin(t * 2.5 + 0.8) * 16),
                int(12 + math.sin(t * 4.7 + 1.3) * 8),
                int(18 + math.sin(t * 3.7) * 7),
            )
            sun_shell_3.rotation_y += dt * 28
            sun_shell_3.rotation_x += dt * 11
            sun_shell_3.texture_offset = Vec2(t * 0.028, -t * 0.019)
            sun_shell_3.scale = current_sun_radius * (1.198 + math.sin(t * 6.2) * 0.038 + math.sin(t * 13.5 + 0.8) * 0.017)
            sun_shell_3.color = color.rgba(
                255,
                int(64 + math.sin(t * 5.4) * 20),
                int(0 + max(0, math.sin(t * 8.1)) * 10),
                int(18 + math.sin(t * 6.7 + 0.9) * 8),
            )
            for ring_index, flame_root in enumerate(flame_roots):
                flame_root.rotation_z += dt * (7 + ring_index * 1.6)
                flame_root.rotation_y += dt * (3.5 if ring_index % 2 == 0 else -3.5)

            for tongue, ring_index, index in flame_tongues:
                phase = t * (2.6 + index * 0.13) + index * 0.8
                angle = math.tau * (index / flame_count)
                radial = flame_surface_radius * (0.89 + ring_index * 0.01) + math.sin(phase * 1.8) * current_sun_radius * 0.016
                tongue.rotation_y = index * (360 / flame_count) + math.sin(phase) * 14
                tongue.rotation_z = index * (360 / flame_count) + math.sin(phase * 1.2) * 18
                tongue.rotation_x = 90 + math.sin(phase * 0.7) * 11
                tongue.position = Vec3(math.cos(angle) * radial, math.sin(angle) * radial, math.sin(phase * 1.5) * current_sun_radius * (0.024 + ring_index * 0.004))
                tongue.scale = Vec2(
                    current_sun_radius * (0.08 + math.sin(phase * 1.7) * 0.014),
                    current_sun_radius * (0.36 + math.sin(phase * 2.4) * 0.092 + ring_index * 0.024),
                )
                tongue.color = color.rgba(
                    255,
                    int(140 + math.sin(phase * 1.5) * 28),
                    int(24 + max(0, math.sin(phase * 2.2)) * 20),
                    int(28 + math.sin(phase * 2.0 + 0.4) * 12 + ring_index * 2),
                )
            earth_clouds.rotation_y += dt * 6.5
            earth_night.rotation_y += dt * 0.8
            current_saturn_radius = float(saturn.body.scale_x)
            saturn_ring_back_entity.scale = current_saturn_radius * 2.32
            saturn_ring_entity.scale = current_saturn_radius * 2.32
            saturn_ring_back_entity.rotation_z = 0
            saturn_ring_entity.rotation_z = 0

            for belt_info in asteroid_belt:
                belt_entity = belt_info['entity']
                belt_info['orbit_angle'] = (belt_info['orbit_angle'] + belt_info['orbit_speed'] * dt * simulation_speed) % math.tau
                orbit_angle = belt_info['orbit_angle']
                orbit_radius = belt_info['orbit_radius']
                belt_entity.position = Vec3(math.cos(orbit_angle) * orbit_radius, belt_info['vertical_offset'], math.sin(orbit_angle) * orbit_radius)
                spin = belt_info['spin']
                belt_entity.rotation_x += spin.x * dt
                belt_entity.rotation_y += spin.y * dt
                belt_entity.rotation_z += spin.z * dt

            for asteroid_info in asteroid_field:
                asteroid_entity = asteroid_info['entity']
                asteroid_tail = asteroid_info['tail']
                velocity = asteroid_info['velocity']
                spin = asteroid_info['spin']
                base_scale = asteroid_info['base_scale']
                fast_pass = asteroid_info['fast_pass']
                asteroid_entity.position += velocity * dt
                asteroid_entity.rotation_x += spin.x * dt
                asteroid_entity.rotation_y += spin.y * dt
                asteroid_entity.rotation_z += spin.z * dt
                asteroid_entity.look_at(asteroid_entity.position + velocity.normalized(), up=Vec3(0, 1, 0))
                distance_to_sun = max(0.001, asteroid_entity.position.length())
                solar_heat = max(0.0, min(1.0, 1.0 - distance_to_sun / asteroid_spawn_radius))
                tail_heat = solar_heat * solar_heat
                tail_length = base_scale * ((14.0 if fast_pass else 11.0) + tail_heat * (34.0 if fast_pass else 22.0) + math.sin(t * 6.0 + base_scale * 10.0) * 1.8)
                tail_width = base_scale * (1.9 + tail_heat * 2.2)
                asteroid_tail.position = Vec3(0, 0, -base_scale * 0.52)
                asteroid_tail.rotation = Vec3(90, 0, 0)
                asteroid_tail.scale = Vec2(tail_width, tail_length)
                asteroid_tail.color = color.rgba(
                    255,
                    255,
                    255,
                    int(92 + tail_heat * 120),
                )
                asteroid_entity.color = color.rgba(
                    int(140 + tail_heat * 95),
                    int(126 + tail_heat * 22),
                    int(110 + tail_heat * 10),
                    210,
                )
                if asteroid_entity.position.length() < sun.body.scale_x * 0.7 or asteroid_entity.position.length() > asteroid_spawn_radius * 1.12:
                    destroy(asteroid_tail)
                    destroy(asteroid_entity)
                    replacement = spawn_asteroid(scene, asteroid_spawn_radius)
                    asteroid_info['entity'] = replacement['entity']
                    asteroid_info['tail'] = replacement['tail']
                    asteroid_info['velocity'] = replacement['velocity']
                    asteroid_info['spin'] = replacement['spin']
                    asteroid_info['base_scale'] = replacement['base_scale']
                    asteroid_info['fast_pass'] = replacement['fast_pass']

            for body in planets:
                body.update(dt, simulation_speed)

        space_panorama.position = camera.world_position

        if selected_body is not None:
            body_center_world = Vec3(selected_body.body.world_position)
            body_radius_world = max(0.08, float(selected_body.body.scale_x) * 0.5)
            center_point = world_to_ui_point(body_center_world)

            if center_point is not None:
                selection_label_position = Vec2(
                    min(0.82, center_point.x + 0.045),
                    min(0.47, center_point.y + 0.02),
                )
            pulse = 1.0 + math.sin(t * 2.4) * 0.035
            selection_reticle.parent = selected_body.anchor
            selection_reticle.position = Vec3(0, 0, 0)
            selection_reticle.scale = max(0.6, (float(selected_body.body.scale_x) / selection_reticle_inner_clear_ratio) * pulse)
            selection_reticle.color = color.rgba(255, 255, 255, int(220 + math.sin(t * 2.4) * 20))
            selection_status_text.enabled = True
            selection_status_text.x = selection_label_position.x
            selection_status_text.y = selection_label_position.y

        if camera_mode in ('earth_follow', 'transition_follow'):
            anti_sun_direction = (target_body.anchor.world_position - sun.anchor.world_position).normalized()
            orbit_normal = target_body.orbit_plane.up.normalized()
            tangential_direction = orbit_normal.cross(anti_sun_direction).normalized()
            leveled_vertical = orbit_normal * (0.08 if target_body.name == 'Earth' else 0.18)
            follow_distance = follow_distances.get(target_body.name, 6.0)
            target_position = target_body.anchor.world_position + anti_sun_direction * follow_distance + tangential_direction * (follow_distance * 0.08) + leveled_vertical
            focus_lerp_speed = 4.2 if camera_mode == 'earth_follow' else 2.8
            up_lerp_speed = 3.4 if camera_mode == 'earth_follow' else 2.4
            move_lerp_speed = 3.5 if camera_mode == 'earth_follow' else 2.6
            follow_focus_point = Vec3(
                lerp(follow_focus_point.x, target_body.anchor.world_position.x, dt * focus_lerp_speed),
                lerp(follow_focus_point.y, target_body.anchor.world_position.y, dt * focus_lerp_speed),
                lerp(follow_focus_point.z, target_body.anchor.world_position.z, dt * focus_lerp_speed),
            )
            follow_up_vector = Vec3(
                lerp(follow_up_vector.x, orbit_normal.x, dt * up_lerp_speed),
                lerp(follow_up_vector.y, orbit_normal.y, dt * up_lerp_speed),
                lerp(follow_up_vector.z, orbit_normal.z, dt * up_lerp_speed),
            )
            if follow_up_vector.length() < 0.001:
                follow_up_vector = orbit_normal
            else:
                follow_up_vector = follow_up_vector.normalized()
            camera.world_position = Vec3(
                lerp(camera.world_position.x, target_position.x, dt * move_lerp_speed),
                lerp(camera.world_position.y, target_position.y, dt * move_lerp_speed),
                lerp(camera.world_position.z, target_position.z, dt * move_lerp_speed),
            )
            camera.look_at(follow_focus_point, up=follow_up_vector)
            if camera_mode == 'transition_follow':
                transition_timer += dt
                if transition_timer >= transition_duration:
                    camera_mode = 'earth_follow'
                    refresh_target_ui()
        elif camera_mode == 'transition_selected_follow' and selected_body is not None:
            desired_focus = selected_body.anchor.world_position + selected_focus_offset
            yaw_radians = math.radians(selected_follow_yaw)
            pitch_radians = math.radians(selected_follow_pitch)
            orbit_offset = Vec3(
                math.sin(yaw_radians) * math.cos(pitch_radians),
                math.sin(pitch_radians),
                math.cos(yaw_radians) * math.cos(pitch_radians),
            ) * selected_follow_distance
            desired_position = desired_focus + orbit_offset
            selected_transition_focus = Vec3(
                lerp(selected_transition_focus.x, desired_focus.x, dt * 1.65),
                lerp(selected_transition_focus.y, desired_focus.y, dt * 1.65),
                lerp(selected_transition_focus.z, desired_focus.z, dt * 1.65),
            )
            camera.world_position = Vec3(
                lerp(camera.world_position.x, desired_position.x, dt * 1.55),
                lerp(camera.world_position.y, desired_position.y, dt * 1.55),
                lerp(camera.world_position.z, desired_position.z, dt * 1.55),
            )
            camera.look_at(selected_transition_focus, up=selected_follow_up)
            transition_timer += dt
            if transition_timer >= selected_transition_duration:
                camera_mode = 'selected_follow'
                refresh_target_ui()
        elif camera_mode == 'selected_follow' and selected_body is not None:
            desired_focus = selected_body.anchor.world_position + selected_focus_offset
            yaw_radians = math.radians(selected_follow_yaw)
            pitch_radians = math.radians(selected_follow_pitch)
            orbit_offset = Vec3(
                math.sin(yaw_radians) * math.cos(pitch_radians),
                math.sin(pitch_radians),
                math.cos(yaw_radians) * math.cos(pitch_radians),
            ) * selected_follow_distance
            camera.world_position = desired_focus + orbit_offset
            camera.look_at(desired_focus, up=selected_follow_up)
        elif camera_mode == 'transition_overview':
            overview_focus = sun.anchor.world_position
            overview_up = Vec3(0, 1, 0)
            follow_focus_point = Vec3(
                lerp(follow_focus_point.x, overview_focus.x, dt * 2.4),
                lerp(follow_focus_point.y, overview_focus.y, dt * 2.4),
                lerp(follow_focus_point.z, overview_focus.z, dt * 2.4),
            )
            follow_up_vector = Vec3(
                lerp(follow_up_vector.x, overview_up.x, dt * 2.2),
                lerp(follow_up_vector.y, overview_up.y, dt * 2.2),
                lerp(follow_up_vector.z, overview_up.z, dt * 2.2),
            )
            if follow_up_vector.length() < 0.001:
                follow_up_vector = overview_up
            else:
                follow_up_vector = follow_up_vector.normalized()
            camera.world_position = Vec3(
                lerp(camera.world_position.x, overview_position.x, dt * 2.6),
                lerp(camera.world_position.y, overview_position.y, dt * 2.6),
                lerp(camera.world_position.z, overview_position.z, dt * 2.6),
            )
            camera.look_at(follow_focus_point, up=follow_up_vector)
            transition_timer += dt
            if transition_timer >= transition_duration:
                world_position = Vec3(camera.world_position)
                world_rotation = Vec3(camera.world_rotation)
                editor_camera.position = world_position
                editor_camera.rotation = world_rotation
                editor_camera.enabled = True
                camera.parent = editor_camera
                camera.position = Vec3(0, 0, 0)
                camera.rotation = Vec3(0, 0, 0)
                editor_camera.target_z = 0
                camera_mode = 'overview'
                refresh_target_ui()

    return update


def main():
    parser = argparse.ArgumentParser(description='3D Solar System in Python/Ursina')
    parser.add_argument('--auto-close', type=float, default=0.0, help='Automatically close after N seconds for testing')
    args = parser.parse_args()

    ensure_assets()
    loadPrcFileData('', 'window-title 太阳系模拟演示工具-flicube.com')
    app = Ursina(title='太阳系模拟演示工具-flicube.com', borderless=False)
    window.title = '太阳系模拟演示工具-flicube.com'
    application.asset_folder = ROOT
    update_fn = build_scene()
    globals()['update'] = update_fn

    if args.auto_close > 0:
        invoke(application.quit, delay=args.auto_close)

    app.run()


if __name__ == '__main__':
    main()
