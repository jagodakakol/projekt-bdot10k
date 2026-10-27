# mapa.py – przeglądarka danych BDOT10k całego powiatu
# Projekt z Geometrii obliczeniowej, dr hab. inż. Waldemar Izdebski
#
# Historia kroków:
# Kroki 1–3: odczyt GML, okienko z mapą (przeliczanie współrzędnych teren -> ekran), nawigacja.
# Kroki 4a–4c: znaki umowne z plików stylu QML wtyczki GUGiK (na razie dla 7 klas), ząbki na granicy rezerwatu.
# Krok A1 (według kryteriów z PDF): cały powiat – wszystkie pliki GML z wybranego folderu albo ZIP
#          (wczytywanie strumieniowe w pliku gml.py), proste kolory warstw, start na całym powiecie,
#          obiekty mniejsze niż piksel jako kropka, okno o zmiennym rozmiarze.
# Krok B1: indeks przestrzenny – siatka regularna (plik indeks.py), przełącznik "z indeksem / bez",
#          w pasku stanu czas wyboru obiektów, liczba sprawdzonych i narysowanych obiektów.
# Krok B2: panel warstw po lewej – klasy pogrupowane według kategorii (SW, SK, BU, PT…),
#          włączanie i wyłączanie, zmiana koloru i grubości linii.
# Krok B3: identyfikacja obiektu kliknięciem (algorytmy w pliku geometria.py): punkt w wielokącie
#          metodą półprostej, odległość punktu od odcinka z tolerancją w pikselach; okno z atrybutami.
# Krok C1: znaki umowne dla wszystkich klas z naszego pliku znaki/znaki.json (robi go qml_na_json.py
#          ze stylów wtyczki GUGiK); wielkości w mm mapy przeliczane na piksele według skali widoku,
#          linie przesunięte w bok, znaczki na liniach i w punktach (kształty proste; SVG w kroku C2).

import os
import sys
import math
import time
import json
import tkinter as tk
from tkinter import filedialog
from tkinter import colorchooser

import gml          # nasz plik gml.py – wczytywanie danych
import indeks       # nasz plik indeks.py – indeks przestrzenny (siatka regularna)
import geometria    # nasz plik geometria.py – punkt w wielokącie, odległość od odcinka

# --- USTAWIENIA ---

FOLDER_PROJEKTU = os.path.dirname(os.path.abspath(__file__))
FOLDER_DANYCH = os.path.join(FOLDER_PROJEKTU, "dane")      # tu otwiera się okno wyboru folderu
FOLDER_ZNAKOW = os.path.join(FOLDER_PROJEKTU, "znaki")

# znaki umowne – nasz plik JSON zrobiony skryptem qml_na_json.py ze stylów wtyczki GUGiK
PLIK_ZNAKOW = os.path.join(FOLDER_ZNAKOW, "znaki.json")

# rozmiar mapy w pikselach (zmienia się razem z rozmiarem okna – patrz zmiana_rozmiaru)
SZEROKOSC = 900
WYSOKOSC = 650

# identyfikacja: kliknięcie trafia w linię albo punkt, jeśli jest bliżej niż tyle pikseli
TOLERANCJA_PIKSELI = 5
KOLOR_ZAZNACZENIA = "#ff00ff"

# --- PROSTE KOLORY (wariant podstawowy: każda warstwa ma stały kolor) ---
KOLORY_KATEGORII = {
    "PT": "#d9ead3",   # pokrycie terenu – jasna zieleń (niektóre klasy mają swój kolor, niżej)
    "SW": "#1f78b4",   # sieć wodna – niebieski
    "SK": "#8c564b",   # sieć komunikacyjna – brązowy
    "SU": "#9467bd",   # sieć uzbrojenia terenu – fioletowy
    "BU": "#d62728",   # budynki i budowle – czerwony
    "KU": "#ff7f0e",   # kompleksy użytkowania terenu – pomarańczowy
    "TC": "#2ca02c",   # tereny chronione – zielony
    "AD": "#444444",   # podział administracyjny – ciemnoszary
    "OI": "#7f7f7f",   # inne obiekty – szary
    "RT": "#a0522d",   # rzeźba terenu – brązowy
}
KOLORY_KLAS = {        # wyjątki w pokryciu terenu, żeby las był zielony, a woda niebieska
    "PTLZ_A": "#8fc98f",   # lasy
    "PTWP_A": "#9ecae1",   # wody powierzchniowe
    "PTTR_A": "#e5f2d5",   # roślinność trawiasta
    "PTZB_A": "#ead9d9",   # zabudowa
    "PTUT_A": "#f0eac0",   # uprawy trwałe
    "PTRK_A": "#c7e0b4",   # roślinność krzewiasta
    "PTKM_A": "#dddddd",   # tereny pod drogami i torami
    "PTPL_A": "#e6e6e6",   # place
    "OIMK_A": "#b8d8d0",   # bagna i tereny podmokłe
    "OISZ_A": "#c9e0a8",   # szuwary
    "OIPR_P": "#4f8f3a",   # drzewa, źródła (obiekty przyrodnicze)
    "OIPR_L": "#4f8f3a",   # rzędy drzew, linie oddziałowe w lesie
}
# obszary, które nakładają się na pokrycie terenu (gminy, rezerwaty, kompleksy) – tylko obrys,
# żeby nie zakryły reszty mapy
TYLKO_OBRYS = ["AD", "TC", "KU"]
# kolejność kategorii przy rysowaniu prostymi kolorami (pokrycie terenu na samym dole)
KOLEJNOSC_KATEGORII = ["PT", "KU", "TC", "AD", "RT", "SW", "SK", "SU", "BU", "OI"]


def ciemniejszy(kolor):
    """"#8fc98f" -> ten sam kolor, ale ciemniejszy (na obrys). Składowe R, G, B mnożymy przez 0,6."""
    r = int(kolor[1:3], 16)                       # dwa znaki szesnastkowe -> liczba 0–255
    g = int(kolor[3:5], 16)
    b = int(kolor[5:7], 16)
    return f"#{int(r * 0.6):02x}{int(g * 0.6):02x}{int(b * 0.6):02x}"


def ustawienia_domyslne(klasa):
    """Ustawienia warstwy (klasy) do rysowania prostymi kolorami. W kroku B2 będzie można je zmieniać."""
    kategoria = klasa[:2]
    kolor = KOLORY_KLAS.get(klasa, KOLORY_KATEGORII.get(kategoria, "#888888"))
    wypelnij = klasa.endswith("_A") and kategoria not in TYLKO_OBRYS
    obrys = kolor
    if wypelnij or klasa.endswith("_P"):
        obrys = ciemniejszy(kolor)
    return {"widoczna": True, "kolor": kolor, "obrys": obrys, "wypelnij": wypelnij, "grubosc": 1}


def miejsce_w_kolejnosci(klasa):
    """Klucz sortowania klas przy prostych kolorach: najpierw wypełnione poligony, potem obrysy,
    linie i punkty, a w każdej grupie według kategorii. Python porównuje takie trójki po kolei."""
    if klasa.endswith("_P"):
        grupa = 3
    elif klasa.endswith("_L"):
        grupa = 2
    elif warstwy[klasa]["wypelnij"]:
        grupa = 0
    else:
        grupa = 1
    kategoria = klasa[:2]
    if kategoria in KOLEJNOSC_KATEGORII:
        numer = KOLEJNOSC_KATEGORII.index(kategoria)
    else:
        numer = len(KOLEJNOSC_KATEGORII)
    return (grupa, numer, klasa)


# --- ZNAKI UMOWNE (plik znaki.json) ---
# Plik robi skrypt qml_na_json.py ze stylów QML wtyczki GUGiK. Najważniejsza jest lista "warstwy":
# warstwy mapy od spodu do wierzchu; każda ma klasę, pole z kodem (kodKarto10k), filtr, skalę,
# przy której znika, i słownik "znaki": kod obiektu -> znak umowny złożony z warstw (wypełnienie, linia,
# znaczki...). Wszystkie wielkości są w milimetrach mapy w skali 1:10 000.

def wczytaj_plik_znakow():
    """Czyta znaki.json. Jeśli pliku nie ma, zwraca None (wtedy działają tylko proste kolory)."""
    if not os.path.exists(PLIK_ZNAKOW):
        return None
    with open(PLIK_ZNAKOW, encoding="utf-8") as plik:
        return json.load(plik)


def pasuje_do_filtra(obiekt, filtr):
    """Filtr warstwy, np. {"pole": "polozenie", "wartosci": ["na powierzchni gruntu"]}:
    obiekt pasuje, gdy wartość jego pola jest na liście. Brak filtra – pasuje każdy obiekt."""
    if filtr is None:
        return True
    return obiekt["atrybuty"].get(filtr["pole"]) in filtr["wartosci"]


def znak_obiektu(warstwa_mapy, obiekt):
    """Znak umowny dla obiektu według jego kodu (np. kodKarto10k = "0010_318_1"); None, jeśli kodu
    nie ma w tej warstwie. Warstwa bez pola kodu ma jeden znak "*" dla wszystkich obiektów."""
    if warstwa_mapy["pole"] is None:
        return warstwa_mapy["znaki"]["*"]
    return warstwa_mapy["znaki"].get(obiekt["atrybuty"].get(warstwa_mapy["pole"]))


def wartosc_z_pola(obiekt, wzor, domyslna):
    """Wielkość liczona z atrybutu obiektu, np. szerokość jezdni: mnożnik · szerokoscNawierzchni + dodatek.
    Gdy wzoru nie ma albo obiekt nie ma tego atrybutu – wartość domyślna ze stylu."""
    if wzor is None:
        return domyslna
    tekst = obiekt["atrybuty"].get(wzor["pole"])
    if tekst is None:
        return domyslna
    try:
        return float(tekst) * wzor["mnoznik"] + wzor["dodatek"]
    except ValueError:
        return domyslna


# --- PRZELICZANIE WSPÓŁRZĘDNYCH ---
# Widok mapy opisują trzy liczby:
#   skala  – ile pikseli przypada na 1 metr w terenie
#   x0, y0 – współrzędne terenowe lewego górnego rogu okienka
# To te same liczby, które QGIS zapisał w pliku .jgw przy eksporcie mapy.
widok = {"skala": 1.0, "x0": 0.0, "y0": 0.0}


def teren_na_ekran(x, y):
    """Zamienia współrzędne terenowe (metry, PUWG 1992) na piksele w okienku."""
    x_ekr = (x - widok["x0"]) * widok["skala"]
    y_ekr = (widok["y0"] - y) * widok["skala"]   # minus, bo na ekranie y rośnie w dół
    return x_ekr, y_ekr


def ekran_na_teren(x_ekr, y_ekr):
    """Odwrotnie: piksele w okienku -> współrzędne terenowe."""
    x = widok["x0"] + x_ekr / widok["skala"]
    y = widok["y0"] - y_ekr / widok["skala"]
    return x, y


def pokaz_prostokat(prostokat):
    """Ustawia widok tak, żeby podany prostokąt (x_min, y_min, x_max, y_max) zmieścił się w okienku.
    Skala jest jedna dla obu osi, więc mapa nie jest rozciągnięta."""
    x_min, y_min, x_max, y_max = prostokat
    skala_x = SZEROKOSC / max(x_max - x_min, 1)
    skala_y = WYSOKOSC / max(y_max - y_min, 1)
    widok["skala"] = min(skala_x, skala_y)        # mniejsza skala, żeby zmieściło się w obu kierunkach
    # środek prostokąta ma wypaść na środku okienka
    srodek_x = (x_min + x_max) / 2
    srodek_y = (y_min + y_max) / 2
    widok["x0"] = srodek_x - (SZEROKOSC / 2) / widok["skala"]
    widok["y0"] = srodek_y + (WYSOKOSC / 2) / widok["skala"]


def prostokaty_nachodza(a, b):
    """Sprawdza, czy dwa prostokąty (x_min, y_min, x_max, y_max) mają część wspólną.
    Nie nachodzą tylko wtedy, gdy jeden leży całkiem na lewo, na prawo, pod albo nad drugim."""
    if a[2] < b[0] or a[0] > b[2]:   # a całkiem na lewo albo na prawo od b
        return False
    if a[3] < b[1] or a[1] > b[3]:   # a całkiem pod albo nad b
        return False
    return True


# --- RYSOWANIE ---

def lista_pikseli(wsp):
    """Zamienia współrzędne terenowe [x1, y1, x2, y2, ...] na płaską listę pikseli dla tkintera.
    Prosta generalizacja: pomija punkty, które na ekranie wypadłyby bliżej niż 1 piksel
    od poprzedniego (i tak nie byłoby ich widać, a rysowanie idzie dużo szybciej).
    Ostatni punkt zostawiamy zawsze, żeby pierścienie poligonów były domknięte.
    Wzór z teren_na_ekran wpisujemy tu bezpośrednio, bo ta funkcja liczy miliony punktów."""
    x0 = widok["x0"]
    y0 = widok["y0"]
    skala = widok["skala"]
    wynik = []
    ostatni_x = None
    ostatni_y = None
    n = len(wsp)
    for i in range(0, n, 2):
        x_ekr = (wsp[i] - x0) * skala
        y_ekr = (y0 - wsp[i + 1]) * skala
        if ostatni_x is None or i == n - 2 or abs(x_ekr - ostatni_x) >= 1 or abs(y_ekr - ostatni_y) >= 1:
            wynik.append(x_ekr)
            wynik.append(y_ekr)
            ostatni_x = x_ekr
            ostatni_y = y_ekr
    return wynik


def linie_obiektu(obiekt):
    """Łamane, po których rysujemy linię: dla linii jej części, dla poligonu wszystkie pierścienie."""
    if obiekt["typ"] == "linia":
        return obiekt["czesci"]
    linie = []
    if obiekt["typ"] == "poligon":
        for pierscienie in obiekt["czesci"]:
            for pierscien in pierscienie:
                linie.append(pierscien)
    return linie


def wybierz_widoczne(klasa, ekran, licz=True):
    """Obiekty klasy, których prostokąt otaczający nachodzi na widoczny fragment mapy.
    Z indeksem sprawdzamy tylko kandydatów z komórek siatki, które przecina okienko;
    bez indeksu – po kolei wszystkie obiekty klasy. Czas i liczbę sprawdzeń zapisujemy w statystyce."""
    start = time.time()
    if uzyj_indeksu.get():
        do_sprawdzenia = indeks.kandydaci(indeks_przestrzenny[klasa], ekran)
    else:
        do_sprawdzenia = dane[klasa]
    widoczne = []
    for obiekt in do_sprawdzenia:
        if prostokaty_nachodza(obiekt["prostokat"], ekran):
            widoczne.append(obiekt)
    if licz:
        statystyka["sprawdzone"] += len(do_sprawdzenia)
        statystyka["czas_wyboru"] += time.time() - start
    return widoczne


def rysuj_jako_piksel(obiekt, kolor, zajete):
    """Obiekt mniejszy niż piksel rysujemy jako kropkę w miejscu jego prostokąta,
    a w jednym pikselu tylko raz – setki budynków w jednym miejscu dałyby i tak tę samą kropkę."""
    p = obiekt["prostokat"]
    x_ekr, y_ekr = teren_na_ekran(p[0], p[1])
    piksel = (int(x_ekr), int(y_ekr))
    if piksel in zajete:
        return
    zajete.add(piksel)
    canvas.create_rectangle(piksel[0], piksel[1], piksel[0] + 2, piksel[1] + 2, fill=kolor, outline="")


def rysuj_obiekt_prosto(obiekt, ust):
    """Wariant podstawowy: punkty jako kropki, linie jako linie, poligony jako wypełnione wielokąty z obrysem."""
    if obiekt["typ"] == "poligon":
        for i in range(len(obiekt["czesci"])):
            pierscienie = obiekt["czesci"][i]
            if ust["wypelnij"] and len(pierscienie) == 1:
                # poligon bez dziur: wypełnienie i obrys jednym wielokątem (najszybciej)
                piksele = lista_pikseli(pierscienie[0])
                if len(piksele) >= 6:
                    canvas.create_polygon(piksele, fill=ust["kolor"], outline=ust["obrys"], width=ust["grubosc"])
                continue
            if ust["wypelnij"]:
                # poligon z dziurami: wypełniamy ścieżkę z mostkami (gml.sciezka_z_dziurami), bez obrysu
                piksele = lista_pikseli(obiekt["sciezki"][i])
                if len(piksele) >= 6:
                    canvas.create_polygon(piksele, fill=ust["kolor"], outline="")
            for pierscien in pierscienie:          # obrysy osobno liniami, żeby nie było widać mostków
                piksele = lista_pikseli(pierscien)
                if len(piksele) >= 4:
                    canvas.create_line(piksele, fill=ust["obrys"], width=ust["grubosc"])
    elif obiekt["typ"] == "linia":
        for wsp in obiekt["czesci"]:
            piksele = lista_pikseli(wsp)
            if len(piksele) >= 4:
                canvas.create_line(piksele, fill=ust["kolor"], width=ust["grubosc"])
    else:
        for x, y in obiekt["czesci"]:
            x_ekr, y_ekr = teren_na_ekran(x, y)
            r = 1 + ust["grubosc"]                 # promień kropki rośnie razem z "grubością" z panelu
            canvas.create_oval(x_ekr - r, y_ekr - r, x_ekr + r, y_ekr + r, fill=ust["kolor"], outline=ust["obrys"])


def rysuj_klase_prosto(klasa, ekran):
    """Rysuje wszystkie widoczne obiekty jednej klasy jej stałym kolorem. Zwraca, ile obiektów narysowała."""
    ust = warstwy[klasa]
    skala = widok["skala"]
    punkty_jako_kropki = skala_mapy() > 50000      # przy małych skalach punkty to tylko kropki
    zajete = set()                     # piksele zajęte już przez małe obiekty tej klasy
    widoczne = wybierz_widoczne(klasa, ekran)
    for obiekt in widoczne:
        p = obiekt["prostokat"]
        if obiekt["typ"] == "punkt":
            if punkty_jako_kropki:
                rysuj_jako_piksel(obiekt, ust["kolor"], zajete)
            else:
                rysuj_obiekt_prosto(obiekt, ust)
        elif (p[2] - p[0]) * skala < 1 and (p[3] - p[1]) * skala < 1:
            rysuj_jako_piksel(obiekt, ust["kolor"], zajete)      # obiekt mniejszy niż piksel
        else:
            rysuj_obiekt_prosto(obiekt, ust)
    return len(widoczne)


def rysuj_prosto(ekran):
    """Wariant podstawowy: każda warstwa jednym kolorem, w kolejności: poligony, obrysy, linie, punkty."""
    narysowane = 0
    for klasa in kolejnosc_klas:
        if warstwy[klasa]["widoczna"]:
            narysowane += rysuj_klase_prosto(klasa, ekran)
    return narysowane


# przelicznik milimetrów mapy na piksele – liczony raz na początku każdego rysowania (rysuj())
przelicznik = {"piksele_na_mm": 1.0}


def mm_na_piksele(mm):
    """Wielkości znaków w znaki.json są w milimetrach mapy w skali 1:10 000. Na ekranie:
    piksele = mm × (pikseli na 1 mm ekranu) × 10 000 / (mianownik skali widoku).
    Przy skali 1:10 000 znak ma więc dokładnie swój rozmiar, a przy przybliżaniu rośnie jak na mapie."""
    return mm * przelicznik["piksele_na_mm"]


def rysuj_wypelnienie(obiekt, w):
    """Warstwa "wypelnienie": kolor środka poligonu i jego kontur."""
    grubosc = mm_na_piksele(w["grubosc_konturu"])
    for i in range(len(obiekt["czesci"])):
        pierscienie = obiekt["czesci"][i]
        if w["kolor"] != "" and len(pierscienie) == 1:
            # poligon bez dziur: wypełnienie i kontur jednym wielokątem (najszybciej)
            piksele = lista_pikseli(pierscienie[0])
            if len(piksele) >= 6:
                canvas.create_polygon(piksele, fill=w["kolor"], outline=w["kontur"], width=grubosc)
            continue
        if w["kolor"] != "":
            # z dziurami: ścieżka z mostkami (gml.sciezka_z_dziurami), tkinter wypełnia regułą parzystości
            piksele = lista_pikseli(obiekt["sciezki"][i])
            if len(piksele) >= 6:
                canvas.create_polygon(piksele, fill=w["kolor"], outline="")
        if w["kontur"] != "":
            for pierscien in pierscienie:          # kontury osobno liniami, żeby nie było widać mostków
                piksele = lista_pikseli(pierscien)
                if len(piksele) >= 4:
                    canvas.create_line(piksele, fill=w["kontur"], width=grubosc)


def rysuj_linie_znaku(obiekt, w):
    """Warstwa "linia": kolor, grubość (stała albo z atrybutu, np. szerokości jezdni), przerywanie
    i przesunięcie w bok (linia równoległa, np. pas wzdłuż granicy gminy). Dla poligonu – po brzegu."""
    if w["kolor"] == "":
        return
    grubosc = mm_na_piksele(wartosc_z_pola(obiekt, w.get("grubosc_z_pola"), w["grubosc"]))
    przesuniecie = mm_na_piksele(wartosc_z_pola(obiekt, w.get("przesuniecie_z_pola"), w["przesuniecie"]))
    kreski = None
    if w["kreski"] is not None:                   # tkinter chce długości kresek w całych pikselach 1–255
        kreski = []
        for dlugosc in w["kreski"]:
            kreski.append(min(255, max(1, round(mm_na_piksele(dlugosc)))))
    for wsp in linie_obiektu(obiekt):
        piksele = lista_pikseli(wsp)
        if len(piksele) < 4:
            continue
        if abs(przesuniecie) >= 0.5:              # przesunięcie mniejsze niż pół piksela i tak nie widać
            piksele = geometria.przesun_lamana(piksele, przesuniecie)
        canvas.create_line(piksele, fill=w["kolor"], width=grubosc, dash=kreski,
                           capstyle=w["koncowki"], joinstyle=w["narozniki"])


def punkt_znaczka(x, y, u, v, cos_k, sin_k):
    """Punkt (u, v) zapisany względem środka znaczka (oś v w dół) -> piksel ekranu po obrocie o kąt
    (cos_k, sin_k): zwykły obrót punktu wokół środka (x, y)."""
    return x + u * cos_k - v * sin_k, y + u * sin_k + v * cos_k


def rysuj_znaczek(x_ekr, y_ekr, kat, z, obiekt):
    """Rysuje znaczek w punkcie ekranu (x_ekr, y_ekr). kat – obrót w radianach (np. kierunek linii),
    do którego dodajemy kąt ze stylu. Kształty: kreska (line), kółko (circle), trójkąt (triangle).
    Symbole SVG dorysujemy w kroku C2 – na razie kółko w ich kolorze."""
    if z["rodzaj"] not in ("znaczek", "znaczek_svg"):
        return
    rozmiar = mm_na_piksele(wartosc_z_pola(obiekt, z.get("rozmiar_z_pola"), z["rozmiar"]))
    if rozmiar < 1:
        return                                    # znaczek mniejszy niż piksel – nie rysujemy
    kat = kat + math.radians(z["kat"])            # w QGIS kąt rośnie zgodnie z ruchem wskazówek zegara
    cos_k = math.cos(kat)
    sin_k = math.sin(kat)
    # przesunięcie znaczka obraca się razem z nim (dzięki temu ząbki są zawsze z tej samej strony linii)
    x, y = punkt_znaczka(x_ekr, y_ekr, mm_na_piksele(z["przesuniecie"][0]), mm_na_piksele(z["przesuniecie"][1]),
                         cos_k, sin_k)
    r = rozmiar / 2
    if z["rodzaj"] == "znaczek_svg":
        canvas.create_oval(x - r / 2, y - r / 2, x + r / 2, y + r / 2, fill=z["kolor"], outline="")
        return
    kontur = z["kontur"]
    grubosc = max(1, mm_na_piksele(z["grubosc_konturu"]))
    if z["ksztalt"] == "line":                    # kreska pionowa w układzie znaczka
        x1, y1 = punkt_znaczka(x, y, 0, -r, cos_k, sin_k)
        x2, y2 = punkt_znaczka(x, y, 0, r, cos_k, sin_k)
        canvas.create_line(x1, y1, x2, y2, fill=kontur or z["kolor"], width=grubosc, capstyle="butt")
    elif z["ksztalt"] == "triangle":              # trójkąt ostrzem do góry w układzie znaczka
        wierzcholki = []
        for u, v in ((0, -r), (-r, r), (r, r)):
            px, py = punkt_znaczka(x, y, u, v, cos_k, sin_k)
            wierzcholki.append(px)
            wierzcholki.append(py)
        canvas.create_polygon(wierzcholki, fill=z["kolor"], outline=kontur, width=grubosc)
    else:                                         # circle i inne – kółko
        canvas.create_oval(x - r, y - r, x + r, y + r, fill=z["kolor"], outline=kontur, width=grubosc)


def kat_na_ekranie(kx, ky):
    """Kierunek (kx, ky) w terenie (oś y w górę) -> kąt na ekranie (oś y w dół), w radianach."""
    return math.atan2(-ky, kx)


def rysuj_znaczki_na_linii(obiekt, w):
    """Warstwa "znaczki_na_linii": znaczek co stały odstęp (np. ząbki na granicy rezerwatu co 40 m)
    albo na początku / końcu / w wierzchołkach linii. Znaczek obraca się zgodnie z kierunkiem linii."""
    odstep_px = mm_na_piksele(w["odstep"])
    if w["rozmieszczenie"] == "co_odstep" and odstep_px < 4:
        return                  # znaczki gęściej niż co 4 piksele zlałyby się w plamę – nie rysujemy
    ekran = widoczny_prostokat()
    z = w["znaczek"]
    for wsp in linie_obiektu(obiekt):
        if len(wsp) < 4:
            continue
        miejsca = []            # (x, y, kx, ky) w terenie
        if w["rozmieszczenie"] == "co_odstep":
            # mm mapy w skali 1:10 000 -> metry w terenie: 1 mm = 10 m
            miejsca = geometria.punkty_co_odstep(wsp, w["odstep"] * 10, w["przesuniecie_wzdluz"] * 10)
        else:
            for i in range(0, len(wsp) - 2, 2):
                if w["rozmieszczenie"] == "na_koncu" and i != len(wsp) - 4:
                    continue
                dl = math.sqrt((wsp[i + 2] - wsp[i]) ** 2 + (wsp[i + 3] - wsp[i + 1]) ** 2)
                if dl == 0:
                    continue
                kx = (wsp[i + 2] - wsp[i]) / dl
                ky = (wsp[i + 3] - wsp[i + 1]) / dl
                if w["rozmieszczenie"] == "na_koncu":
                    miejsca.append((wsp[i + 2], wsp[i + 3], kx, ky))
                else:
                    miejsca.append((wsp[i], wsp[i + 1], kx, ky))
                if w["rozmieszczenie"] == "na_poczatku":
                    break
        for x, y, kx, ky in miejsca:
            if x < ekran[0] or x > ekran[2] or y < ekran[1] or y > ekran[3]:
                continue                          # ten znaczek jest poza okienkiem
            kat = 0.0
            if w["obracaj"]:
                kat = kat_na_ekranie(kx, ky)
            x_ekr, y_ekr = teren_na_ekran(x, y)
            rysuj_znaczek(x_ekr, y_ekr, kat, z, obiekt)


def rysuj_warstwe_znaku(obiekt, w):
    """Rysuje jedną warstwę znaku umownego dla jednego obiektu."""
    rodzaj = w["rodzaj"]
    if rodzaj == "wypelnienie" and obiekt["typ"] == "poligon":
        rysuj_wypelnienie(obiekt, w)
    elif rodzaj == "linia":
        rysuj_linie_znaku(obiekt, w)
    elif rodzaj == "znaczki_na_linii":
        rysuj_znaczki_na_linii(obiekt, w)
    elif rodzaj in ("znaczek", "znaczek_svg") and obiekt["typ"] == "punkt":
        for x, y in obiekt["czesci"]:
            x_ekr, y_ekr = teren_na_ekran(x, y)
            rysuj_znaczek(x_ekr, y_ekr, 0.0, w, obiekt)
    # wzór z punktów (np. drzewka w lesie), kreskowanie i znaczek w środku obszaru – w kroku C3


def kolor_glowny(warstwy_znaku):
    """Najważniejszy kolor znaku – nim rysujemy kropkę, gdy obiekt jest mniejszy niż piksel."""
    for w in warstwy_znaku:
        if w.get("kolor"):
            return w["kolor"]
        if w.get("kontur"):
            return w["kontur"]
        if "znaczek" in w and w["znaczek"].get("kolor"):
            return w["znaczek"]["kolor"]
    return "#000000"


def rysuj_znakami(ekran, skala_teraz):
    """Rysuje mapę znakami umownymi z pliku znaki.json, warstwa po warstwie od spodu do wierzchu.
    Klasy, których wtyczka nie rysuje (np. same napisy), tu też nie są rysowane."""
    skala = widok["skala"]
    punkty_jako_kropki = skala_teraz > 50000
    narysowane = 0
    for warstwa_mapy in znaki["warstwy"]:
        klasa = warstwa_mapy["klasa"]
        if klasa not in dane or not warstwy[klasa]["widoczna"]:
            continue
        if warstwa_mapy["min_skala"] is not None and skala_teraz > warstwa_mapy["min_skala"]:
            continue                              # w tej skali tej warstwy nie pokazujemy (jak QGIS)
        do_rysowania = []                         # pary (obiekt, warstwy jego znaku)
        zajete = set()
        for obiekt in wybierz_widoczne(klasa, ekran):
            if not pasuje_do_filtra(obiekt, warstwa_mapy["filtr"]):
                continue
            znak = znak_obiektu(warstwa_mapy, obiekt)
            if znak is None:
                continue                          # obiekt bez kodu z tej warstwy – nie rysujemy
            p = obiekt["prostokat"]
            maly = (p[2] - p[0]) * skala < 1 and (p[3] - p[1]) * skala < 1
            if (obiekt["typ"] == "punkt" and punkty_jako_kropki) or (obiekt["typ"] != "punkt" and maly):
                rysuj_jako_piksel(obiekt, kolor_glowny(znak["warstwy"]), zajete)
                narysowane += 1
            else:
                do_rysowania.append((obiekt, znak["warstwy"]))
        # Rysujemy "przebiegami" (w QGIS: poziomy symboli): najpierw warstwy z przebiegu 0
        # wszystkich obiektów, potem z przebiegu 1 itd. Dzięki temu brązowe obwódki wszystkich
        # jezdni leżą pod białymi środkami i na skrzyżowaniach drogi ładnie się łączą.
        for przebieg in warstwa_mapy["przebiegi"]:
            for obiekt, warstwy_znaku in do_rysowania:
                for w in warstwy_znaku:
                    if w["przebieg"] == przebieg:
                        rysuj_warstwe_znaku(obiekt, w)
        narysowane += len(do_rysowania)
    return narysowane


def rysuj_nazwy_miejscowosci(ekran, skala_teraz):
    """Nazwy miejscowości (klasa OT_ADMS_P) – tylko w skalach większych niż 1:60 000,
    bo przy całym powiecie 250 napisów zlałoby się w jedną plamę."""
    if "ADMS_P" not in dane or not warstwy["ADMS_P"]["widoczna"] or skala_teraz > 60000:
        return
    for obiekt in wybierz_widoczne("ADMS_P", ekran, licz=False):     # napisów nie liczymy w statystyce
        nazwa = obiekt["atrybuty"].get("nazwa")
        if nazwa:
            x, y = obiekt["czesci"][0]
            x_ekr, y_ekr = teren_na_ekran(x, y)
            canvas.create_text(x_ekr, y_ekr - 10, text=nazwa, font=("Arial", 10, "bold"))


def widoczny_prostokat():
    """Prostokąt terenu, który aktualnie widać w okienku (x_min, y_min, x_max, y_max)."""
    x_min, y_max = ekran_na_teren(0, 0)                    # lewy górny róg okienka
    x_max, y_min = ekran_na_teren(SZEROKOSC, WYSOKOSC)     # prawy dolny róg okienka
    return x_min, y_min, x_max, y_max


def rysuj():
    """Czyści okienko i rysuje mapę: prostymi kolorami albo znakami umownymi (przełącznik u góry).
    W prawym dolnym rogu pokazujemy: ile obiektów sprawdzono i w jakim czasie (tu widać działanie
    indeksu), ile narysowano i ile trwało całe rysowanie."""
    if wczytywanie["trwa"] or len(dane) == 0:
        return
    statystyka["sprawdzone"] = 0
    statystyka["czas_wyboru"] = 0.0
    start = time.time()
    canvas.delete("all")
    ekran = widoczny_prostokat()
    skala_teraz = skala_mapy()
    if znaki is not None:
        przelicznik["piksele_na_mm"] = canvas.winfo_fpixels("1m") * znaki["skala_odniesienia"] / skala_teraz
    if znaki_umowne.get() and znaki is not None:
        narysowane = rysuj_znakami(ekran, skala_teraz)
    else:
        narysowane = rysuj_prosto(ekran)
    rysuj_nazwy_miejscowosci(ekran, skala_teraz)
    rysuj_zaznaczenie()
    czas = time.time() - start
    if uzyj_indeksu.get():
        sposob = "z indeksem"
    else:
        sposob = "bez indeksu"
    tekst = (f"{sposob}: sprawdzono {statystyka['sprawdzone']:,} obiektów ({statystyka['czas_wyboru']:.3f} s),"
             f" narysowano {narysowane:,} obiektów w {czas:.2f} s")
    pasek_rysowania.config(text=tekst.replace(",", " "))


# --- NAWIGACJA ---

def zoom(x_ekr, y_ekr, mnoznik):
    """Przybliża (mnoznik > 1) albo oddala (mnoznik < 1) mapę tak,
    żeby punkt terenu pod kursorem został w tym samym miejscu ekranu."""
    nowa_skala = widok["skala"] * mnoznik
    if nowa_skala < 0.002 or nowa_skala > 50:     # nie pozwalamy oddalić/przybliżyć w nieskończoność
        return
    x, y = ekran_na_teren(x_ekr, y_ekr)           # jaki punkt terenu jest teraz pod kursorem
    widok["skala"] = nowa_skala
    # przesuwamy widok tak, żeby ten sam punkt terenu wypadł znowu pod kursorem
    # (to po prostu wzór teren_na_ekran rozwiązany względem x0 i y0)
    widok["x0"] = x - x_ekr / widok["skala"]
    widok["y0"] = y + y_ekr / widok["skala"]
    rysuj()
    pokaz_status(x_ekr, y_ekr)


def kolko_myszy(event):
    """Kółko myszy: nad mapą przybliża i oddala, nad panelem warstw przewija listę.
    Windows podaje event.delta (+120 / -120), Linux – przyciski 4 i 5."""
    do_gory = event.delta > 0 or event.num == 4
    if event.widget == canvas:
        if do_gory:
            zoom(event.x, event.y, 1.25)
        else:
            zoom(event.x, event.y, 0.8)
    elif str(event.widget).startswith(str(panel)):
        # nazwa widżetu w tkinterze to ścieżka jak w folderach, np. ".!frame2.!canvas.!frame.!checkbutton3";
        # jeśli zaczyna się od nazwy panelu, to myszka jest nad panelem
        if do_gory:
            panel_canvas.yview_scroll(-2, "units")
        else:
            panel_canvas.yview_scroll(2, "units")


# gdzie ostatnio była myszka podczas przeciągania
przeciaganie = {"x": 0, "y": 0, "start_x": 0, "start_y": 0}


def wcisniecie(event):
    przeciaganie["x"] = event.x
    przeciaganie["y"] = event.y
    przeciaganie["start_x"] = event.x             # gdzie przycisk został wciśnięty
    przeciaganie["start_y"] = event.y


def ciagniecie(event):
    dx = event.x - przeciaganie["x"]              # o ile pikseli przesunęła się myszka
    dy = event.y - przeciaganie["y"]
    canvas.move("all", dx, dy)                    # szybko przesuwamy to, co już jest narysowane
    widok["x0"] = widok["x0"] - dx / widok["skala"]   # mapa w prawo = patrzymy bardziej na zachód
    widok["y0"] = widok["y0"] + dy / widok["skala"]   # mapa w dół = patrzymy bardziej na północ
    przeciaganie["x"] = event.x
    przeciaganie["y"] = event.y
    pokaz_status(event.x, event.y)


def puszczenie(event):
    """Puszczenie przycisku: jeśli myszka prawie się nie ruszyła, to było kliknięcie – identyfikujemy obiekt;
    jeśli była przeciągana – rysujemy mapę od nowa, żeby dorysować to, co wjechało na ekran."""
    przesuniecie = abs(event.x - przeciaganie["start_x"]) + abs(event.y - przeciaganie["start_y"])
    if przesuniecie > 0:
        rysuj()
    if przesuniecie < 3:
        identyfikuj(event.x, event.y)


def skala_mapy():
    """Mianownik skali mapy (np. 10000 dla skali 1:10 000).
    Skala mówi, ile metrów w terenie przypada na 1 metr na ekranie."""
    piksele_na_metr_ekranu = canvas.winfo_fpixels("1m") * 1000   # "1m" w tkinterze to 1 milimetr
    return piksele_na_metr_ekranu / widok["skala"]


def pokaz_status(x_ekr, y_ekr):
    """Wypisuje na dole okna współrzędne punktu pod kursorem i skalę mapy."""
    x, y = ekran_na_teren(x_ekr, y_ekr)
    # jak Geoportal i QGIS: najpierw X geodezyjne (północ), potem Y (wschód)
    tekst = f"PUWG 1992:   X = {y:,.1f} m (północ)    Y = {x:,.1f} m (wschód)        skala 1:{skala_mapy():,.0f}"
    pasek.config(text=tekst.replace(",", " "))


def ruch_myszy(event):
    if not wczytywanie["trwa"]:                   # w trakcie wczytywania pasek pokazuje postęp
        pokaz_status(event.x, event.y)


def pokaz_calosc():
    """Powrót do widoku całego powiatu."""
    if zasieg is not None:
        pokaz_prostokat(zasieg)
        rysuj()


def przybliz():
    zoom(SZEROKOSC / 2, WYSOKOSC / 2, 1.5)        # zoom względem środka okna


def oddal():
    zoom(SZEROKOSC / 2, WYSOKOSC / 2, 1 / 1.5)


def zmiana_rozmiaru(event):
    """Okno zmieniło rozmiar (np. po maksymalizacji) – mapa wypełnia teraz całe okno."""
    global SZEROKOSC, WYSOKOSC
    if event.width == SZEROKOSC and event.height == WYSOKOSC:
        return
    SZEROKOSC = event.width
    WYSOKOSC = event.height
    rysuj()


# --- IDENTYFIKACJA OBIEKTU KLIKNIĘCIEM (wariant rozszerzony) ---

zaznaczenie = {"obiekt": None}      # obiekt wskazany ostatnio kliknięciem (podświetlamy go na mapie)
okno_info = {"okno": None, "tekst": None}


def trafiony(obiekt, x, y, tolerancja):
    """Czy kliknięcie w punkcie terenu (x, y) trafia w obiekt.
    punkt   – odległość od punktu nie większa niż tolerancja,
    linia   – odległość od łamanej (od najbliższego odcinka) nie większa niż tolerancja,
    poligon – punkt w wielokącie (metoda półprostej) albo blisko brzegu; dla warstw rysowanych samym
              obrysem (gminy, rezerwaty, kompleksy) tylko blisko brzegu – środek jest przecież pusty."""
    if obiekt["typ"] == "punkt":
        for px, py in obiekt["czesci"]:
            if math.sqrt((px - x) ** 2 + (py - y) ** 2) <= tolerancja:
                return True
        return False
    if obiekt["typ"] == "linia":
        for wsp in obiekt["czesci"]:
            if geometria.odleglosc_od_lamanej(x, y, wsp) <= tolerancja:
                return True
        return False
    for pierscienie in obiekt["czesci"]:
        if warstwy[obiekt["klasa"]]["wypelnij"] and geometria.punkt_w_wielokacie(x, y, pierscienie):
            return True
        for pierscien in pierscienie:
            if geometria.odleglosc_od_lamanej(x, y, pierscien) <= tolerancja:
                return True
    return False


def klasy_od_gory():
    """Klasy w kolejności od tej rysowanej na wierzchu do tej na samym spodzie –
    kliknięcie powinno najpierw trafić w to, co widać na górze (punkty, linie, budynki)."""
    if znaki_umowne.get() and znaki is not None:
        kolejnosc = []
        for warstwa_mapy in znaki["warstwy"]:
            if warstwa_mapy["klasa"] in dane and warstwa_mapy["klasa"] not in kolejnosc:
                kolejnosc.append(warstwa_mapy["klasa"])
    else:
        kolejnosc = list(kolejnosc_klas)
    kolejnosc.reverse()
    return kolejnosc


def identyfikuj(x_ekr, y_ekr):
    """Szuka obiektów pod kursorem i pokazuje ich klasę i atrybuty w osobnym okienku."""
    if wczytywanie["trwa"] or len(dane) == 0:
        return
    start = time.time()
    x, y = ekran_na_teren(x_ekr, y_ekr)
    tolerancja = TOLERANCJA_PIKSELI / widok["skala"]      # tolerancja w pikselach zamieniona na metry
    wokol = (x - tolerancja, y - tolerancja, x + tolerancja, y + tolerancja)
    trafienia = []
    sprawdzone = 0
    for klasa in klasy_od_gory():
        if not warstwy[klasa]["widoczna"]:
            continue                                      # niewidocznej warstwy nie da się kliknąć
        if uzyj_indeksu.get():
            kandydaci = indeks.kandydaci(indeks_przestrzenny[klasa], wokol)
        else:
            kandydaci = dane[klasa]
        sprawdzone += len(kandydaci)
        for obiekt in kandydaci:
            if prostokaty_nachodza(obiekt["prostokat"], wokol) and trafiony(obiekt, x, y, tolerancja):
                trafienia.append(obiekt)
        if len(trafienia) >= 10:
            break
    czas = time.time() - start

    canvas.delete("zaznaczenie")
    if len(trafienia) > 0:
        zaznaczenie["obiekt"] = trafienia[0]
    else:
        zaznaczenie["obiekt"] = None
    rysuj_zaznaczenie()
    pokaz_atrybuty(trafienia, x, y)
    pasek_rysowania.config(text=f"identyfikacja: znaleziono {len(trafienia)} obiektów, sprawdzono "
                                f"{sprawdzone:,} kandydatów w {czas:.3f} s".replace(",", " "))


def rysuj_zaznaczenie():
    """Podświetla wskazany obiekt grubą różową linią (rysujemy ją na wierzchu, z etykietą "zaznaczenie")."""
    obiekt = zaznaczenie["obiekt"]
    if obiekt is None:
        return
    if obiekt["typ"] == "punkt":
        for px, py in obiekt["czesci"]:
            x_ekr, y_ekr = teren_na_ekran(px, py)
            canvas.create_oval(x_ekr - 7, y_ekr - 7, x_ekr + 7, y_ekr + 7, outline=KOLOR_ZAZNACZENIA,
                               width=3, tags="zaznaczenie")
        return
    for wsp in linie_obiektu(obiekt):
        piksele = lista_pikseli(wsp)
        if len(piksele) >= 4:
            canvas.create_line(piksele, fill=KOLOR_ZAZNACZENIA, width=3, tags="zaznaczenie")


def opis_geometrii(obiekt):
    """Krótki opis geometrii: typ, liczba części i punktów."""
    punkty = 0
    if obiekt["typ"] == "punkt":
        punkty = len(obiekt["czesci"])
    else:
        for wsp in linie_obiektu(obiekt):
            punkty += len(wsp) // 2
    return f"{obiekt['typ']}, części: {len(obiekt['czesci'])}, punktów: {punkty}"


def pokaz_atrybuty(trafienia, x, y):
    """Okienko z wynikiem identyfikacji. Najpierw obiekt z wierzchu (podświetlony), pod nim te leżące niżej."""
    if okno_info["okno"] is None or not okno_info["okno"].winfo_exists():
        nowe = tk.Toplevel(okno)
        nowe.title("Identyfikacja obiektu")
        nowe.geometry("430x520")
        tekst = tk.Text(nowe, wrap="word", font=("Arial", 9))
        suwak = tk.Scrollbar(nowe, command=tekst.yview)
        tekst.configure(yscrollcommand=suwak.set)
        suwak.pack(side="right", fill="y")
        tekst.pack(side="left", fill="both", expand=True)
        tekst.tag_configure("naglowek", font=("Arial", 10, "bold"))
        okno_info["okno"] = nowe
        okno_info["tekst"] = tekst
    tekst = okno_info["tekst"]
    tekst.configure(state="normal")
    tekst.delete("1.0", "end")
    tekst.insert("end", f"Punkt: X = {y:,.1f} m, Y = {x:,.1f} m\n\n".replace(",", " "))
    if len(trafienia) == 0:
        tekst.insert("end", "Nie trafiono w żaden obiekt.")
    numer = 0
    for obiekt in trafienia:
        numer += 1
        klasa = obiekt["klasa"]
        tekst.insert("end", f"{numer}. OT_{klasa} – {gml.nazwa_klasy(klasa)}\n", "naglowek")
        tekst.insert("end", f"   geometria: {opis_geometrii(obiekt)}\n")
        for nazwa in obiekt["atrybuty"]:
            tekst.insert("end", f"   {nazwa}: {obiekt['atrybuty'][nazwa]}\n")
        tekst.insert("end", "\n")
    tekst.configure(state="disabled")              # tylko do czytania
    okno_info["okno"].lift()


# --- PANEL WARSTW (wariant rozszerzony) ---

zmienne_warstw = {}         # klasa -> BooleanVar: czy warstwa jest widoczna
zmienne_kategorii = {}      # kategoria -> BooleanVar: włącza/wyłącza wszystkie klasy kategorii
zmienne_grubosci = {}       # klasa -> IntVar: grubość linii
przyciski_kolorow = {}      # klasa -> przycisk pokazujący kolor warstwy


def zmien_widocznosc(klasa):
    warstwy[klasa]["widoczna"] = zmienne_warstw[klasa].get()
    rysuj()


def zmien_kategorie(kategoria):
    """Włącza albo wyłącza wszystkie klasy jednej kategorii naraz."""
    widoczna = zmienne_kategorii[kategoria].get()
    for klasa in warstwy:
        if klasa[:2] == kategoria:
            warstwy[klasa]["widoczna"] = widoczna
            zmienne_warstw[klasa].set(widoczna)
    rysuj()


def zmien_kolor(klasa):
    """Okno wyboru koloru; askcolor zwraca ((r, g, b), "#rrggbb") albo (None, None), gdy anulujemy."""
    wynik = colorchooser.askcolor(color=warstwy[klasa]["kolor"], parent=okno, title="Kolor warstwy " + klasa)
    if wynik[1] is None:
        return
    kolor = wynik[1]
    warstwy[klasa]["kolor"] = kolor
    if warstwy[klasa]["wypelnij"] or klasa.endswith("_P"):
        warstwy[klasa]["obrys"] = ciemniejszy(kolor)
    else:
        warstwy[klasa]["obrys"] = kolor
    przyciski_kolorow[klasa].config(bg=kolor)
    rysuj()


def zmien_grubosc(klasa):
    try:
        grubosc = zmienne_grubosci[klasa].get()
    except tk.TclError:          # w polu jest coś, co nie jest liczbą
        return
    warstwy[klasa]["grubosc"] = max(1, min(grubosc, 10))
    rysuj()


def zbuduj_panel_warstw():
    """Lista warstw po lewej: klasy pogrupowane według kategorii (SW, SK, BU, PT…).
    W każdym wierszu: kolor (kliknięcie otwiera wybór koloru), grubość linii i włącz/wyłącz.
    Kolor i grubość działają w prostych kolorach; przy znakach umownych wygląd bierzemy ze stylów."""
    for element in lista_warstw.winfo_children():          # usuwamy listę poprzedniego powiatu
        element.destroy()
    zmienne_warstw.clear()
    zmienne_kategorii.clear()
    zmienne_grubosci.clear()
    przyciski_kolorow.clear()
    # "lambda k=klasa: ..." zapamiętuje, której klasy dotyczy dany przycisk
    # (bez k=klasa wszystkie przyciski wskazywałyby ostatnią klasę z pętli)
    for kategoria in gml.KATEGORIE:
        klasy = []
        for klasa in sorted(dane):
            if klasa[:2] == kategoria:
                klasy.append(klasa)
        if len(klasy) == 0:
            continue
        zmienne_kategorii[kategoria] = tk.BooleanVar(value=True)
        tk.Checkbutton(lista_warstw, text=f"{kategoria} – {gml.KATEGORIE[kategoria]}", font=("Arial", 9, "bold"),
                       variable=zmienne_kategorii[kategoria],
                       command=lambda k=kategoria: zmien_kategorie(k)).pack(anchor="w", pady=(6, 0))
        for klasa in klasy:
            wiersz = tk.Frame(lista_warstw)
            wiersz.pack(fill="x", padx=(18, 0))
            # kwadracik z kolorem warstwy; kliknięcie (<Button-1>) otwiera okno wyboru koloru
            przycisk = tk.Label(wiersz, width=2, bg=warstwy[klasa]["kolor"], relief="solid", bd=1, cursor="hand2")
            przycisk.bind("<Button-1>", lambda event, k=klasa: zmien_kolor(k))
            przycisk.pack(side="left")
            przyciski_kolorow[klasa] = przycisk
            zmienne_grubosci[klasa] = tk.IntVar(value=warstwy[klasa]["grubosc"])
            pole = tk.Spinbox(wiersz, from_=1, to=10, width=3, textvariable=zmienne_grubosci[klasa],
                              command=lambda k=klasa: zmien_grubosc(k))
            pole.bind("<Return>", lambda event, k=klasa: zmien_grubosc(k))
            pole.pack(side="left", padx=3)
            zmienne_warstw[klasa] = tk.BooleanVar(value=warstwy[klasa]["widoczna"])
            opis = f"{klasa} {gml.nazwa_klasy(klasa)} ({len(dane[klasa]):,})".replace(",", " ")
            tk.Checkbutton(wiersz, text=opis, font=("Arial", 8), variable=zmienne_warstw[klasa],
                           command=lambda k=klasa: zmien_widocznosc(k)).pack(side="left")
    panel_canvas.yview_moveto(0)


def odswiez_przewijanie(event):
    """Lista zmieniła rozmiar – ustawiamy, jak daleko da się ją przewinąć."""
    panel_canvas.configure(scrollregion=panel_canvas.bbox("all"))


# --- WCZYTYWANIE DANYCH (folder albo ZIP) ---

dane = {}               # klasa (np. "BUBD_A") -> lista obiektów
warstwy = {}            # klasa -> ustawienia warstwy (kolor, widoczność...)
kolejnosc_klas = []     # kolejność rysowania prostymi kolorami
zasieg = None           # prostokąt całego powiatu
indeks_przestrzenny = {}            # klasa -> siatka (indeks.py)
wczytywanie = {"trwa": False}
statystyka = {"sprawdzone": 0, "czas_wyboru": 0.0}   # liczone na nowo przy każdym rysowaniu


def pokaz_postep(tekst):
    """Napis o postępie wczytywania w pasku na dole. okno.update() odświeża okno w trakcie długiej pracy."""
    pasek.config(text=tekst)
    okno.update()


def otworz_dane(sciezka):
    """Wczytuje powiat z folderu albo pliku ZIP i pokazuje go w całości."""
    global dane, warstwy, kolejnosc_klas, zasieg, indeks_przestrzenny
    wczytywanie["trwa"] = True
    canvas.delete("all")
    nowe_dane, opis = gml.wczytaj_dane(sciezka, pokaz_postep)
    if len(nowe_dane) == 0:
        wczytywanie["trwa"] = False
        pasek.config(text="Nie znaleziono plików BDOT10k (OT_xxxx_A/L/P.xml) w: " + sciezka)
        return
    # indeks budujemy raz, zaraz po wczytaniu – potem przy każdym rysowaniu tylko z niego korzystamy
    pokaz_postep("Buduję indeks przestrzenny...")
    start = time.time()
    nowy_zasieg = gml.zasieg_danych(nowe_dane)
    indeks_przestrzenny = indeks.zbuduj_indeks(nowe_dane, nowy_zasieg)
    opis = opis + f", indeks zbudowany w {time.time() - start:.1f} s"
    print(indeks.opis_indeksu(indeks_przestrzenny))
    wczytywanie["trwa"] = False
    dane = nowe_dane
    warstwy = {}
    for klasa in dane:
        warstwy[klasa] = ustawienia_domyslne(klasa)
    kolejnosc_klas = sorted(dane, key=miejsce_w_kolejnosci)
    zasieg = nowy_zasieg
    zaznaczenie["obiekt"] = None
    zbuduj_panel_warstw()
    okno.title("BDOT10k – " + os.path.basename(sciezka.rstrip("/\\")))
    print(opis)
    pokaz_calosc()                                # pierwszy widok: cały powiat
    pasek.config(text=opis)


def otworz_folder():
    if wczytywanie["trwa"]:
        return
    sciezka = filedialog.askdirectory(parent=okno, title="Wybierz folder z paczką BDOT10k powiatu",
                                      initialdir=FOLDER_DANYCH)
    if sciezka:
        otworz_dane(sciezka)


def otworz_zip():
    if wczytywanie["trwa"]:
        return
    sciezka = filedialog.askopenfilename(parent=okno, title="Wybierz plik ZIP z paczką BDOT10k powiatu",
                                         initialdir=FOLDER_DANYCH, filetypes=[("Paczka BDOT10k", "*.zip")])
    if sciezka:
        otworz_dane(sciezka)


# --- PROGRAM ---

# znaki umowne z pliku znaki.json (jeśli go nie ma – trzeba raz uruchomić qml_na_json.py)
znaki = wczytaj_plik_znakow()
if znaki is None:
    print("Brak pliku znaki/znaki.json – uruchom qml_na_json.py; na razie działają tylko proste kolory")
else:
    print(f"Znaki umowne: {len(znaki['warstwy'])} warstw z pliku znaki.json")

# okienko: u góry przyciski, w środku mapa, na dole pasek ze współrzędnymi i czasem rysowania
okno = tk.Tk()
okno.title("BDOT10k – przeglądarka")

przyciski = tk.Frame(okno)
przyciski.pack(fill="x")
tk.Button(przyciski, text="Otwórz folder…", command=otworz_folder).pack(side="left", padx=2, pady=2)
tk.Button(przyciski, text="Otwórz ZIP…", command=otworz_zip).pack(side="left", padx=2, pady=2)
tk.Button(przyciski, text="Pokaż całość", command=pokaz_calosc).pack(side="left", padx=(12, 2), pady=2)
tk.Button(przyciski, text="Przybliż +", command=przybliz).pack(side="left", padx=2, pady=2)
tk.Button(przyciski, text="Oddal −", command=oddal).pack(side="left", padx=2, pady=2)
znaki_umowne = tk.BooleanVar(value=False)
przelacznik_znakow = tk.Checkbutton(przyciski, text="Znaki umowne GUGiK", variable=znaki_umowne, command=rysuj)
przelacznik_znakow.pack(side="left", padx=12)
if znaki is None:
    przelacznik_znakow.config(state="disabled")       # bez znaki.json nie ma czego włączać
uzyj_indeksu = tk.BooleanVar(value=True)
tk.Checkbutton(przyciski, text="Indeks przestrzenny", variable=uzyj_indeksu,
               command=rysuj).pack(side="left")

# pasek na dole pakujemy przed mapą, żeby zawsze był widoczny, nawet w małym oknie;
# ma dwa wiersze: współrzędne i skala, a pod nimi statystyka rysowania
dol = tk.Frame(okno)
dol.pack(side="bottom", fill="x")
pasek = tk.Label(dol, text="Wybierz folder z danymi powiatu", anchor="w")
pasek.pack(side="top", fill="x")
pasek_rysowania = tk.Label(dol, text="", anchor="w", fg="#444444")
pasek_rysowania.pack(side="top", fill="x")

# środek okna: po lewej panel warstw, po prawej mapa
srodek = tk.Frame(okno)
srodek.pack(fill="both", expand=True)

# panel warstw: przewijana lista (Canvas z ramką w środku + pasek przewijania)
panel = tk.Frame(srodek)
panel.pack(side="left", fill="y")
tk.Label(panel, text="Warstwy", font=("Arial", 10, "bold")).pack(anchor="w", padx=4)
panel_canvas = tk.Canvas(panel, width=360, highlightthickness=0)
przewijanie = tk.Scrollbar(panel, orient="vertical", command=panel_canvas.yview)
panel_canvas.configure(yscrollcommand=przewijanie.set)
przewijanie.pack(side="right", fill="y")
panel_canvas.pack(side="left", fill="both", expand=True)
lista_warstw = tk.Frame(panel_canvas)
panel_canvas.create_window((0, 0), window=lista_warstw, anchor="nw")
lista_warstw.bind("<Configure>", odswiez_przewijanie)

canvas = tk.Canvas(srodek, width=SZEROKOSC, height=WYSOKOSC, bg="white", highlightthickness=0)
canvas.pack(side="left", fill="both", expand=True)

# podpinamy funkcje pod zdarzenia myszy i zmianę rozmiaru okna;
# kółko podpinamy do całego okna (bind_all), a kolko_myszy sprawdza, czy jesteśmy nad mapą czy nad panelem
okno.bind_all("<MouseWheel>", kolko_myszy)        # kółko na Windowsie
okno.bind_all("<Button-4>", kolko_myszy)          # kółko na Linuksie (do góry)
okno.bind_all("<Button-5>", kolko_myszy)          # kółko na Linuksie (w dół)
canvas.bind("<ButtonPress-1>", wcisniecie)
canvas.bind("<B1-Motion>", ciagniecie)
canvas.bind("<ButtonRelease-1>", puszczenie)
canvas.bind("<Motion>", ruch_myszy)
canvas.bind("<Configure>", zmiana_rozmiaru)

# na start: folder podany przy uruchomieniu (python mapa.py <folder>) albo okno wyboru folderu
if len(sys.argv) > 1:
    okno.after(100, otworz_dane, sys.argv[1])
else:
    okno.after(100, otworz_folder)

# na Windowsie okienko lubi otworzyć się pod VS Code – na chwilę stawiamy je na wierzchu
okno.attributes("-topmost", True)
okno.after(1000, okno.attributes, "-topmost", False)

okno.mainloop()
