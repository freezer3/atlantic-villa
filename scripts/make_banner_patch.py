#!/usr/bin/env python3
"""Villa Atlantic banner: naklejka z nowym numerem telefonu (1:1) + poprawiony master."""
import fitz

MM = 72 / 25.4          # mm -> pt
K = 25.4 / 72           # pt -> mm

SRC = "/Users/vividq/Desktop/Villa Baner/banner-120x40-editable.pdf"
OUT_SHEET = "/Users/vividq/Desktop/Villa Baner/naklejka-nowy-numer-A4-1do1.pdf"
OUT_BANNER = "/Users/vividq/Desktop/Villa Baner/banner-120x40-nowy-numer.pdf"
FONT_BOLD = "/Library/Fonts/SpaceGrotesk-Bold.ttf"
FONT_REG = "/Library/Fonts/SpaceGrotesk-Regular.ttf"

OCEAN = (0x0A / 255, 0x4D / 255, 0x68 / 255)
BG = (0xFE / 255, 0xFD / 255, 0xFB / 255)
GREY = (0.62, 0.62, 0.62)

NEW = "+44 7550 421923"
SIZE = 96                       # identycznie jak oryginal
PATCH_MARGIN = 4.5              # mm zapasu wokol tuszu

fbold = fitz.Font(fontfile=FONT_BOLD)
freg = fitz.Font(fontfile=FONT_REG)


def ink_bbox(text, size, fontfile):
    """Zmierz realny bbox tuszu (nie metryki fontu) renderujac probke."""
    w = fitz.Font(fontfile=fontfile).text_length(text, size) + 40
    d = fitz.open()
    p = d.new_page(width=w, height=size * 2.2)
    p.insert_text((20, size * 1.5), text, fontsize=size,
                  fontfile=fontfile, fontname="F", color=(0, 0, 0))
    dpi = 600
    s = dpi / 72
    pm = p.get_pixmap(dpi=dpi)
    W, H, n, smp = pm.width, pm.height, pm.n, pm.samples
    xs, ys = [], []
    for y in range(H):
        row = y * W * n
        for x in range(W):
            i = row + x * n
            if smp[i] + smp[i + 1] + smp[i + 2] < 600:
                xs.append(x); ys.append(y)
    x0, x1 = min(xs) / s, (max(xs) + 1) / s
    y0, y1 = min(ys) / s, (max(ys) + 1) / s
    # zwroc offsety wzgledem punktu wstawienia (20, size*1.5)
    return (x0 - 20, y0 - size * 1.5, x1 - 20, y1 - size * 1.5)


off = ink_bbox(NEW, SIZE, FONT_BOLD)
ink_w, ink_h = off[2] - off[0], off[3] - off[1]
print(f"nowy numer: tusz {ink_w*K:.1f} x {ink_h*K:.1f} mm")

PATCH_W = ink_w * K + 2 * PATCH_MARGIN
PATCH_H = 40.0
print(f"naklejka: {PATCH_W:.1f} x {PATCH_H:.1f} mm")

# ---------------------------------------------------------------- arkusz A4
doc = fitz.open()
page = doc.new_page(width=297 * MM, height=210 * MM)


def patch(cx_mm, cy_mm):
    """Narysuj naklejke wysrodkowana w (cx, cy) mm."""
    x0 = (cx_mm - PATCH_W / 2) * MM
    y0 = (cy_mm - PATCH_H / 2) * MM
    r = fitz.Rect(x0, y0, x0 + PATCH_W * MM, y0 + PATCH_H * MM)
    page.draw_rect(r, color=None, fill=BG)
    # tekst: wysrodkowany po realnym tuszu
    tx = r.x0 + (r.width - ink_w) / 2 - off[0]
    ty = r.y0 + (r.height - ink_h) / 2 - off[1]
    page.insert_text((tx, ty), NEW, fontsize=SIZE, fontfile=FONT_BOLD,
                     fontname="SGB", color=OCEAN)
    # linia ciecia
    page.draw_rect(r, color=GREY, width=0.3, dashes="[3 3] 0")
    return r


r1 = patch(148.5, 72)
r2 = patch(148.5, 133)


def label(x_mm, y_mm, txt, size=9, color=(0.35, 0.35, 0.35), align=0):
    page.insert_text((x_mm * MM, y_mm * MM), txt, fontsize=size,
                     fontfile=FONT_REG, fontname="SGR", color=color)


label(10, 14, "VILLA ATLANTIC — naklejka z nowym numerem, skala 1:1", 12, OCEAN)
label(10, 21, "Drukuj w 100% (Skala: 100% / Rzeczywisty rozmiar). Nie wybieraj „Dopasuj do strony”.")
label(10, 26.5, f"Naklejka: {PATCH_W:.0f} × {PATCH_H:.0f} mm. Stary numer na banerze ma 277 × 25 mm, "
                "czyli łatka zakrywa go z zapasem ok. 4 mm z każdej strony.")
label(10, 31, "Zalaminuj arkusz, potem tnij po przerywanej linii (albo 1–2 mm na zewnątrz, "
              "żeby laminat sklejał się na krawędzi).")
label(10, 35.5, "Przyklejaj tak, żeby nowe cyfry legły dokładnie na starych. Druga sztuka jest zapasowa.")

# linijka kontrolna 100 mm
ry = 176.0
rx0 = 98.5
page.draw_line(fitz.Point(rx0 * MM, ry * MM), fitz.Point((rx0 + 100) * MM, ry * MM),
               color=OCEAN, width=0.6)
for i in range(11):
    x = (rx0 + i * 10) * MM
    h = 3.5 if i % 5 == 0 else 2.0
    page.draw_line(fitz.Point(x, ry * MM), fitz.Point(x, (ry - h) * MM),
                   color=OCEAN, width=0.6)
label(rx0, ry + 5.5, "Kontrola skali: ten odcinek musi mieć dokładnie 100 mm.", 9)

doc.save(OUT_SHEET)
doc.close()
print("zapisano:", OUT_SHEET)

# ------------------------------------------------- poprawiony master banera
b = fitz.open(SRC)
p = b[0]
old = fitz.Rect(2440, 780, 3300, 935)       # tylko numer, ikona WA nietknieta
p.add_redact_annot(old, fill=BG)
p.apply_redactions()
p.insert_text((2453.878, 890.16), NEW, fontsize=SIZE, fontfile=FONT_BOLD,
              fontname="SGB", color=OCEAN)
b.save(OUT_BANNER)
b.close()
print("zapisano:", OUT_BANNER)

# ------------------------------------------------------------------ podglady
SP = "/private/tmp/claude-501/-Users-vividq-Documents-knowlegde-monorepo-nosync/8720dc46-f669-4184-b38d-f8ce4b2cb559/scratchpad/"
d = fitz.open(OUT_SHEET)
d[0].get_pixmap(dpi=110).save(SP + "sheet.png")
d.close()
d = fitz.open(OUT_BANNER)
d[0].get_pixmap(dpi=28).save(SP + "banner_new.png")
d[0].get_pixmap(clip=fitz.Rect(2200, 700, 3402, 1000), dpi=110).save(SP + "banner_new_crop.png")
d.close()
print("podglady gotowe")
