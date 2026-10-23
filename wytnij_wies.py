# wytnij_wies.py
# Program pomocniczy do projektu z Geometrii obliczeniowej (dr hab. inż. W. Izdebski).
# Z paczki BDOT10k dla całego powiatu otwockiego wycina tylko obiekty
# z okolic Woli Karczewskiej i zapisuje je do małych plików GML w folderze dane_wies.
# Uruchamiamy go tylko raz (albo po pobraniu nowych danych).

import os
import re

# --- USTAWIENIA ---

# folder, w którym leży ten plik (czyli folder projektu)
FOLDER_PROJEKTU = os.path.dirname(os.path.abspath(__file__))

# skąd czytamy dane (paczka powiatu 1417) i dokąd zapisujemy wycinek
FOLDER_POWIAT = os.path.join(FOLDER_PROJEKTU, "dane", "1417_GML", "PL.PZGiK.330.1417", "BDOT10k")
FOLDER_WIES = os.path.join(FOLDER_PROJEKTU, "dane_wies")

# początek nazwy każdego pliku w paczce
PRZEDROSTEK = "PL.PZGiK.330.1417__"

# prostokąt wokół Woli Karczewskiej w układzie PUWG 1992 (EPSG:2180)
# x = współrzędna wschodnia, y = północna (w takiej kolejności są zapisane w plikach GML)
X_MIN = 662400
X_MAX = 664900
Y_MIN = 475400
Y_MAX = 476900

# klasy obiektów, które bierzemy do projektu
KLASY = ["PTLZ_A", "PTWP_A", "TCRZ_A", "BUBD_A", "SKDR_L", "SWRS_L", "ADMS_P"]


# --- FUNKCJE ---

def punkty_obiektu(tekst_obiektu):
    """Zwraca listę wszystkich punktów (x, y) zapisanych w gml:pos i gml:posList."""
    punkty = []
    # szukamy tekstu między <gml:pos> albo <gml:posList> a następnym znakiem <
    for liczby_tekst in re.findall(r"<gml:pos(?:List)?[^>]*>([^<]*)<", tekst_obiektu):
        liczby = liczby_tekst.split()           # "x1 y1 x2 y2" -> ["x1", "y1", "x2", "y2"]
        for i in range(0, len(liczby) - 1, 2):  # bierzemy liczby parami
            x = float(liczby[i])
            y = float(liczby[i + 1])
            punkty.append((x, y))
    return punkty


def prostokat_otaczajacy(punkty):
    """Zwraca (x_min, y_min, x_max, y_max), czyli najmniejszy prostokąt,
    w którym mieszczą się wszystkie punkty."""
    xs = [p[0] for p in punkty]
    ys = [p[1] for p in punkty]
    return min(xs), min(ys), max(xs), max(ys)


def prostokaty_nachodza(a, b):
    """Sprawdza, czy dwa prostokąty (x_min, y_min, x_max, y_max) mają część wspólną.
    Nie nachodzą tylko wtedy, gdy jeden leży całkiem na lewo, na prawo, pod albo nad drugim."""
    if a[2] < b[0] or a[0] > b[2]:   # a całkiem na lewo albo na prawo od b
        return False
    if a[3] < b[1] or a[1] > b[3]:   # a całkiem pod albo nad b
        return False
    return True


def wytnij_klase(klasa):
    """Czyta plik jednej klasy dla powiatu i zapisuje tylko obiekty z prostokąta wsi."""
    sciezka_we = os.path.join(FOLDER_POWIAT, PRZEDROSTEK + "OT_" + klasa + ".xml")
    sciezka_wy = os.path.join(FOLDER_WIES, "OT_" + klasa + ".xml")

    # utf-8-sig, bo pliki z Geoportalu zaczynają się niewidocznym znakiem BOM
    with open(sciezka_we, encoding="utf-8-sig") as plik:
        tekst = plik.read()

    # odcinamy znacznik zamykający cały plik, dopiszemy go z powrotem na końcu
    tekst = tekst.replace("</gml:FeatureCollection>", "")

    # dzielimy plik na kawałki: [nagłówek, obiekt1, obiekt2, ...]
    kawalki = tekst.split("<gml:featureMember>")
    naglowek = kawalki[0]
    obiekty = kawalki[1:]

    prostokat_wsi = (X_MIN, Y_MIN, X_MAX, Y_MAX)
    zostawione = []
    for obiekt in obiekty:
        punkty = punkty_obiektu(obiekt)
        if len(punkty) == 0:
            continue
        if prostokaty_nachodza(prostokat_otaczajacy(punkty), prostokat_wsi):
            zostawione.append(obiekt)

    with open(sciezka_wy, "w", encoding="utf-8") as plik:
        plik.write(naglowek)
        for obiekt in zostawione:
            plik.write("<gml:featureMember>" + obiekt)
        plik.write("</gml:FeatureCollection>\n")

    print(f"{klasa}: w powiecie {len(obiekty)} obiektów, w okolicy wsi {len(zostawione)}")


# --- PROGRAM ---

os.makedirs(FOLDER_WIES, exist_ok=True)   # tworzymy folder dane_wies, jeśli go nie ma
for klasa in KLASY:
    wytnij_klase(klasa)
print("Gotowe! Wycięte pliki są w folderze dane_wies")
