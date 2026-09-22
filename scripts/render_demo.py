from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"
DOWNLOADS = Path.home() / "Downloads" / "import-effects-demo"
WIDTH, HEIGHT = 1200, 676
FPS = 12
COMMAND = "import-effects demo_bad_package"


def capture_output() -> list[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.fspath(ROOT / "examples")
    environment["IMPORT_EFFECTS_DEMO_DIR"] = "/tmp/import-effects-demo"
    result = subprocess.run(
        [
            os.fspath(ROOT / ".venv" / "bin" / "import-effects"),
            "demo_bad_package",
            "--ignore",
            "mkdir /tmp/import-effects-demo",
            "--ignore",
            os.devnull,
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return [line for line in result.stdout.strip().splitlines() if line]


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(name, size)


MONO = font("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 21)
MONO_BOLD = font("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 21)
LABEL = font("/usr/share/fonts/truetype/lato/Lato-Semibold.ttf", 19)


def background() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT))
    pixels = image.load()
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        for x in range(WIDTH):
            s = x / (WIDTH - 1)
            pixels[x, y] = (
                int(203 - 42 * t + 8 * s),
                int(193 + 24 * t + 12 * s),
                int(232 - 12 * t + 5 * s),
            )
    return image


def draw_frame(typed: str, visible: list[str], cursor: bool) -> Image.Image:
    image = background()
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (65, 47, 1135, 628), radius=24, fill="#10131d", outline="#ffffff66", width=2
    )
    draw.rounded_rectangle((65, 47, 1135, 99), radius=24, fill="#181c29")
    draw.rectangle((65, 75, 1135, 99), fill="#181c29")
    for index, color in enumerate(("#ff8fa3", "#ffd080", "#8de1c2")):
        x = 91 + index * 27
        draw.ellipse((x, 66, x + 14, 80), fill=color)
    draw.text((500, 65), "import-effects", font=LABEL, fill="#d9d8e8")

    prompt_y = 123
    draw.text((94, prompt_y), "$", font=MONO_BOLD, fill="#8de1c2")
    shown = typed + ("▌" if cursor else "")
    draw.text((121, prompt_y), shown, font=MONO, fill="#eceaf6")

    y = 160
    for line in visible:
        color = "#c9c8d8"
        active_font = MONO
        if line.startswith("✓"):
            color = "#8de1c2"
        elif line.startswith("⚠"):
            color = "#ffd080"
            active_font = MONO_BOLD
        elif line == "SIDE EFFECTS":
            color = "#b9a7ff"
            active_font = MONO_BOLD
        elif line.startswith("4 side effects"):
            color = "#f4b7d2"
            active_font = MONO_BOLD
        draw.text((94, y), line, font=active_font, fill=color)
        y += 27
    draw.text(
        (89, 594), "real isolated import · no package installation", font=LABEL, fill="#777b91"
    )
    return image


def main() -> None:
    lines = capture_output()
    frames: list[Image.Image] = []
    for count in range(0, len(COMMAND) + 1, 3):
        frames.extend([draw_frame(COMMAND[:count], [], True)] * 2)
    frames.extend([draw_frame(COMMAND, [], False)] * 5)
    for count in range(1, len(lines) + 1):
        frames.extend([draw_frame(COMMAND, lines[:count], False)] * 3)
    frames.extend([draw_frame(COMMAND, lines, False)] * 30)

    ASSETS.mkdir(parents=True, exist_ok=True)
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    frame_dir = DOWNLOADS / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    for old_frame in frame_dir.glob("frame-*.png"):
        old_frame.unlink()
    for index, frame in enumerate(frames):
        frame.save(frame_dir / f"frame-{index:04d}.png", optimize=True)

    gif_path = ASSETS / "demo.gif"
    frames[0].save(
        gif_path,
        save_all=True,
        append_images=frames[1:],
        duration=round(1000 / FPS),
        loop=0,
        optimize=True,
    )
    (DOWNLOADS / "import-effects-demo.gif").write_bytes(gif_path.read_bytes())
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(FPS),
            "-i",
            os.fspath(frame_dir / "frame-%04d.png"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            os.fspath(DOWNLOADS / "import-effects-demo.mp4"),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


if __name__ == "__main__":
    main()
