"""Marks a collage of ESPN odds screenshots with the side our projection says covers each spread.
    python make_pick_image.py "C:\\path\\Denver_Screenshots_Collage.jpg"
The cell coordinates below belong to the Week 6 collage (4 phone screenshots side by side); a new collage needs new coordinates."""
import sys

from PIL import Image, ImageDraw, ImageFont

import board_data

SRC = sys.argv[1] if len(sys.argv) > 1 else "Denver_Screenshots_Collage.jpg"
ctx, res = board_data.run()
M = {(r["away"], r["home"]): r["margin"] for r in res}
# ESPN BET home spread lines as shown in the screenshot
HL = {("HOU", "JAX"): -2.5, ("BAL", "CLE"): 3.5, ("CAR", "PHI"): 3.5, ("CHI", "ATL"): 1.5, ("NO", "NYG"): 1.5, ("NYJ", "NE"): -7.5, ("PIT", "TB"): 2.5, ("TEN", "IND"): -7.0,
      ("ARI", "LA"): -12.5, ("BUF", "LV"): 5.5, ("LAC", "KC"): -7.5, ("DAL", "GB"): -1.5, ("WAS", "SF"): -7.5}
# spread-button centres in the 2000-wide preview of the collage (multiply by 2.16 for the 4320-wide original)
CELLS = {("HOU", "JAX"): {"away": [(293, 329)], "home": [(293, 390)]}, ("BAL", "CLE"): {"away": [(293, 502)], "home": [(293, 563)]},
         ("CAR", "PHI"): {"away": [(293, 676)], "home": [(293, 737)]}, ("CHI", "ATL"): {"away": [(293, 849)], "home": [(293, 910)]},
         ("NO", "NYG"): {"away": [(793, 307)], "home": [(793, 368)]}, ("NYJ", "NE"): {"away": [(793, 481)], "home": [(793, 542)]},
         ("PIT", "TB"): {"away": [(793, 654)], "home": [(793, 715)]}, ("TEN", "IND"): {"away": [(793, 828)], "home": [(793, 889), (1293, 195)]},
         ("ARI", "LA"): {"away": [(1293, 307)], "home": [(1293, 368)]}, ("BUF", "LV"): {"away": [(1293, 481)], "home": [(1293, 542)]},
         ("LAC", "KC"): {"away": [(1293, 654), (1792, 197)], "home": [(1293, 715), (1792, 258)]},
         ("DAL", "GB"): {"away": [(1293, 828), (1792, 371)], "home": [(1293, 889), (1792, 432)]}, ("WAS", "SF"): {"away": [(1792, 618)], "home": [(1792, 679)]}}
S = 2.16
img = Image.open(SRC).convert("RGBA")
W, H = img.size
band = 380
canvas = Image.new("RGBA", (W, H + band), (15, 17, 22, 255))
canvas.paste(img, (0, 0))
ov = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
d = ImageDraw.Draw(ov)
bold = lambda n: ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", int(n * S))
reg = lambda n: ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", int(n * S))
fb, fs, fl = bold(21), bold(13), reg(15)
col = {"g": (47, 207, 107), "y": (242, 194, 48), "r": (255, 90, 95)}
picks = []
for (aw, hm), hl in HL.items():
    cush = M[(aw, hm)] + hl
    side = "home" if cush >= 0 else "away"
    c = abs(cush)
    k = "g" if c >= 3 else "y" if c >= 1.5 else "r"
    picks.append((aw, hm, hm if side == "home" else aw, hl if side == "home" else -hl, c, k))
    for cx, cy in CELLS[(aw, hm)][side]:
        d.rounded_rectangle([(cx - 37) * S, (cy - 28) * S, (cx + 37) * S, (cy + 28) * S], radius=14, fill=col[k] + (95,), outline=col[k] + (255,), width=8)
        px, pw, ph = (cx - 135) * S, 52 * S, 24 * S
        d.rounded_rectangle([px - pw / 2, cy * S - ph / 2, px + pw / 2, cy * S + ph / 2], radius=14, fill=col[k] + (255,))
        t = f"+{c:.1f}"
        d.text((px - d.textlength(t, font=fs) / 2, cy * S - fs.size / 2 - 2), t, font=fs, fill=(10, 12, 16, 255))
y = H + 28
d.text((60, y), "Highlighted = the team our projection says covers the spread (projected margin vs the ESPN line shown)", font=fb, fill=(240, 240, 240, 255))
d.text((60, y + int(36 * S)), "The tag beside each team is how many points our projection beats the line by:", font=fl, fill=(205, 210, 220, 255))
x, yy = 60, y + int(66 * S)
for k, lab in (("g", "3 or more: solid lean"), ("y", "1.5 to 3: lean"), ("r", "under 1.5: coin flip")):
    d.rounded_rectangle([x, yy, x + int(26 * S), yy + int(22 * S)], radius=8, fill=col[k] + (255,))
    d.text((x + int(34 * S), yy), lab, font=fl, fill=(230, 230, 235, 255))
    x += int(34 * S) + int(d.textlength(lab, font=fl)) + int(40 * S)
d.text((60, y + int(100 * S)), "Spread picks only. Many are not +EV at these prices, and the raw projection has not yet beaten the market in backtests, so read these as opinions, not edges.", font=fl, fill=(160, 166, 180, 255))
d.text((60, y + int(124 * S)), "Lines are as on your screen (ESPN BET). Projections as of Fri Oct 16.", font=fl, fill=(160, 166, 180, 255))
out = Image.alpha_composite(canvas, ov).convert("RGB")
out.save("ESPN odds with picks.png")
out.save("ESPN odds with picks.jpg", quality=92)
for p in picks:
    print(f"{p[0]}@{p[1]}: {p[2]} {p[3]:+g}  beats the line by {p[4]:.1f}  ({p[5]})")
