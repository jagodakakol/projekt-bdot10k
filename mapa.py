# mapa.py – przeglądarka danych BDOT10k (Wola Karczewska)
# Projekt z Geometrii obliczeniowej, dr hab. inż. Waldemar Izdebski
#
# Krok 1: wczytanie plików GML z folderu dane_wies.
# Krok 2: okienko i rysowanie mapy (przeliczanie współrzędnych teren -> ekran).
# Krok 3: nawigacja – zoom kółkiem, przesuwanie myszą, przyciski i pasek ze współrzędnymi.
# Krok 4a: drogi rysujemy z jezdni (OT_SKJZ_L), a nie z dróg (OT_SKDR_L), bo to jezdniom
#          BDOT10k przypisuje kody znaków umownych (kodKarto10k) – tak robi też wtyczka GUGiK.
# Krok 4b: znaki umowne z plików stylu QGIS (.qml) z repozytorium GUGiK (folder znaki):
#          kod obiektu -> znak umowny, warstwy w kolejności poziomów, usuwanie nieaktualnych wersji obiektów.
# Krok 4c: ząbki na granicy rezerwatu – znaczki stawiane co 40 m wzdłuż linii.

import os
import math
import xml.etree.ElementTree as ET
import tkinter as tk
import time

# --- USTAWIENIA ---

# folder projektu, folder z wyciętymi danymi (zrobionymi przez wytnij_wies.py) i folder ze znakami umownymi
FOLDER_PROJEKTU = os.path.dirname(os.path.abspath(__file__))
FOLDER_DANYCH = os.path.join(FOLDER_PROJEKTU, "dane_wies")
FOLDER_ZNAKOW = os.path.join(FOLDER_PROJEKTU, "znaki")

# przestrzenie nazw z nagłówka plików GML – to one stoją za przedrostkami "gml:" i "ot:"
NS = {
    "gml": "http://www.opengis.net/gml/3.2",
    "ot": "urn:gugik:specyfikacje:gmlas:bazaDanychObiektowTopograficznych10k:2.0",
}

# klasy, które wczytujemy (kolejność rysowania ustalają teraz poziomy ze stylów – patrz niżej)
KLASY = ["PTLZ_A", "PTWP_A", "TCRZ_A", "BUBD_A", "SKJZ_L", "SWRS_L", "ADMS_P"]

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

# rozmiar okienka z mapą (w pikselach)
SZEROKOSC = 1000
WYSOKOSC = 650

# prostokąt wsi (x_min, y_min, x_max, y_max) – ten obszar pokazujemy na starcie
WIES = (662400, 475400, 664900, 476900)

# nazwy końcówek linii w QGIS -> nazwy w tkinterze
KONCOWKI = {"flat": "butt", "round": "round", "square": "projecting"}


# --- WCZYTYWANIE DANYCH ---

def tekst_na_punkty(tekst):
    """Zamienia napis "x1 y1 x2 y2 ..." na listę punktów [(x1, y1), (x2, y2), ...]."""
    liczby = tekst.split()
    punkty = []
    for i in range(0, len(liczby) - 1, 2):
        punkty.append((float(liczby[i]), float(liczby[i + 1])))
    return punkty


def wczytaj_geometrie(element):
    """Sprawdza, jaka geometria siedzi w znaczniku <ot:geometria>, i zwraca (typ, współrzędne).
    punkt   -> (x, y)
    linia   -> [(x, y), (x, y), ...]
    poligon -> [obwód, dziura1, dziura2, ...], a każdy z nich to lista punktów"""
    punkt = element.find("gml:Point", NS)
    if punkt is not None:
        tekst = punkt.find("gml:pos", NS).text
        return "punkt", tekst_na_punkty(tekst)[0]

    linia = element.find("gml:Curve", NS)
    if linia is not None:
        punkty = []
        # linia może mieć kilka odcinków (LineStringSegment) – sklejamy je po kolei
        for poslist in linia.findall(".//gml:posList", NS):
            punkty = punkty + tekst_na_punkty(poslist.text)
        return "linia", punkty

    poligon = element.find("gml:Polygon", NS)
    if poligon is not None:
        pierscienie = []
        obwod = poligon.find("gml:exterior//gml:posList", NS)
        pierscienie.append(tekst_na_punkty(obwod.text))
        for dziura in poligon.findall("gml:interior//gml:posList", NS):
            pierscienie.append(tekst_na_punkty(dziura.text))
        return "poligon", pierscienie

    return None, None   # inna geometria – na razie jej nie obsługujemy


def wczytaj_klase(klasa):
    """Czyta jeden plik GML i zwraca listę obiektów. Każdy obiekt to słownik:
    {"klasa": ..., "typ": ..., "geometria": ..., "atrybuty": {...}}"""
    sciezka = os.path.join(FOLDER_DANYCH, "OT_" + klasa + ".xml")
    korzen = ET.parse(sciezka).getroot()          # <gml:FeatureCollection>
    obiekty = []
    usuniete = 0
    for pudelko in korzen.findall("gml:featureMember", NS):
        element = pudelko[0]                      # np. <ot:OT_BUBD_A>
        atrybuty = {}
        typ = None
        geometria = None
        for dziecko in element:
            nazwa = dziecko.tag.split("}")[1]     # "{urn:...}nazwa" -> "nazwa"
            if nazwa == "geometria":
                typ, geometria = wczytaj_geometrie(dziecko)
            else:
                atrybuty[nazwa] = dziecko.text
        # "Usuwamy dane" nieaktualne: BDOT10k przechowuje też stare wersje obiektów – mają wpisaną
        # datę koniecWersjiObiektu. Wtyczka GUGiK pokazuje tylko obiekty aktualne, więc my też.
        if atrybuty.get("koniecWersjiObiektu"):
            usuniete += 1
            continue
        obiekt = {"klasa": klasa, "typ": typ, "geometria": geometria, "atrybuty": atrybuty}
        # prostokąt otaczający liczymy raz, przy wczytywaniu – przyda się przy rysowaniu
        obiekt["prostokat"] = prostokat_otaczajacy(wszystkie_punkty(obiekt))
        if typ == "poligon":
            obiekt["sciezka"] = sciezka_z_dziurami(geometria)   # też liczymy raz, przy wczytywaniu
        obiekty.append(obiekt)
    print(f"{klasa}: {len(obiekty)} obiektów (usunięte nieaktualne wersje: {usuniete})")
    return obiekty


def wszystkie_punkty(obiekt):
    """Zwraca płaską listę wszystkich punktów obiektu (przyda się do liczenia zasięgu)."""
    if obiekt["typ"] == "punkt":
        return [obiekt["geometria"]]
    if obiekt["typ"] == "linia":
        return obiekt["geometria"]
    if obiekt["typ"] == "poligon":
        return obiekt["geometria"][0]             # do zasięgu wystarczy obwód
    return []


def sciezka_z_dziurami(pierscienie):
    """Łączy obwód poligonu i jego dziury w jedną ścieżkę do wypełnienia (sztuczka z "mostkami").
    Każdą dziurę doczepiamy do NAJBLIŻSZEGO wierzchołka obwodu, żeby mostki były jak najkrótsze:
    idziemy po obwodzie, w tym wierzchołku skaczemy do dziury, obchodzimy ją i wracamy."""
    obwod = pierscienie[0]
    doczepione = {}          # numer wierzchołka obwodu -> lista dziur doczepionych w tym miejscu
    for dziura in pierscienie[1:]:
        dx, dy = dziura[0]                        # pierwszy punkt dziury
        najblizszy = 0
        najmniejsza = None
        for i in range(len(obwod)):
            x, y = obwod[i]
            odleglosc = (x - dx) ** 2 + (y - dy) ** 2   # kwadrat odległości – do porównań wystarczy
            if najmniejsza is None or odleglosc < najmniejsza:
                najmniejsza = odleglosc
                najblizszy = i
        if najblizszy not in doczepione:
            doczepione[najblizszy] = []
        doczepione[najblizszy].append(dziura)
    sciezka = []
    for i in range(len(obwod)):
        sciezka.append(obwod[i])
        if i in doczepione:
            for dziura in doczepione[i]:
                sciezka = sciezka + list(dziura) + [obwod[i]]   # tam (mostek), dookoła dziury, z powrotem
    return sciezka


def prostokat_otaczajacy(punkty):
    """Zwraca (x_min, y_min, x_max, y_max), czyli najmniejszy prostokąt,
    w którym mieszczą się wszystkie punkty (ta sama funkcja co w wytnij_wies.py)."""
    xs = [p[0] for p in punkty]
    ys = [p[1] for p in punkty]
    return min(xs), min(ys), max(xs), max(ys)


def prostokaty_nachodza(a, b):
    """Sprawdza, czy dwa prostokąty mają część wspólną (ta sama funkcja co w wytnij_wies.py)."""
    if a[2] < b[0] or a[0] > b[2]:   # a całkiem na lewo albo na prawo od b
        return False
    if a[3] < b[1] or a[1] > b[3]:   # a całkiem pod albo nad b
        return False
    return True


def zasieg(obiekty):
    """Zasięg danych: najmniejszy prostokąt (x_min, y_min, x_max, y_max), w którym mieszczą się wszystkie obiekty."""
    xs = []
    ys = []
    for obiekt in obiekty:
        for x, y in wszystkie_punkty(obiekt):
            xs.append(x)
            ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


# --- ZNAKI UMOWNE (odczyt plików stylu QML z repozytorium GUGiK) ---
# Plik .qml to zwykły XML, więc czytamy go tak samo jak GML – biblioteką ElementTree.
# Najważniejsza część to <renderer-v2 type="categorizedSymbol">: lista kategorii "kod -> numer symbolu"
# i lista symboli. Symbol składa się z warstw (np. brązowa szeroka linia + biała węższa = jezdnia).

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
    Na razie rozumiemy wypełnienie (SimpleFill) i linię (SimpleLine); resztę zapamiętujemy tylko z nazwy."""
    rodzaj = warstwa.get("class")                       # np. "SimpleFill", "SimpleLine", "MarkerLine"
    u = ustawienia_warstwy(warstwa)
    w = {"rodzaj": rodzaj,
         "przebieg": int(warstwa.get("pass")),          # kolejność rysowania warstw (opis w rysuj())
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
        warstwy = []
        for warstwa in symbol.findall("layer"):
            w = wczytaj_warstwe_znaku(warstwa, pola)
            if w["wlaczona"]:
                warstwy.append(w)
                if w["przebieg"] not in przebiegi:
                    przebiegi.append(w["przebieg"])
        symbole[symbol.get("name")] = warstwy

    # kategorie: kod znaku umownego -> numer symbolu
    znaki = {}
    for kategoria in renderer.findall("categories/category"):
        if kategoria.get("render") == "true":
            znaki[kategoria.get("value")] = symbole[kategoria.get("symbol")]

    przebiegi.sort()
    return {"plik": plik, "poziom": poziom, "pole": pole_kodu, "min_skala": min_skala,
            "przebiegi": przebiegi, "znaki": znaki}


def poziom_stylu(styl):
    """Pomocnicza funkcja do sortowania stylów według poziomu rysowania."""
    return styl["poziom"]


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
    """Ustawia widok tak, żeby podany prostokąt (x_min, y_min, x_max, y_max) zmieścił się w okienku."""
    x_min, y_min, x_max, y_max = prostokat
    skala_x = SZEROKOSC / (x_max - x_min)
    skala_y = WYSOKOSC / (y_max - y_min)
    widok["skala"] = min(skala_x, skala_y)        # mniejsza skala, żeby zmieściło się w obu kierunkach
    # środek prostokąta ma wypaść na środku okienka
    srodek_x = (x_min + x_max) / 2
    srodek_y = (y_min + y_max) / 2
    widok["x0"] = srodek_x - (SZEROKOSC / 2) / widok["skala"]
    widok["y0"] = srodek_y + (WYSOKOSC / 2) / widok["skala"]


# --- RYSOWANIE ---

def lista_pikseli(punkty):
    """Zamienia listę punktów terenowych na płaską listę pikseli [x1, y1, x2, y2, ...] dla tkintera.
    Prosta generalizacja: pomija punkty, które na ekranie wypadłyby bliżej niż 1 piksel
    od poprzedniego (i tak nie byłoby ich widać, a rysowanie idzie dużo szybciej).
    Ostatni punkt zostawiamy zawsze, żeby pierścienie poligonów były domknięte."""
    wynik = []
    ostatni_x = None
    ostatni_y = None
    for i in range(len(punkty)):
        x, y = punkty[i]
        x_ekr, y_ekr = teren_na_ekran(x, y)
        czy_ostatni = (i == len(punkty) - 1)
        if ostatni_x is None or czy_ostatni or abs(x_ekr - ostatni_x) >= 1 or abs(y_ekr - ostatni_y) >= 1:
            wynik.append(x_ekr)
            wynik.append(y_ekr)
            ostatni_x = x_ekr
            ostatni_y = y_ekr
    return wynik


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
        # (patrz sciezka_z_dziurami). Tkinter wypełnia według reguły parzystości: punkt jest w środku,
        # jeśli linia poprowadzona od niego w bok przecina brzeg nieparzystą liczbę razy.
        # Z wnętrza dziury przecina parzyście, więc dziura zostaje pusta, a każdy mostek
        # przechodzimy dwa razy (tam i z powrotem), więc się znosi.
        piksele = lista_pikseli(obiekt["sciezka"])
        if len(piksele) >= 6:                     # poligon potrzebuje co najmniej 3 punktów
            canvas.create_polygon(piksele, fill=w["wypelnienie"], outline="")
    if w["kontur"] != "":
        # kontury rysujemy osobno liniami, żeby nie było widać mostków
        grubosc = na_piksele(w["grubosc"], w["jednostka"])
        for pierscien in obiekt["geometria"]:
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

    if obiekt["typ"] == "linia":
        linie = [obiekt["geometria"]]
    elif obiekt["typ"] == "poligon":
        linie = obiekt["geometria"]               # obwód i dziury
    else:
        return
    for punkty in linie:
        piksele = lista_pikseli(punkty)
        if len(piksele) >= 4:
            canvas.create_line(piksele, fill=w["kolor"], width=grubosc, dash=kreski,
                               capstyle=w["koncowki"], joinstyle=w["narozniki"])


def punkty_co_odstep(punkty, odstep):
    """Wyznacza punkty co `odstep` metrów wzdłuż łamanej – w nich stawiamy znaczki.
    Zwraca listę (x, y, kx, ky): punkt i kierunek odcinka, na którym leży (wektor o długości 1)."""
    wynik = []
    pozycja = 0.0             # odległość następnego znaczka od początku bieżącego odcinka
    for i in range(len(punkty) - 1):
        x1, y1 = punkty[i]
        x2, y2 = punkty[i + 1]
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
    if obiekt["typ"] == "linia":
        linie = [obiekt["geometria"]]
    elif obiekt["typ"] == "poligon":
        linie = obiekt["geometria"]
    else:
        return
    for punkty in linie:
        for x, y, kx, ky in punkty_co_odstep(punkty, w["odstep"]):
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
    # wzór z drzewek w lesie i znaki punktowe z plików SVG dorobimy w następnym kroku


def rysuj_miejscowosc(obiekt):
    """Miejscowości nie mają znaku w folderze znaki (we wtyczce to tylko napis).
    Na razie kropka z nazwą – prawdziwe napisy zrobimy w kroku 4d."""
    x, y = obiekt["geometria"]
    x_ekr, y_ekr = teren_na_ekran(x, y)
    canvas.create_oval(x_ekr - 4, y_ekr - 4, x_ekr + 4, y_ekr + 4, fill="black")
    nazwa = obiekt["atrybuty"].get("nazwa")
    if nazwa:
        canvas.create_text(x_ekr, y_ekr - 12, text=nazwa, font=("Arial", 11, "bold"))


def widoczny_prostokat():
    """Prostokąt terenu, który aktualnie widać w okienku (x_min, y_min, x_max, y_max)."""
    x_min, y_max = ekran_na_teren(0, 0)                    # lewy górny róg okienka
    x_max, y_min = ekran_na_teren(SZEROKOSC, WYSOKOSC)     # prawy dolny róg okienka
    return x_min, y_min, x_max, y_max


def rysuj():
    """Czyści okienko i rysuje mapę znakami umownymi, styl po stylu od najniższego poziomu.
    Rysujemy tylko obiekty widoczne w okienku i tylko te, którym styl przypisuje znak."""
    start = time.time()
    canvas.delete("all")
    ekran = widoczny_prostokat()
    skala_teraz = skala_mapy()
    narysowane = 0
    for styl in style:                            # posortowane według poziomu (od spodu do góry)
        if styl["min_skala"] is not None and skala_teraz > styl["min_skala"]:
            continue                              # w tej skali tej warstwy nie pokazujemy (jak QGIS)
        # wybieramy obiekty: widoczne w okienku i z kodem, który jest w tym stylu
        do_rysowania = []
        for obiekt in dane[styl["klasa"]]:
            kod = obiekt["atrybuty"].get(styl["pole"])
            if kod in styl["znaki"] and prostokaty_nachodza(obiekt["prostokat"], ekran):
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
    for obiekt in dane["ADMS_P"]:                 # miejscowości na samym wierzchu
        rysuj_miejscowosc(obiekt)
    print(f"Narysowano {narysowane} obiektów w {time.time() - start:.2f} s (skala 1:{skala_teraz:,.0f})".replace(",", " "))


# --- NAWIGACJA ---

def zoom(x_ekr, y_ekr, mnoznik):
    """Przybliża (mnoznik > 1) albo oddala (mnoznik < 1) mapę tak,
    żeby punkt terenu pod kursorem został w tym samym miejscu ekranu."""
    nowa_skala = widok["skala"] * mnoznik
    if nowa_skala < 0.02 or nowa_skala > 50:      # nie pozwalamy oddalić/przybliżyć w nieskończoność
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
    pokaz_status(event.x, event.y)


def pokaz_wies():
    pokaz_prostokat(WIES)
    rysuj()


def pokaz_calosc():
    pokaz_prostokat(zasieg(wszystkie))
    rysuj()


def przybliz():
    zoom(SZEROKOSC / 2, WYSOKOSC / 2, 1.5)        # zoom względem środka okna


def oddal():
    zoom(SZEROKOSC / 2, WYSOKOSC / 2, 1 / 1.5)


# --- PROGRAM ---

dane = {}           # klasa -> lista obiektów
wszystkie = []      # wszystkie obiekty razem (do przycisku "Pokaż całość")
for klasa in KLASY:
    obiekty = wczytaj_klase(klasa)
    dane[klasa] = obiekty
    wszystkie = wszystkie + obiekty
print("Razem:", len(wszystkie), "obiektów")

# znaki umowne: czytamy style i układamy je według poziomu rysowania (od spodu do góry)
style = []
for klasa, plik in PLIKI_ZNAKOW:
    styl = wczytaj_znaki(plik)
    styl["klasa"] = klasa
    style.append(styl)
    print(f"{plik}: {len(styl['znaki'])} znaków, kod w polu {styl['pole']}")
style.sort(key=poziom_stylu)

# okienko: u góry przyciski, w środku mapa, na dole pasek ze współrzędnymi
okno = tk.Tk()
okno.title("Wola Karczewska – BDOT10k")

przyciski = tk.Frame(okno)
przyciski.pack(fill="x")
tk.Button(przyciski, text="Pokaż wieś", command=pokaz_wies).pack(side="left", padx=2, pady=2)
tk.Button(przyciski, text="Pokaż całość", command=pokaz_calosc).pack(side="left", padx=2, pady=2)
tk.Button(przyciski, text="Przybliż +", command=przybliz).pack(side="left", padx=2, pady=2)
tk.Button(przyciski, text="Oddal −", command=oddal).pack(side="left", padx=2, pady=2)

canvas = tk.Canvas(okno, width=SZEROKOSC, height=WYSOKOSC, bg="white")
canvas.pack()

pasek = tk.Label(okno, text="Najedź myszką na mapę", anchor="w")
pasek.pack(fill="x")

# podpinamy funkcje pod zdarzenia myszy
canvas.bind("<MouseWheel>", kolko_myszy)          # kółko na Windowsie
canvas.bind("<Button-4>", kolko_myszy)            # kółko na Linuksie (do góry)
canvas.bind("<Button-5>", kolko_myszy)            # kółko na Linuksie (w dół)
canvas.bind("<ButtonPress-1>", wcisniecie)
canvas.bind("<B1-Motion>", ciagniecie)
canvas.bind("<ButtonRelease-1>", puszczenie)
canvas.bind("<Motion>", ruch_myszy)

pokaz_prostokat(WIES)
print("Rysuję mapę...")
rysuj()
print(f"Skala: {widok['skala']:.3f} piksela na metr, lewy górny róg: {widok['x0']:.0f}, {widok['y0']:.0f}")

# na Windowsie okienko lubi otworzyć się pod VS Code – na chwilę stawiamy je na wierzchu
okno.attributes("-topmost", True)
okno.after(1000, okno.attributes, "-topmost", False)

okno.mainloop()
