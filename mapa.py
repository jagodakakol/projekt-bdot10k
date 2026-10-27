# mapa.py – przeglądarka danych BDOT10k całego powiatu
# Projekt z Geometrii obliczeniowej, dr hab. inż. Waldemar Izdebski
#
# Historia kroków:
# Kroki 1–3: odczyt GML, okienko z mapą (przeliczanie współrzędnych teren -> ekran), nawigacja.
# Kroki 4a–4c: znaki umowne z plików stylu QML wtyczki GUGiK (na razie dla 7 klas), ząbki na granicy rezerwatu.
# Krok A1 (według kryteriów z PDF): cały powiat – wszystkie pliki GML z wybranego folderu albo ZIP
#          (wczytywanie strumieniowe w pliku gml.py), proste kolory warstw, start na całym powiecie,
#          obiekty mniejsze niż piksel jako kropka, okno o zmiennym rozmiarze.

import os
import sys
import math
import time
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import filedialog

import gml          # nasz plik gml.py – wczytywanie danych

# --- USTAWIENIA ---

FOLDER_PROJEKTU = os.path.dirname(os.path.abspath(__file__))
FOLDER_DANYCH = os.path.join(FOLDER_PROJEKTU, "dane")      # tu otwiera się okno wyboru folderu
FOLDER_ZNAKOW = os.path.join(FOLDER_PROJEKTU, "znaki")

# znaki umowne: która klasa jest rysowana którym plikiem stylu z repozytorium GUGiK
# (jezdnie mają dwa pliki: drogi gruntowe [31] i drogi o nawierzchni twardej [33-38])
PLIKI_ZNAKOW = [
    ("PTLZ_A", "OT_PTLZ_A [0].qml"),
    ("SWRS_L", "OT_SWRS_L [12].qml"),
    ("PTWP_A", "OT_PTWP_A [13].qml"),
    ("TCRZ_A", "OT_TCRZ_A [23].qml"),
    ("SKJZ_L", "OT_SKJZ_L [31].qml"),
    ("SKJZ_L", "OT_SKJZ_L [33-38].qml"),
    ("BUBD_A", "OT_BUBD_A [42].qml"),
]

# rozmiar mapy w pikselach (zmienia się razem z rozmiarem okna – patrz zmiana_rozmiaru)
SZEROKOSC = 1000
WYSOKOSC = 650

# nazwy końcówek linii w QGIS -> nazwy w tkinterze
KONCOWKI = {"flat": "butt", "round": "round", "square": "projecting"}

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


# --- ZNAKI UMOWNE (odczyt plików stylu QML z repozytorium GUGiK) ---
# Plik .qml to zwykły XML, więc czytamy go tak samo jak GML – biblioteką ElementTree.
# Najważniejsza część to <renderer-v2 type="categorizedSymbol">: lista kategorii "kod -> numer symbolu"
# i lista symboli. Symbol składa się z warstw (np. brązowa szeroka linia + biała węższa = jezdnia).
# (W kroku C1 te reguły zapiszemy we własnym pliku JSON, jak każe PDF.)

def kolor_qgis(tekst):
    """QGIS zapisuje kolor jako "R,G,B,A", np. "204,100,21,255".
    tkinter chce zapis szesnastkowy "#cc6415" (przezroczystość A pomijamy – tkinter jej nie zna)."""
    czesci = tekst.split(",")
    r = int(czesci[0])
    g = int(czesci[1])
    b = int(czesci[2])
    return f"#{r:02x}{g:02x}{b:02x}"          # :02x = liczba szesnastkowo, zawsze 2 znaki


def ustawienia_warstwy(warstwa):
    """Ustawienia warstwy symbolu są zapisane jako <prop k="nazwa" v="wartość"/>. Zbieramy je w słownik."""
    ustawienia = {}
    for prop in warstwa.findall("prop"):
        ustawienia[prop.get("k")] = prop.get("v")
    return ustawienia


def wzor_grubosci(warstwa, pola):
    """Niektóre grubości nie są stałe, tylko liczone z atrybutu obiektu (w QGIS: "data defined").
    Dla jezdni "w skali" styl GUGiK ma wzór "SZERNAWIE"*0.9 + 2: grubość zależy od szerokości jezdni.
    Obsługujemy tylko taki prosty wzór "POLE"*liczba + liczba. Zwraca (pole, mnożnik, dodatek) albo None."""
    for wlasciwosc in warstwa.iter("Option"):
        if wlasciwosc.get("name") != "outlineWidth":
            continue
        aktywna = False
        wyrazenie = ""
        for opcja in wlasciwosc:
            if opcja.get("name") == "active":
                aktywna = (opcja.get("value") == "true")
            if opcja.get("name") == "expression":
                wyrazenie = opcja.get("value")
        if not aktywna or not wyrazenie.startswith('"'):
            return None          # np. wzór CASE dla rzek – go nie obsługujemy, zostaje stała grubość
        tekst = wyrazenie.replace(" ", "")              # '"SZERNAWIE"*0.9+2'
        czesci = tekst.split("+")                       # ['"SZERNAWIE"*0.9', '2']
        pole, mnoznik = czesci[0].split("*")            # '"SZERNAWIE"', '0.9'
        pole = pole.strip('"')
        dodatek = 0.0
        if len(czesci) > 1:
            dodatek = float(czesci[1])
        return pola.get(pole, pole), float(mnoznik), dodatek    # SZERNAWIE -> szerokoscNawierzchni
    return None


def wczytaj_warstwe_znaku(warstwa, pola):
    """Zamienia jedną warstwę symbolu z pliku QML na prosty słownik.
    Rozumiemy wypełnienie (SimpleFill), linię (SimpleLine) i znaczki wzdłuż linii (MarkerLine)."""
    rodzaj = warstwa.get("class")                       # np. "SimpleFill", "SimpleLine", "MarkerLine"
    u = ustawienia_warstwy(warstwa)
    w = {"rodzaj": rodzaj,
         "przebieg": int(warstwa.get("pass")),          # kolejność rysowania warstw (opis w rysuj_znakami())
         "wlaczona": warstwa.get("enabled") == "1"}
    if rodzaj == "SimpleFill":
        w["wypelnienie"] = ""
        if u.get("style") != "no":
            w["wypelnienie"] = kolor_qgis(u["color"])
        w["kontur"] = ""
        if u.get("outline_style") != "no":
            w["kontur"] = kolor_qgis(u["outline_color"])
        w["grubosc"] = float(u["outline_width"])
        w["jednostka"] = u.get("outline_width_unit")
    elif rodzaj == "SimpleLine":
        w["kolor"] = kolor_qgis(u["line_color"])
        w["grubosc"] = float(u["line_width"])
        w["jednostka"] = u.get("line_width_unit")
        w["koncowki"] = KONCOWKI.get(u.get("capstyle"), "round")
        w["narozniki"] = u.get("joinstyle", "round")    # miter / round / bevel – tak samo w tkinterze
        w["kreski"] = None                              # linia przerywana: długości kresek i przerw
        if u.get("use_custom_dash") == "1":
            w["kreski"] = []
            for liczba in u["customdash"].split(";"):   # "3;4" -> [3.0, 4.0]
                w["kreski"].append(float(liczba))
        w["wzor"] = wzor_grubosci(warstwa, pola)
    elif rodzaj == "MarkerLine":
        # znaczki powtarzane wzdłuż linii, np. ząbki na granicy rezerwatu co 40 m;
        # sam znaczek jest opisany w środku jako osobny mały symbol (zwykle SimpleMarker)
        w["rozmieszczenie"] = u.get("placement")        # "interval" = co stały odstęp
        w["odstep"] = float(u.get("interval", "0"))
        w["jednostka"] = u.get("interval_unit")
        zu = ustawienia_warstwy(warstwa.find("symbol/layer"))
        w["ksztalt"] = zu.get("name")                   # "line" = kreska, którą obracamy w poprzek linii
        w["rozmiar"] = float(zu.get("size", "0"))       # długość kreski (m)
        w["przesuniecie"] = float(zu.get("offset", "0,0").split(",")[1])   # odsunięcie w bok od linii (m)
        w["kolor"] = kolor_qgis(zu.get("outline_color", "0,0,0,255"))
        w["grubosc"] = float(zu.get("outline_width", "0"))
    return w


def wczytaj_znaki(plik):
    """Czyta plik stylu QGIS (.qml) z folderu znaki. Zwraca słownik:
    {"poziom": 42, "pole": "kodKarto10k", "min_skala": ..., "przebiegi": [...], "znaki": {kod: [warstwy]}}"""
    korzen = ET.parse(os.path.join(FOLDER_ZNAKOW, plik)).getroot()      # <qgis>

    # poziom rysowania z nazwy pliku: "OT_BUBD_A [42].qml" -> 42, "OT_SKJZ_L [33-38].qml" -> 33
    poziom = int(plik.split("[")[1].split("]")[0].split("-")[0])

    # Pola wirtualne: style są zrobione też dla plików SHP, gdzie pola mają krótkie nazwy.
    # W pliku jest "tłumaczenie", np. KOD10K = "kodKarto10k", SZERNAWIE = "szerokoscNawierzchni".
    pola = {}
    for pole in korzen.findall("expressionfields/field"):
        pola[pole.get("name")] = pole.get("expression").strip().strip('"')

    renderer = korzen.find("renderer-v2")              # categorizedSymbol = znak zależy od wartości pola
    pole_kodu = pola.get(renderer.get("attr"), renderer.get("attr"))   # KOD10K -> kodKarto10k

    # widoczność zależna od skali, np. drogi gruntowe tylko w skalach większych niż 1:25 000
    min_skala = None
    if korzen.get("hasScaleBasedVisibilityFlag") == "1" and float(korzen.get("minScale")) > 0:
        min_skala = float(korzen.get("minScale"))

    # symbole: numer -> lista warstw
    symbole = {}
    przebiegi = []
    for symbol in renderer.findall("symbols/symbol"):
        warstwy_symbolu = []
        for warstwa in symbol.findall("layer"):
            w = wczytaj_warstwe_znaku(warstwa, pola)
            if w["wlaczona"]:
                warstwy_symbolu.append(w)
                if w["przebieg"] not in przebiegi:
                    przebiegi.append(w["przebieg"])
        symbole[symbol.get("name")] = warstwy_symbolu

    # kategorie: kod znaku umownego -> numer symbolu
    znaki = {}
    for kategoria in renderer.findall("categories/category"):
        if kategoria.get("render") == "true":
            znaki[kategoria.get("value")] = symbole[kategoria.get("symbol")]

    przebiegi.sort()
    return {"plik": plik, "poziom": poziom, "pole": pole_kodu, "min_skala": min_skala,
            "przebiegi": przebiegi, "znaki": znaki}


def poziom_bez_stylu(klasa):
    """Klasy, dla których nie mamy jeszcze stylu w folderze znaki, rysujemy prostym kolorem
    na zastępczym poziomie: obszary na dole, linie w środku, punkty na wierzchu (do kroku C1)."""
    if klasa.endswith("_P"):
        return 60
    if klasa.endswith("_L"):
        return 30
    if klasa[:2] == "BU":
        return 41
    if klasa[:2] in TYLKO_OBRYS:
        return 22
    return -1


def poziom_pozycji(pozycja):
    """Pomocnicza funkcja do sortowania kolejki rysowania według poziomu."""
    return pozycja[0]


def przygotuj_kolejke_znakow():
    """Kolejka rysowania znakami umownymi: (poziom, klasa, styl albo None), od spodu do góry."""
    kolejka = []
    klasy_ze_stylem = []
    for styl in style:
        klasy_ze_stylem.append(styl["klasa"])
        if styl["klasa"] in dane:
            kolejka.append((styl["poziom"], styl["klasa"], styl))
    for klasa in dane:
        if klasa not in klasy_ze_stylem:
            kolejka.append((poziom_bez_stylu(klasa), klasa, None))
    kolejka.sort(key=poziom_pozycji)
    return kolejka


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
            canvas.create_oval(x_ekr - 2, y_ekr - 2, x_ekr + 2, y_ekr + 2, fill=ust["kolor"], outline=ust["obrys"])


def rysuj_klase_prosto(klasa, ekran):
    """Rysuje wszystkie widoczne obiekty jednej klasy jej stałym kolorem. Zwraca, ile obiektów narysowała."""
    ust = warstwy[klasa]
    skala = widok["skala"]
    punkty_jako_kropki = skala_mapy() > 50000      # przy małych skalach punkty to tylko kropki
    zajete = set()                     # piksele zajęte już przez małe obiekty tej klasy
    narysowane = 0
    for obiekt in dane[klasa]:
        p = obiekt["prostokat"]
        if not prostokaty_nachodza(p, ekran):
            continue                   # obiekt poza okienkiem – szkoda czasu
        narysowane += 1
        if obiekt["typ"] == "punkt":
            if punkty_jako_kropki:
                rysuj_jako_piksel(obiekt, ust["kolor"], zajete)
            else:
                rysuj_obiekt_prosto(obiekt, ust)
        elif (p[2] - p[0]) * skala < 1 and (p[3] - p[1]) * skala < 1:
            rysuj_jako_piksel(obiekt, ust["kolor"], zajete)      # obiekt mniejszy niż piksel
        else:
            rysuj_obiekt_prosto(obiekt, ust)
    return narysowane


def rysuj_prosto(ekran):
    """Wariant podstawowy: każda warstwa jednym kolorem, w kolejności: poligony, obrysy, linie, punkty."""
    narysowane = 0
    for klasa in kolejnosc_klas:
        if warstwy[klasa]["widoczna"]:
            narysowane += rysuj_klase_prosto(klasa, ekran)
    return narysowane


def na_piksele(wartosc, jednostka):
    """Grubości w stylach GUGiK są zwykle w jednostkach mapy (MapUnit = metry w terenie),
    więc na ekranie zależą od skali, tak jak na mapie papierowej 1:10 000.
    Rzadziej są w milimetrach ekranu (MM) – wtedy grubość się nie zmienia przy zoomie."""
    if jednostka == "MM":
        return wartosc * canvas.winfo_fpixels("1m")   # "1m" w tkinterze to 1 milimetr
    return wartosc * widok["skala"]


def rysuj_wypelnienie(obiekt, w):
    """Warstwa SimpleFill: wypełnienie poligonu i jego kontur."""
    if w["wypelnienie"] != "":
        # Wypełnienie z dziurami: tkinter nie zna dziur, więc rysujemy jedną ścieżkę z "mostkami"
        # (patrz gml.sciezka_z_dziurami). Tkinter wypełnia według reguły parzystości: punkt jest w środku,
        # jeśli linia poprowadzona od niego w bok przecina brzeg nieparzystą liczbę razy.
        # Z wnętrza dziury przecina parzyście, więc dziura zostaje pusta, a każdy mostek
        # przechodzimy dwa razy (tam i z powrotem), więc się znosi.
        for sciezka in obiekt["sciezki"]:
            piksele = lista_pikseli(sciezka)
            if len(piksele) >= 6:                 # poligon potrzebuje co najmniej 3 punktów
                canvas.create_polygon(piksele, fill=w["wypelnienie"], outline="")
    if w["kontur"] != "":
        # kontury rysujemy osobno liniami, żeby nie było widać mostków
        grubosc = na_piksele(w["grubosc"], w["jednostka"])
        for pierscien in linie_obiektu(obiekt):
            piksele = lista_pikseli(pierscien)
            if len(piksele) >= 4:                 # linia potrzebuje co najmniej 2 punktów
                canvas.create_line(piksele, fill=w["kontur"], width=grubosc)


def rysuj_linie_znaku(obiekt, w):
    """Warstwa SimpleLine: linia o kolorze i grubości ze stylu. Dla poligonu (np. rezerwat)
    rysujemy ją po brzegu."""
    grubosc = w["grubosc"]
    if w["wzor"] is not None:                     # grubość liczona z atrybutu, np. szerokości jezdni
        pole, mnoznik, dodatek = w["wzor"]
        tekst = obiekt["atrybuty"].get(pole)      # np. "6.0" (metry)
        if tekst:
            grubosc = float(tekst) * mnoznik + dodatek
    grubosc = na_piksele(grubosc, w["jednostka"])

    kreski = None
    if w["kreski"] is not None:                   # tkinter chce długości kresek w całych pikselach
        kreski = []
        for dlugosc in w["kreski"]:
            kreski.append(max(1, round(na_piksele(dlugosc, w["jednostka"]))))

    for wsp in linie_obiektu(obiekt):
        piksele = lista_pikseli(wsp)
        if len(piksele) >= 4:
            canvas.create_line(piksele, fill=w["kolor"], width=grubosc, dash=kreski,
                               capstyle=w["koncowki"], joinstyle=w["narozniki"])


def punkty_co_odstep(wsp, odstep):
    """Wyznacza punkty co `odstep` metrów wzdłuż łamanej [x1, y1, x2, y2, ...] – w nich stawiamy znaczki.
    Zwraca listę (x, y, kx, ky): punkt i kierunek odcinka, na którym leży (wektor o długości 1)."""
    wynik = []
    pozycja = 0.0             # odległość następnego znaczka od początku bieżącego odcinka
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


def rysuj_zabki(obiekt, w):
    """Warstwa MarkerLine z kreską: krótkie kreski prostopadłe do linii co stały odstęp,
    odsunięte w bok od linii – tak wyglądają ząbki na granicy rezerwatu."""
    odstep_px = na_piksele(w["odstep"], w["jednostka"])
    if odstep_px < 4:
        return      # ząbki byłyby gęściej niż co 4 piksele i zlałyby się w plamę, więc ich nie rysujemy
    grubosc = na_piksele(w["grubosc"], w["jednostka"])
    od = w["przesuniecie"] - w["rozmiar"] / 2        # kreska zaczyna się tyle metrów od linii...
    do = w["przesuniecie"] + w["rozmiar"] / 2        # ...a kończy tyle (u nas od 1 m do 6 m)
    ekran = widoczny_prostokat()
    for wsp in linie_obiektu(obiekt):
        for x, y, kx, ky in punkty_co_odstep(wsp, w["odstep"]):
            if x < ekran[0] or x > ekran[2] or y < ekran[1] or y > ekran[3]:
                continue                                # ten ząbek jest poza okienkiem
            # wektor prostopadły "w prawo" od kierunku linii to (ky, -kx);
            # obwody poligonów w BDOT10k biegną zgodnie z ruchem wskazówek zegara,
            # więc "w prawo" oznacza do środka rezerwatu
            x1, y1 = teren_na_ekran(x + ky * od, y - kx * od)
            x2, y2 = teren_na_ekran(x + ky * do, y - kx * do)
            canvas.create_line(x1, y1, x2, y2, fill=w["kolor"], width=grubosc, capstyle="butt")


def rysuj_warstwe_znaku(obiekt, w):
    """Rysuje jedną warstwę znaku umownego dla jednego obiektu."""
    if w["rodzaj"] == "SimpleFill" and obiekt["typ"] == "poligon":
        rysuj_wypelnienie(obiekt, w)
    elif w["rodzaj"] == "SimpleLine":
        rysuj_linie_znaku(obiekt, w)
    elif w["rodzaj"] == "MarkerLine" and w["rozmieszczenie"] == "interval" and w["ksztalt"] == "line":
        rysuj_zabki(obiekt, w)
    # wzór z drzewek w lesie i znaki punktowe z plików SVG dorobimy w krokach C2–C3


def kolor_glowny(warstwy_znaku):
    """Najważniejszy kolor znaku (pierwsze wypełnienie albo linia) – nim rysujemy kropkę,
    gdy obiekt jest mniejszy niż piksel."""
    for w in warstwy_znaku:
        for nazwa in ("wypelnienie", "kolor", "kontur"):
            if w.get(nazwa):
                return w[nazwa]
    return "#000000"


def rysuj_znakami(ekran, skala_teraz):
    """Rysuje mapę znakami umownymi, styl po stylu od najniższego poziomu.
    Klasy bez stylu w folderze znaki rysujemy na razie prostymi kolorami."""
    skala = widok["skala"]
    narysowane = 0
    for poziom, klasa, styl in kolejka_znakow:
        if not warstwy[klasa]["widoczna"]:
            continue
        if styl is None:
            narysowane += rysuj_klase_prosto(klasa, ekran)
            continue
        if styl["min_skala"] is not None and skala_teraz > styl["min_skala"]:
            continue                              # w tej skali tej warstwy nie pokazujemy (jak QGIS)
        # wybieramy obiekty: widoczne w okienku i z kodem, który jest w tym stylu
        do_rysowania = []
        zajete = set()
        for obiekt in dane[klasa]:
            kod = obiekt["atrybuty"].get(styl["pole"])
            if kod not in styl["znaki"]:
                continue
            p = obiekt["prostokat"]
            if not prostokaty_nachodza(p, ekran):
                continue
            if obiekt["typ"] != "punkt" and (p[2] - p[0]) * skala < 1 and (p[3] - p[1]) * skala < 1:
                rysuj_jako_piksel(obiekt, kolor_glowny(styl["znaki"][kod]), zajete)
                narysowane += 1
            else:
                do_rysowania.append(obiekt)
        # Rysujemy "przebiegami" (w QGIS: poziomy symboli): najpierw warstwy z przebiegu 0
        # wszystkich obiektów, potem z przebiegu 1 itd. Dzięki temu brązowe obwódki wszystkich
        # jezdni leżą pod białymi środkami i na skrzyżowaniach drogi ładnie się łączą.
        for przebieg in styl["przebiegi"]:
            for obiekt in do_rysowania:
                for w in styl["znaki"][obiekt["atrybuty"].get(styl["pole"])]:
                    if w["przebieg"] == przebieg:
                        rysuj_warstwe_znaku(obiekt, w)
        narysowane += len(do_rysowania)
    return narysowane


def rysuj_nazwy_miejscowosci(ekran, skala_teraz):
    """Nazwy miejscowości (klasa OT_ADMS_P) – tylko w skalach większych niż 1:60 000,
    bo przy całym powiecie 250 napisów zlałoby się w jedną plamę."""
    if "ADMS_P" not in dane or not warstwy["ADMS_P"]["widoczna"] or skala_teraz > 60000:
        return
    for obiekt in dane["ADMS_P"]:
        nazwa = obiekt["atrybuty"].get("nazwa")
        if nazwa and prostokaty_nachodza(obiekt["prostokat"], ekran):
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
    Czas rysowania i liczbę obiektów pokazujemy w prawym dolnym rogu okna."""
    if wczytywanie["trwa"] or len(dane) == 0:
        return
    start = time.time()
    canvas.delete("all")
    ekran = widoczny_prostokat()
    skala_teraz = skala_mapy()
    if znaki_umowne.get():
        narysowane = rysuj_znakami(ekran, skala_teraz)
    else:
        narysowane = rysuj_prosto(ekran)
    rysuj_nazwy_miejscowosci(ekran, skala_teraz)
    czas = time.time() - start
    pasek_rysowania.config(text=f"narysowano {narysowane:,} obiektów w {czas:.2f} s".replace(",", " "))


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
    # Windows podaje event.delta (+120 / -120), Linux – przyciski 4 i 5
    if event.delta > 0 or event.num == 4:
        zoom(event.x, event.y, 1.25)
    else:
        zoom(event.x, event.y, 0.8)


# gdzie ostatnio była myszka podczas przeciągania
przeciaganie = {"x": 0, "y": 0}


def wcisniecie(event):
    przeciaganie["x"] = event.x
    przeciaganie["y"] = event.y


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
    rysuj()     # po puszczeniu rysujemy od nowa, żeby dorysować to, co wjechało na ekran


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


# --- WCZYTYWANIE DANYCH (folder albo ZIP) ---

dane = {}               # klasa (np. "BUBD_A") -> lista obiektów
warstwy = {}            # klasa -> ustawienia warstwy (kolor, widoczność...)
kolejnosc_klas = []     # kolejność rysowania prostymi kolorami
kolejka_znakow = []     # kolejność rysowania znakami umownymi
zasieg = None           # prostokąt całego powiatu
wczytywanie = {"trwa": False}


def pokaz_postep(tekst):
    """Napis o postępie wczytywania w pasku na dole. okno.update() odświeża okno w trakcie długiej pracy."""
    pasek.config(text=tekst)
    okno.update()


def otworz_dane(sciezka):
    """Wczytuje powiat z folderu albo pliku ZIP i pokazuje go w całości."""
    global dane, warstwy, kolejnosc_klas, kolejka_znakow, zasieg
    wczytywanie["trwa"] = True
    canvas.delete("all")
    nowe_dane, opis = gml.wczytaj_dane(sciezka, pokaz_postep)
    wczytywanie["trwa"] = False
    if len(nowe_dane) == 0:
        pasek.config(text="Nie znaleziono plików BDOT10k (OT_xxxx_A/L/P.xml) w: " + sciezka)
        return
    dane = nowe_dane
    warstwy = {}
    for klasa in dane:
        warstwy[klasa] = ustawienia_domyslne(klasa)
    kolejnosc_klas = sorted(dane, key=miejsce_w_kolejnosci)
    kolejka_znakow = przygotuj_kolejke_znakow()
    zasieg = gml.zasieg_danych(dane)
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

# znaki umowne: czytamy style (na razie 7 plików z folderu znaki)
style = []
for klasa_stylu, plik_stylu in PLIKI_ZNAKOW:
    styl_klasy = wczytaj_znaki(plik_stylu)
    styl_klasy["klasa"] = klasa_stylu
    style.append(styl_klasy)

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
tk.Checkbutton(przyciski, text="Znaki umowne GUGiK", variable=znaki_umowne,
               command=rysuj).pack(side="left", padx=12)

# pasek na dole pakujemy przed mapą, żeby zawsze był widoczny, nawet w małym oknie
dol = tk.Frame(okno)
dol.pack(side="bottom", fill="x")
pasek = tk.Label(dol, text="Wybierz folder z danymi powiatu", anchor="w")
pasek.pack(side="left", fill="x", expand=True)
pasek_rysowania = tk.Label(dol, text="", anchor="e")
pasek_rysowania.pack(side="right", padx=6)

canvas = tk.Canvas(okno, width=SZEROKOSC, height=WYSOKOSC, bg="white", highlightthickness=0)
canvas.pack(fill="both", expand=True)

# podpinamy funkcje pod zdarzenia myszy i zmianę rozmiaru okna
canvas.bind("<MouseWheel>", kolko_myszy)          # kółko na Windowsie
canvas.bind("<Button-4>", kolko_myszy)            # kółko na Linuksie (do góry)
canvas.bind("<Button-5>", kolko_myszy)            # kółko na Linuksie (w dół)
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
