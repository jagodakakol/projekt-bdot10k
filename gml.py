# gml.py – wczytywanie danych BDOT10k z plików GML (własny parser, bez bibliotek GIS)
# Projekt z Geometrii obliczeniowej, dr hab. inż. Waldemar Izdebski
#
# Wczytujemy cały powiat: wszystkie pliki klas (OT_xxxx_A/L/P.xml) z wybranego folderu albo z pliku ZIP.
# Pliki są duże (budynki powiatu otwockiego to 96 MB), więc czytamy je STRUMIENIOWO (iterparse):
# obiekt po obiekcie, a każdy przeczytany kawałek XML od razu wyrzucamy z pamięci.

import os
import re
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from array import array

# przestrzeń nazw GML (to ona stoi za przedrostkiem "gml:" w plikach)
GML = "{http://www.opengis.net/gml/3.2}"

# Kolejność współrzędnych w plikach z Geoportalu: najpierw wschodnia (E), potem północna (N),
# np. Wola Karczewska: 663647.12 476125.76. (PDF z kryteriami podaje odwrotnie – sprawdziłyśmy na danych
# i na zrzutach z QGIS.) Gdyby trafił się plik z odwrotną kolejnością, wystarczy zmienić na False.
NAJPIERW_WSCHODNIA = True

# nazwa pliku klasy: "PL.PZGiK.330.1417__OT_BUBD_A.xml" albo po prostu "OT_BUBD_A.xml"
WZOR_NAZWY = re.compile(r"OT_([A-Z]{4})_([APL])\.(xml|gml)$", re.IGNORECASE)

# kategorie BDOT10k – dwie pierwsze litery kodu klasy
KATEGORIE = {
    "SW": "sieć wodna",
    "SK": "sieć komunikacyjna",
    "SU": "sieć uzbrojenia terenu",
    "BU": "budynki i budowle",
    "PT": "pokrycie terenu",
    "KU": "kompleksy użytkowania terenu",
    "TC": "tereny chronione",
    "AD": "podział administracyjny",
    "OI": "inne obiekty",
    "RT": "rzeźba terenu",
}


def klasa_z_nazwy(nazwa_pliku):
    """"PL.PZGiK.330.1417__OT_BUBD_A.xml" -> "BUBD_A". Dla innych plików zwraca None."""
    wynik = WZOR_NAZWY.search(nazwa_pliku)
    if wynik is None:
        return None
    return wynik.group(1).upper() + "_" + wynik.group(2).upper()


def tekst_na_wspolrzedne(tekst):
    """Zamienia napis "x1 y1 x2 y2 ..." na tablicę liczb [x1, y1, x2, y2, ...].
    Używamy array("d") z biblioteki standardowej: liczba zajmuje w niej 8 bajtów,
    a jako zwykły float w liście ok. 32 bajty. Przy 2 mln punktów to duża różnica."""
    wsp = array("d", map(float, tekst.split()))   # map(float, ...) = float() dla każdego kawałka
    if not NAJPIERW_WSCHODNIA:
        wsp[0::2], wsp[1::2] = wsp[1::2], wsp[0::2]   # zamiana miejscami w każdej parze
    return wsp


def odczytaj_geometrie(element):
    """Odczytuje geometrię ze znacznika <ot:geometria>. Zwraca (typ, części):
    poligon -> lista wielokątów, a każdy wielokąt to lista pierścieni [obwód, dziura1, ...]
    linia   -> lista łamanych
    punkt   -> lista punktów (x, y)
    Obiekt może mieć kilka części (geometria wieloczęściowa, np. gml:MultiSurface) – stąd listy."""
    poligony = element.findall(".//" + GML + "Polygon")
    if len(poligony) > 0:
        czesci = []
        for poligon in poligony:
            pierscienie = []
            for granica in poligon:                       # najpierw gml:exterior, potem gml:interior
                lista = granica.find(".//" + GML + "posList")
                if lista is not None:
                    pierscienie.append(tekst_na_wspolrzedne(lista.text))
            if len(pierscienie) > 0:
                czesci.append(pierscienie)
        return "poligon", czesci

    krzywe = element.findall(".//" + GML + "Curve") + element.findall(".//" + GML + "LineString")
    if len(krzywe) > 0:
        czesci = []
        for krzywa in krzywe:
            wsp = array("d")
            for lista in krzywa.iter(GML + "posList"):    # krzywa może mieć kilka odcinków – sklejamy je
                wsp.extend(tekst_na_wspolrzedne(lista.text))
            czesci.append(wsp)
        return "linia", czesci

    pozycje = element.findall(".//" + GML + "pos")
    if len(pozycje) > 0:
        czesci = []
        for pozycja in pozycje:
            wsp = tekst_na_wspolrzedne(pozycja.text)
            czesci.append((wsp[0], wsp[1]))
        return "punkt", czesci

    return None, []        # obiekt bez geometrii, której nie znamy – pominiemy go


def prostokat_obiektu(typ, czesci):
    """Prostokąt otaczający (x_min, y_min, x_max, y_max) liczony jednym przebiegiem po współrzędnych,
    od razu przy wczytywaniu. Dla poligonu wystarczą obwody (dziury i tak leżą w środku)."""
    x_min = float("inf")
    y_min = float("inf")
    x_max = float("-inf")
    y_max = float("-inf")
    if typ == "punkt":
        for x, y in czesci:
            x_min = min(x_min, x)
            x_max = max(x_max, x)
            y_min = min(y_min, y)
            y_max = max(y_max, y)
        return x_min, y_min, x_max, y_max
    if typ == "poligon":
        linie = []
        for pierscienie in czesci:
            linie.append(pierscienie[0])                  # sam obwód
    else:
        linie = czesci
    for wsp in linie:
        for i in range(0, len(wsp), 2):
            x = wsp[i]
            y = wsp[i + 1]
            if x < x_min:
                x_min = x
            if x > x_max:
                x_max = x
            if y < y_min:
                y_min = y
            if y > y_max:
                y_max = y
    return x_min, y_min, x_max, y_max


def sciezka_z_dziurami(pierscienie):
    """Łączy obwód poligonu i jego dziury w jedną ścieżkę do wypełnienia (sztuczka z "mostkami").
    Każdą dziurę doczepiamy do NAJBLIŻSZEGO wierzchołka obwodu, żeby mostki były jak najkrótsze:
    idziemy po obwodzie, w tym wierzchołku skaczemy do dziury, obchodzimy ją i wracamy.
    Poligon bez dziur nie potrzebuje mostków – wtedy ścieżką jest sam obwód (nic nie kopiujemy)."""
    obwod = pierscienie[0]
    if len(pierscienie) == 1:
        return obwod
    doczepione = {}          # numer wierzchołka obwodu -> lista dziur doczepionych w tym miejscu
    for dziura in pierscienie[1:]:
        dx = dziura[0]                                    # pierwszy punkt dziury
        dy = dziura[1]
        najblizszy = 0
        najmniejsza = None
        for i in range(0, len(obwod), 2):
            odleglosc = (obwod[i] - dx) ** 2 + (obwod[i + 1] - dy) ** 2   # kwadrat odległości wystarczy
            if najmniejsza is None or odleglosc < najmniejsza:
                najmniejsza = odleglosc
                najblizszy = i
        if najblizszy not in doczepione:
            doczepione[najblizszy] = []
        doczepione[najblizszy].append(dziura)
    sciezka = array("d")
    for i in range(0, len(obwod), 2):
        sciezka.append(obwod[i])
        sciezka.append(obwod[i + 1])
        if i in doczepione:
            for dziura in doczepione[i]:
                sciezka.extend(dziura)                    # tam (mostek) i dookoła dziury...
                sciezka.append(obwod[i])                  # ...i z powrotem do obwodu
                sciezka.append(obwod[i + 1])
    return sciezka


def odczytaj_obiekt(element, klasa):
    """Zamienia jeden obiekt z pliku (np. <ot:OT_BUBD_A>) na słownik:
    {"klasa", "typ", "czesci", "atrybuty", "prostokat"} (+ "sciezki" dla poligonów)."""
    atrybuty = {}
    typ = None
    czesci = []
    for dziecko in element:
        nazwa = dziecko.tag.split("}")[-1]                # "{urn:...}kodKarto10k" -> "kodKarto10k"
        if nazwa == "geometria":
            typ, czesci = odczytaj_geometrie(dziecko)
        elif dziecko.text is not None and dziecko.text.strip() != "":
            # sys.intern: ten sam napis (np. "eksploatowany" w 60 tys. budynków) trzymamy w pamięci raz
            atrybuty[sys.intern(nazwa)] = sys.intern(dziecko.text.strip())
    if typ is None or len(czesci) == 0:
        return None
    obiekt = {"klasa": klasa, "typ": typ, "czesci": czesci, "atrybuty": atrybuty,
              "prostokat": prostokat_obiektu(typ, czesci)}
    if typ == "poligon":
        obiekt["sciezki"] = []
        for pierscienie in czesci:
            obiekt["sciezki"].append(sciezka_z_dziurami(pierscienie))
    return obiekt


def wczytaj_plik(plik, klasa, postep=None):
    """Czyta jeden plik klasy strumieniowo. Zwraca (lista obiektów, ile usunięto nieaktualnych).
    iterparse podaje znaczniki po kolei, w miarę czytania pliku; gdy skończy się <gml:featureMember>,
    zamieniamy go na obiekt, a potem czyścimy korzeń, żeby przeczytany XML nie zostawał w pamięci."""
    obiekty = []
    usuniete = 0
    korzen = None
    for zdarzenie, element in ET.iterparse(plik, events=("start", "end")):
        if korzen is None:
            korzen = element                              # pierwszy znacznik: <gml:FeatureCollection>
        if zdarzenie != "end" or element.tag != GML + "featureMember":
            continue
        if len(element) > 0:
            obiekt = odczytaj_obiekt(element[0], klasa)
            if obiekt is not None:
                # "Usuwamy dane" nieaktualne: BDOT10k przechowuje też stare wersje obiektów – mają wpisaną
                # datę koniecWersjiObiektu. Wtyczka GUGiK pokazuje tylko obiekty aktualne, więc my też.
                if obiekt["atrybuty"].get("koniecWersjiObiektu"):
                    usuniete += 1
                else:
                    obiekty.append(obiekt)
        korzen.clear()                                    # wyrzucamy przeczytany kawałek XML z pamięci
        if postep is not None and len(obiekty) % 5000 == 0 and len(obiekty) > 0:
            postep(f"Wczytuję {klasa}: {len(obiekty)} obiektów...")
    return obiekty, usuniete


def wczytaj_dane(sciezka, postep=None):
    """Wczytuje wszystkie pliki klas z folderu (razem z podfolderami) albo z pliku ZIP.
    Zwraca słownik {klasa: lista obiektów}. postep to funkcja, której podajemy napisy o postępie."""
    start = time.time()
    archiwum = None
    if sciezka.lower().endswith(".zip"):
        archiwum = zipfile.ZipFile(sciezka)               # ZIP czytamy bezpośrednio, bez rozpakowywania
        nazwy = archiwum.namelist()
    else:
        nazwy = []
        for folder, podfoldery, pliki in os.walk(sciezka):
            for nazwa in pliki:
                nazwy.append(os.path.join(folder, nazwa))

    pliki_klas = []
    for nazwa in sorted(nazwy):
        klasa = klasa_z_nazwy(nazwa)
        if klasa is not None:
            pliki_klas.append((klasa, nazwa))

    dane = {}
    usuniete_razem = 0
    numer = 0
    for klasa, nazwa in pliki_klas:
        numer += 1
        if postep is not None:
            postep(f"Wczytuję {klasa} ({numer}/{len(pliki_klas)})...")
        if archiwum is not None:
            plik = archiwum.open(nazwa)
        else:
            plik = open(nazwa, "rb")
        obiekty, usuniete = wczytaj_plik(plik, klasa, postep)
        plik.close()
        usuniete_razem += usuniete
        if len(obiekty) > 0:                              # pliki po 0,4 KB to klasy bez obiektów
            if klasa not in dane:
                dane[klasa] = []
            dane[klasa].extend(obiekty)
    if archiwum is not None:
        archiwum.close()

    liczba = 0
    for klasa in dane:
        liczba += len(dane[klasa])
    czas = time.time() - start
    opis = (f"Wczytano {liczba:,} obiektów z {len(dane)} klas w {czas:.1f} s"
            f" (usunięte nieaktualne wersje: {usuniete_razem})").replace(",", " ")
    return dane, opis


def zasieg_danych(dane):
    """Najmniejszy prostokąt, w którym mieszczą się wszystkie obiekty – suma prostokątów obiektów."""
    x_min = float("inf")
    y_min = float("inf")
    x_max = float("-inf")
    y_max = float("-inf")
    for klasa in dane:
        for obiekt in dane[klasa]:
            p = obiekt["prostokat"]
            x_min = min(x_min, p[0])
            y_min = min(y_min, p[1])
            x_max = max(x_max, p[2])
            y_max = max(y_max, p[3])
    return x_min, y_min, x_max, y_max


# test: python gml.py <folder albo plik ZIP> – wczytuje dane i wypisuje, ile jest obiektów w każdej klasie
if __name__ == "__main__":
    dane, opis = wczytaj_dane(sys.argv[1], print)
    for klasa in sorted(dane):
        print(klasa, len(dane[klasa]))
    print(opis)
    print("Zasięg:", zasieg_danych(dane))
