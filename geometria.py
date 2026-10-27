# geometria.py – algorytmy geometrii obliczeniowej używane w programie
# Projekt z Geometrii obliczeniowej, dr hab. inż. Waldemar Izdebski
#
# Współrzędne łamanych i pierścieni są zapisane płasko: [x1, y1, x2, y2, ...] (tak jak w gml.py).

import math


def odleglosc_od_odcinka(px, py, x1, y1, x2, y2):
    """Odległość punktu P(px, py) od odcinka AB, gdzie A = (x1, y1), B = (x2, y2).
    Rzutujemy P na prostą AB: t = (AP · AB) / |AB|² mówi, gdzie wypada rzut (t = 0 w A, t = 1 w B).
    t obcinamy do przedziału [0, 1], żeby rzut nie wyszedł poza odcinek, i liczymy odległość P od rzutu."""
    dx = x2 - x1
    dy = y2 - y1
    dlugosc2 = dx * dx + dy * dy                     # kwadrat długości odcinka
    if dlugosc2 == 0:
        t = 0.0                                      # odcinek zerowej długości – to po prostu punkt A
    else:
        t = ((px - x1) * dx + (py - y1) * dy) / dlugosc2   # iloczyn skalarny AP · AB podzielony przez |AB|²
        t = max(0.0, min(1.0, t))
    rx = x1 + t * dx                                 # rzut punktu P na odcinek
    ry = y1 + t * dy
    return math.sqrt((px - rx) ** 2 + (py - ry) ** 2)


def odleglosc_od_lamanej(px, py, wsp):
    """Najmniejsza odległość punktu od łamanej [x1, y1, x2, y2, ...] – minimum po wszystkich odcinkach."""
    najmniejsza = float("inf")
    for i in range(0, len(wsp) - 2, 2):
        d = odleglosc_od_odcinka(px, py, wsp[i], wsp[i + 1], wsp[i + 2], wsp[i + 3])
        if d < najmniejsza:
            najmniejsza = d
    return najmniejsza


def punkt_w_wielokacie(px, py, pierscienie):
    """Czy punkt P leży w wielokącie z dziurami – metoda półprostej (reguła parzystości).
    Z punktu prowadzimy półprostą w prawo i liczymy, ile razy przecina brzegi wielokąta.
    Nieparzysta liczba przecięć = punkt w środku, parzysta = na zewnątrz.
    Dziury liczą się same: z wnętrza dziury półprosta przecina i brzeg dziury, i obwód, czyli parzyście.
    pierscienie = [obwód, dziura1, ...], każdy zamknięty (pierwszy punkt powtórzony na końcu)."""
    w_srodku = False
    for wsp in pierscienie:
        for i in range(0, len(wsp) - 2, 2):
            x1 = wsp[i]
            y1 = wsp[i + 1]
            x2 = wsp[i + 2]
            y2 = wsp[i + 3]
            # czy odcinek przecina poziomą prostą przechodzącą przez P (jeden koniec nad, drugi pod nią)
            if (y1 > py) != (y2 > py):
                # x punktu przecięcia odcinka z tą prostą (z proporcji w trójkątach podobnych)
                x_przeciecia = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
                if x_przeciecia > px:              # przecięcie leży na półprostej w prawo od P
                    w_srodku = not w_srodku
    return w_srodku
