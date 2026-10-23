# mapa.py – przeglądarka danych BDOT10k (Wola Karczewska)
# Projekt z Geometrii obliczeniowej, dr hab. inż. Waldemar Izdebski
#
# Krok 1: wczytanie plików GML z folderu dane_wies i sprawdzenie, co w nich jest.

import os
import xml.etree.ElementTree as ET

# --- USTAWIENIA ---

# folder projektu i folder z wyciętymi danymi (zrobionymi przez wytnij_wies.py)
FOLDER_PROJEKTU = os.path.dirname(os.path.abspath(__file__))
FOLDER_DANYCH = os.path.join(FOLDER_PROJEKTU, "dane_wies")

# przestrzenie nazw z nagłówka plików GML – to one stoją za przedrostkami "gml:" i "ot:"
NS = {
    "gml": "http://www.opengis.net/gml/3.2",
    "ot": "urn:gugik:specyfikacje:gmlas:bazaDanychObiektowTopograficznych10k:2.0",
}

# klasy w kolejności rysowania: najpierw poligony, potem linie, na końcu punkty
KLASY = ["PTLZ_A", "PTWP_A", "TCRZ_A", "BUBD_A", "SKDR_L", "SWRS_L", "ADMS_P"]


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
        obiekty.append({"klasa": klasa, "typ": typ, "geometria": geometria, "atrybuty": atrybuty})
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


def zasieg(obiekty):
    """Zasięg danych: najmniejszy prostokąt (x_min, y_min, x_max, y_max), w którym mieszczą się wszystkie obiekty."""
    xs = []
    ys = []
    for obiekt in obiekty:
        for x, y in wszystkie_punkty(obiekt):
            xs.append(x)
            ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


# --- PROGRAM ---

wszystkie = []
for klasa in KLASY:
    obiekty = wczytaj_klase(klasa)
    wszystkie = wszystkie + obiekty
    print(f"{klasa}: {len(obiekty)} obiektów")

# ile jest obiektów każdego typu geometrii
ile = {"punkt": 0, "linia": 0, "poligon": 0}
dziury = 0
for obiekt in wszystkie:
    ile[obiekt["typ"]] += 1
    if obiekt["typ"] == "poligon":
        dziury += len(obiekt["geometria"]) - 1    # wszystko poza obwodem to dziury
print("Razem:", len(wszystkie), "obiektów –", ile, "– dziur w poligonach:", dziury)

# zasięg wszystkich danych
x_min, y_min, x_max, y_max = zasieg(wszystkie)
print(f"Zasięg: x od {x_min:.0f} do {x_max:.0f}, y od {y_min:.0f} do {y_max:.0f}")
print(f"Szerokość {x_max - x_min:.0f} m, wysokość {y_max - y_min:.0f} m")

# dla sprawdzenia: punkt Woli Karczewskiej
for obiekt in wszystkie:
    if obiekt["klasa"] == "ADMS_P":
        print("Miejscowość:", obiekt["atrybuty"]["nazwa"], obiekt["geometria"],
              "mieszkańców:", obiekt["atrybuty"]["liczbaMieszkancow"])
