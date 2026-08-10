# Baner 120 × 40 cm — zmierzona specyfikacja

Zmierzone 2026-08-10 z pliku, z którego baner faktycznie wydrukowano:
`~/Desktop/Villa Baner/banner-120x40-editable.pdf` (Quartz PDF, eksport z `banner-120x40-editable.pptx`).

Strona PDF: 3402 × 1134 pt = **1200,15 × 400,05 mm**, czyli skala 1:1 wobec wydruku 120 × 40 cm.

## Kolory (z content streamu PDF, nie z pipety)

| rola | hex |
|---|---|
| ocean (tekst, ikona, QR) | `#0A4D68` |
| coral (VILLA ATLANTIC) | `#E8664D` |
| tło | `#FEFDFB` |

## Geometria elementów (mm od lewej/górnej krawędzi banera, bbox tuszu)

| element | x | y | szer. | wys. |
|---|---|---|---|---|
| RENT ME | 174,6 – 477,5 | 42,2 – 131,8 | 303 | 90 |
| VILLA ATLANTIC | 65,6 – 874,9 | 149,9 – 254,3 | 809 | 104 |
| www.atlanticvilla.net | 68,6 – 714,9 | 269,3 – 344,9 | 646 | 76 |
| ikona WhatsApp | 798,3 – 851,8 | 276,2 – 329,7 | 53,5 | 53,5 |
| numer telefonu (cyfry) | 869,1 – 1146,4 | 289,9 – 314,5 | **277** | **25** |
| QR (sam wzór, bez ramki) | — | — | 193 | 193 |

Numer zajmuje 23,1% szerokości banera. Weryfikacja niezależna od przeliczeń mm:
stosunek pikseli w renderze całej strony daje te same 23,1%.

## Typografia numeru

Space Grotesk Bold, 96 pt, tracking `Tc 0.0206` (artefakt eksportu z PPTX, ok. 0,7 mm na znak).
Punkt wstawienia w PDF: `(2453.878, 890.16)` pt, układ top-left.
Font w systemie: `/Library/Fonts/SpaceGrotesk-Bold.ttf`.

## QR

Koduje `https://www.atlanticvilla.net`. Nie zawiera numeru telefonu, więc zmiana numeru
nie wymaga przedruku QR-a.

## Łatka na zmianę numeru (procedura, 2026-08-10)

Numer zmieniony z `+34 658 31 12 39` na `+44 7550 421923`. Zamiast przedruku całego banera:
naklejka 1:1 na kartce A4, laminowana, naklejana na stary numer.

- Nowy numer w tym samym foncie i rozmiarze ma 276,5 × 24,7 mm, czyli praktycznie ten sam
  ślad co stary (277 × 25 mm). Skalowanie nie było potrzebne — trzeba było tylko wyzerować
  tracking, żeby zmieściło się w tej samej szerokości.
- Łatka: 285 × 40 mm, tło `#FEFDFB`, zapas ok. 4 mm wokół starego tuszu, 13 mm luzu do ikony WhatsApp.
- Arkusz: A4 poziomo, dwie łatki, linia cięcia, odcinek kontrolny 100 mm do sprawdzenia skali wydruku.

Pliki: `~/Desktop/Villa Baner/naklejka-nowy-numer-A4-1do1.pdf`,
poprawiony master `~/Desktop/Villa Baner/banner-120x40-nowy-numer.pdf`.
Generator: `scripts/make_banner_patch.py` w tym repo.

## Uwaga o starych plikach

`banner/banner-120x40-150dpi.png` to nieaktualny render (placeholder `+XX XXX`, zły układ,
brak QR). Nie używać jako źródła prawdy ani do kontroli wymiarów.

## Numer na stronie

`index.html` linkuje do `wa.me/48604782783` — to numer właściciela, celowo inny niż numer
na banerze. Nie ujednolicać.
