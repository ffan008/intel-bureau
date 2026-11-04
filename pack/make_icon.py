"""生成 App 图标：深空蓝底 + 青色 HUD 雷达，和大屏配色一致。

用法：.venv/bin/python pack/make_icon.py
产出：pack/appicon.icns（以及 iconset 目录，可删）
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

S = 1024
CYAN = (34, 228, 255)
HERE = Path(__file__).resolve().parent


def base_layer() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=228, fill=255)

    grad = Image.new("RGB", (S, S))
    d = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / S
        d.line([(0, y), (S, y)], fill=(int(12 - 9 * t), int(26 - 18 * t), int(46 - 28 * t)))

    img.paste(grad, (0, 0), mask)
    return img, mask  # type: ignore[return-value]


def draw_hud() -> Image.Image:
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    dl = ImageDraw.Draw(layer)
    cx = cy = S // 2

    # 扫描扇区
    dl.pieslice([cx - 340, cy - 340, cx + 340, cy + 340], start=-70, end=-10, fill=(*CYAN, 34))

    # 三圈同心环，越外越淡
    for i, rad in enumerate((150, 250, 340)):
        dl.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=(*CYAN, 210 - i * 55), width=9 - i * 2)

    # 十字准线
    dl.line([cx - 400, cy, cx + 400, cy], fill=(*CYAN, 45), width=3)
    dl.line([cx, cy - 400, cx, cy + 400], fill=(*CYAN, 45), width=3)

    # 中心辉光
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([cx - 95, cy - 95, cx + 95, cy + 95], fill=(*CYAN, 110))
    layer = Image.alpha_composite(layer, glow.filter(ImageFilter.GaussianBlur(42)))

    # 中心亮点
    ImageDraw.Draw(layer).ellipse([cx - 33, cy - 33, cx + 33, cy + 33], fill=(186, 250, 255, 255))

    # 四个角的小刻度，做出 HUD 边框感
    d = ImageDraw.Draw(layer)
    for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        x0, y0 = cx + sx * 380, cy + sy * 380
        d.line([x0, y0, x0 - sx * 70, y0], fill=(*CYAN, 130), width=5)
        d.line([x0, y0, x0, y0 - sy * 70], fill=(*CYAN, 130), width=5)
    return layer


def main() -> int:
    img, mask = base_layer()
    img = Image.alpha_composite(img, Image.composite(draw_hud(), Image.new("RGBA", (S, S), (0, 0, 0, 0)), mask))

    png = HERE / "appicon.png"
    img.save(png)

    iconset = HERE / "appicon.iconset"
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir()
    for size in (16, 32, 64, 128, 256, 512, 1024):
        scaled = img.resize((size, size), Image.LANCZOS)
        scaled.save(iconset / f"icon_{size}x{size}.png")
        if size <= 512:
            scaled.resize((size * 2, size * 2), Image.LANCZOS).save(iconset / f"icon_{size}x{size}@2x.png")

    out = HERE / "appicon.icns"
    r = subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"iconutil 失败：{r.stderr}", file=sys.stderr)
        return 1
    shutil.rmtree(iconset)
    print(f"已生成 {out}（{out.stat().st_size // 1024} KB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
