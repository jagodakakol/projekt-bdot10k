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


def punkty_co_odstep(wsp, odstep, poczatek=0.0):
    """Wyznacza punkty co `odstep` wzdłuż łamanej [x1, y1, x2, y2, ...] – w nich stawiamy znaczki.
    Pierwszy punkt wypada `poczatek` od początku łamanej. Zwraca listę (x, y, kx, ky):
    punkt i kierunek odcinka, na którym leży (wektor o długości 1)."""
    wynik = []
    if odstep <= 0:
        return wynik
    pozycja = poczatek        # odległość następnego znaczka od początku bieżącego odcinka
    for i in range(0, len(wsp) - 2, 2):
        x1 = wsp[i]
        y1 = wsp[i + 1]
        x2 = wsp[i + 2]
        y2 = wsp[i + 3]
        dlugosc = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)      # twierdzenie Pitagorasa
        if dlugosc == 0:
            continue
        kx = (x2 - x1) / dlugosc          # wektor kierunku odcinka o długości 1
        ky = (y2 - y1) / dlugosc
        while pozycja <= dlugosc:         # wszystkie znaczki, które wypadają na tym odcinku
            wynik.append((x1 + kx * pozycja, y1 + ky * pozycja, kx, ky))
            pozycja = pozycja + odstep
        pozycja = pozycja - dlugosc       # to, co zostało do następnego znaczka, przechodzi na kolejny odcinek
    return wynik


def normalna_w_prawo(x1, y1, x2, y2):
    """Wektor o długości 1 prostopadły do odcinka, skierowany w prawo patrząc wzdłuż odcinka
    (we współrzędnych ekranu, gdzie y rośnie w dół). Dla odcinka zerowej długości – None."""
    dx = x2 - x1
    dy = y2 - y1
    dlugosc = math.sqrt(dx * dx + dy * dy)
    if dlugosc == 0:
        return None
    return -dy / dlugosc, dx / dlugosc


def przesun_lamana(piksele, d):
    """Linia równoległa do łamanej (w pikselach ekranu), odsunięta o d w prawo (d < 0 – w lewo).
    Każdy wierzchołek przesuwamy wzdłuż dwusiecznej kąta między sąsiednimi odcinkami (tzw. miter):
    n = n1 + n2 (suma normalnych obu odcinków, znormalizowana), a długość przesunięcia to d / cos(α/2),
    gdzie cos(α/2) = n · n1. Przy bardzo ostrych kątach ograniczamy ją, żeby nie powstały długie szpice.
    Dla zamkniętego pierścienia (ostatni punkt = pierwszy) pierwszy wierzchołek też ma dwóch sąsiadów."""
    n = len(piksele) // 2
    if n < 2:
        return piksele
    zamkniety = piksele[0] == piksele[-2] and piksele[1] == piksele[-1]
    wynik = []
    for i in range(n):
        x = piksele[2 * i]
        y = piksele[2 * i + 1]
        n1 = None                                     # normalna odcinka przed wierzchołkiem
        n2 = None                                     # normalna odcinka za wierzchołkiem
        if i > 0:
            n1 = normalna_w_prawo(piksele[2 * i - 2], piksele[2 * i - 1], x, y)
        elif zamkniety:
            n1 = normalna_w_prawo(piksele[-4], piksele[-3], x, y)
        if i < n - 1:
            n2 = normalna_w_prawo(x, y, piksele[2 * i + 2], piksele[2 * i + 3])
        elif zamkniety:
            n2 = normalna_w_prawo(x, y, piksele[2], piksele[3])
        if n1 is None:
            n1 = n2
        if n2 is None:
            n2 = n1
        if n1 is None:                                # oba odcinki zerowe – zostawiamy punkt
            wynik.append(x)
            wynik.append(y)
            continue
        mx = n1[0] + n2[0]
        my = n1[1] + n2[1]
        dlugosc = math.sqrt(mx * mx + my * my)
        if dlugosc < 1e-9:                            # zawrót o 180° – bierzemy normalną pierwszego odcinka
            mx, my = n1
        else:
            mx = mx / dlugosc
            my = my / dlugosc
        cos_polowy = max(mx * n1[0] + my * n1[1], 0.25)   # ograniczenie szpic przy ostrych kątach
        wynik.append(x + mx * d / cos_polowy)
        wynik.append(y + my * d / cos_polowy)
    return wynik
