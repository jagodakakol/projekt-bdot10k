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


# --- KROK C3: wypełnienia wzorem i znaczek w środku obszaru ---

def odcinki_wewnatrz(pierscienie, y):
    """Część poziomej prostej na wysokości y, która leży w wielokącie (z dziurami) – lista odcinków (xa, xb).
    To ta sama idea co w punkt_w_wielokacie: liczymy punkty przecięcia prostej z brzegami wielokąta
    i sortujemy je od lewej. Idąc od lewej, każde przecięcie zmienia "na zewnątrz" na "w środku" i odwrotnie,
    więc w środku leżą odcinki od 1. do 2. przecięcia, od 3. do 4. itd. (reguła parzystości – dziury same
    wypadają). Warunek (y1 > y) != (y2 > y) liczy wierzchołek leżący dokładnie na prostej tylko raz."""
    przeciecia = []
    for wsp in pierscienie:
        for i in range(0, len(wsp) - 2, 2):
            y1 = wsp[i + 1]
            y2 = wsp[i + 3]
            if (y1 > y) != (y2 > y):
                x1 = wsp[i]
                x2 = wsp[i + 2]
                przeciecia.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    przeciecia.sort()
    odcinki = []
    for k in range(0, len(przeciecia) - 1, 2):
        odcinki.append((przeciecia[k], przeciecia[k + 1]))
    return odcinki


def prostokat_wspolrzednych(wsp):
    """Prostokąt otaczający łamaną [x1, y1, x2, y2, ...]: (x_min, y_min, x_max, y_max)."""
    xs = wsp[0::2]
    ys = wsp[1::2]
    return min(xs), min(ys), max(xs), max(ys)


def punkty_wzoru(pierscienie, dx, dy, przes_wiersza, przes_kolumny, x0, y0, okno):
    """Punkty siatki wzoru (np. drzewka w lesie), które leżą w wielokącie i w oknie (x_min, y_min, x_max, y_max).
    Siatka: kolumny co dx, wiersze co dy, zaczepiona w punkcie (x0, y0) – dzięki temu przy przesuwaniu mapy
    wzór "stoi" w terenie. Co drugi wiersz jest przesunięty w poziomie o przes_wiersza, co druga kolumna
    w pionie o przes_kolumny (tak opisuje to QGIS). Nie sprawdzamy każdego punktu osobno metodą półprostej,
    tylko dla każdego wiersza raz liczymy odcinki wewnątrz wielokąta (odcinki_wewnatrz) i bierzemy
    punkty siatki, które na nie wypadają – to dużo szybsze przy dużych lasach."""
    if dx <= 0 or dy <= 0 or len(pierscienie[0]) < 6:
        return []
    p = prostokat_wspolrzednych(pierscienie[0])     # obwód otacza cały wielokąt
    x_min = max(p[0], okno[0])
    y_min = max(p[1], okno[1])
    x_max = min(p[2], okno[2])
    y_max = min(p[3], okno[3])
    if x_min > x_max or y_min > y_max:
        return []                                   # wielokąt poza oknem
    if przes_kolumny == 0:
        przebiegi = [(None, 0.0)]                   # wszystkie kolumny w tych samych wierszach
    else:
        przebiegi = [(0, 0.0), (1, przes_kolumny)]  # kolumny parzyste, potem nieparzyste (przesunięte)
    wynik = []
    for parzystosc, dy_kolumny in przebiegi:
        r_od = math.ceil((y_min - y0 + dy_kolumny) / dy)
        r_do = math.floor((y_max - y0 + dy_kolumny) / dy)
        for r in range(r_od, r_do + 1):
            y = y0 + r * dy - dy_kolumny
            dx_wiersza = przes_wiersza if r % 2 == 1 else 0.0
            for xa, xb in odcinki_wewnatrz(pierscienie, y):
                xa = max(xa, x_min)
                xb = min(xb, x_max)
                c_od = math.ceil((xa - x0 + dx_wiersza) / dx)
                c_do = math.floor((xb - x0 + dx_wiersza) / dx)
                for c in range(c_od, c_do + 1):
                    if parzystosc is None or c % 2 == parzystosc:
                        wynik.append((x0 + c * dx - dx_wiersza, y))
    return wynik


def obroc_wspolrzedne(wsp, cos_k, sin_k, x0, y0):
    """Obrót łamanej [x1, y1, ...] wokół punktu (x0, y0): x' = x·cos − y·sin, y' = x·sin + y·cos."""
    wynik = []
    for i in range(0, len(wsp) - 1, 2):
        x = wsp[i] - x0
        y = wsp[i + 1] - y0
        wynik.append(x * cos_k - y * sin_k)
        wynik.append(x * sin_k + y * cos_k)
    return wynik


def odcinki_kreskowania(pierscienie, odstep, kat, przesuniecie, x0, y0, okno):
    """Kreskowanie wielokąta (np. bagno): równoległe linie co `odstep` pod kątem `kat` (w stopniach,
    przeciwnie do ruchu wskazówek zegara od poziomu; współrzędne ekranu, y w dół), obcięte do wielokąta.
    Obracamy wielokąt o kąt kreskowania, żeby kreski stały się poziome, tniemy go poziomymi prostymi
    co `odstep` (odcinki_wewnatrz) i końce otrzymanych odcinków obracamy z powrotem.
    Linie są zaczepione w (x0, y0), więc przy przesuwaniu mapy stoją w terenie. Wynik: [(x1, y1, x2, y2), ...]."""
    if odstep <= 0 or len(pierscienie[0]) < 6:
        return []
    t = math.radians(kat)
    cos_k = math.cos(t)
    sin_k = math.sin(t)
    obrocone = []
    for wsp in pierscienie:
        obrocone.append(obroc_wspolrzedne(wsp, cos_k, sin_k, x0, y0))
    p = prostokat_wspolrzednych(obrocone[0])
    # okno po obrocie (jego cztery rogi) – kresek poza oknem nie liczymy
    rogi = obroc_wspolrzedne([okno[0], okno[1], okno[2], okno[1], okno[2], okno[3], okno[0], okno[3]],
                             cos_k, sin_k, x0, y0)
    o = prostokat_wspolrzednych(rogi)
    x_min = max(p[0], o[0])
    y_min = max(p[1], o[1])
    x_max = min(p[2], o[2])
    y_max = min(p[3], o[3])
    if x_min > x_max or y_min > y_max:
        return []
    wynik = []
    r_od = math.ceil((y_min - przesuniecie) / odstep)
    r_do = math.floor((y_max - przesuniecie) / odstep)
    for r in range(r_od, r_do + 1):
        y = r * odstep + przesuniecie
        for xa, xb in odcinki_wewnatrz(obrocone, y):
            xa = max(xa, x_min)
            xb = min(xb, x_max)
            if xb <= xa:
                continue
            # obrót z powrotem (o kąt przeciwny): x = x'·cos + y'·sin, y = −x'·sin + y'·cos
            wynik.append((x0 + xa * cos_k + y * sin_k, y0 - xa * sin_k + y * cos_k,
                          x0 + xb * cos_k + y * sin_k, y0 - xb * sin_k + y * cos_k))
    return wynik


def pole_i_srodek_pierscienia(wsp):
    """Pole (ze znakiem) i środek ciężkości jednego pierścienia – wzory Gaussa (shoelace):
    A  = ½ Σ (xᵢ·yᵢ₊₁ − xᵢ₊₁·yᵢ)
    Cx = 1/(6A) Σ (xᵢ + xᵢ₊₁)(xᵢ·yᵢ₊₁ − xᵢ₊₁·yᵢ),  Cy = 1/(6A) Σ (yᵢ + yᵢ₊₁)(xᵢ·yᵢ₊₁ − xᵢ₊₁·yᵢ).
    Liczymy względem pierwszego wierzchołka, bo współrzędne PUWG 1992 są duże (setki tysięcy metrów)
    i iloczyny takich liczb traciłyby dokładność."""
    xr = wsp[0]
    yr = wsp[1]
    n = len(wsp) // 2
    a2 = 0.0            # podwojone pole
    sx = 0.0
    sy = 0.0
    for k in range(n):
        x1 = wsp[2 * k] - xr
        y1 = wsp[2 * k + 1] - yr
        j = (k + 1) % n                             # następny wierzchołek (po ostatnim – pierwszy)
        x2 = wsp[2 * j] - xr
        y2 = wsp[2 * j + 1] - yr
        iloczyn = x1 * y2 - x2 * y1
        a2 += iloczyn
        sx += (x1 + x2) * iloczyn
        sy += (y1 + y2) * iloczyn
    if a2 == 0:
        return 0.0, xr, yr                          # pierścień zdegenerowany (zerowe pole)
    return a2 / 2, xr + sx / (3 * a2), yr + sy / (3 * a2)


def srodek_ciezkosci(pierscienie):
    """Środek ciężkości wielokąta z dziurami: środek obwodu "minus" środki dziur, ważone polami
    C = (A₀·C₀ − Σ Aₕ·Cₕ) / (A₀ − Σ Aₕ). Pola bierzemy bez znaku, więc kierunek obiegu pierścieni
    nie ma znaczenia. Zwraca (pole, x, y)."""
    pole, x, y = pole_i_srodek_pierscienia(pierscienie[0])
    pole = abs(pole)
    suma_x = pole * x
    suma_y = pole * y
    for dziura in pierscienie[1:]:
        p, xd, yd = pole_i_srodek_pierscienia(dziura)
        p = abs(p)
        pole -= p
        suma_x -= p * xd
        suma_y -= p * yd
    if pole <= 0:
        return 0.0, x, y
    return pole, suma_x / pole, suma_y / pole


def punkt_na_powierzchni(pierscienie):
    """Punkt, który na pewno leży w wielokącie (środek ciężkości np. litery "C" wypada poza nią).
    Jak w bibliotece GEOS (pointOnSurface): prowadzimy poziomą prostą przez środek wysokości wielokąta,
    bierzemy najdłuższy odcinek tej prostej leżący w środku (odcinki_wewnatrz) i jego środek."""
    p = prostokat_wspolrzednych(pierscienie[0])
    y = (p[1] + p[3]) / 2
    najdluzszy = None
    for xa, xb in odcinki_wewnatrz(pierscienie, y):
        if najdluzszy is None or xb - xa > najdluzszy[1] - najdluzszy[0]:
            najdluzszy = (xa, xb)
    if najdluzszy is None:
        pole, x, y = srodek_ciezkosci(pierscienie)
        return x, y
    return (najdluzszy[0] + najdluzszy[1]) / 2, y
