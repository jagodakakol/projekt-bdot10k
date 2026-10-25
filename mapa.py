# mapa.py – przeglądarka danych BDOT10k (Wola Karczewska)
# Projekt z Geometrii obliczeniowej, dr hab. inż. Waldemar Izdebski
#
# Krok 1: wczytanie plików GML z folderu dane_wies.
# Krok 2: okienko i rysowanie mapy (przeliczanie współrzędnych teren -> ekran).
# Krok 3: nawigacja – zoom kółkiem, przesuwanie myszą, przyciski i pasek ze współrzędnymi.

import os
import xml.etree.ElementTree as ET
import tkinter as tk
import time

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

# rozmiar okienka z mapą (w pikselach)
SZEROKOSC = 1000
WYSOKOSC = 650

# prostokąt wsi (x_min, y_min, x_max, y_max) – ten obszar pokazujemy na starcie
WIES = (662400, 475400, 664900, 476900)

# proste style dla każdej klasy (jak "surowe" warstwy w QGIS – bez znaków umownych)
STYL = {
    "PTLZ_A": {"wypelnienie": "#b9dca0", "kontur": "#5e9442"},   # lasy
    "PTWP_A": {"wypelnienie": "#a9d2ea", "kontur": "#2a7ab8"},   # wody
    "TCRZ_A": {"wypelnienie": "",        "kontur": "#2f9e44"},   # rezerwat – sam kontur
    "BUBD_A": {"wypelnienie": "#f6b26b", "kontur": "#a0522d"},   # budynki
    "SKDR_L": {"kolor": "#7b3fa0", "grubosc": 2},                # drogi
    "SWRS_L": {"kolor": "#2a7ab8", "grubosc": 2},                # rzeki
    "ADMS_P": {"kolor": "#d62728", "promien": 5},                # miejscowości
}


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
        obiekt = {"klasa": klasa, "typ": typ, "geometria": geometria, "atrybuty": atrybuty}
        # prostokąt otaczający liczymy raz, przy wczytywaniu – przyda się przy rysowaniu
        obiekt["prostokat"] = prostokat_otaczajacy(wszystkie_punkty(obiekt))
        if typ == "poligon":
            obiekt["sciezka"] = sciezka_z_dziurami(geometria)   # też liczymy raz, przy wczytywaniu
        obiekty.append(obiekt)
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


def rysuj_poligon(obiekt, styl):
    pierscienie = obiekt["geometria"]
    if styl["wypelnienie"] != "":
        # Wypełnienie z dziurami: tkinter nie zna dziur, więc rysujemy jedną ścieżkę z "mostkami"
        # (patrz sciezka_z_dziurami). Tkinter wypełnia według reguły parzystości: punkt jest w środku,
        # jeśli linia poprowadzona od niego w bok przecina brzeg nieparzystą liczbę razy.
        # Z wnętrza dziury przecina parzyście, więc dziura zostaje pusta, a każdy mostek
        # przechodzimy dwa razy (tam i z powrotem), więc się znosi.
        piksele = lista_pikseli(obiekt["sciezka"])
        if len(piksele) >= 6:                     # poligon potrzebuje co najmniej 3 punktów
            canvas.create_polygon(piksele, fill=styl["wypelnienie"], outline="")
    # kontury rysujemy osobno liniami, żeby nie było widać mostków
    for pierscien in pierscienie:
        piksele = lista_pikseli(pierscien)
        if len(piksele) >= 4:                     # linia potrzebuje co najmniej 2 punktów
            canvas.create_line(piksele, fill=styl["kontur"])


def rysuj_linie(obiekt, styl):
    piksele = lista_pikseli(obiekt["geometria"])
    if len(piksele) >= 4:
        canvas.create_line(piksele, fill=styl["kolor"], width=styl["grubosc"])


def rysuj_punkt(obiekt, styl):
    x, y = obiekt["geometria"]
    x_ekr, y_ekr = teren_na_ekran(x, y)
    r = styl["promien"]
    canvas.create_oval(x_ekr - r, y_ekr - r, x_ekr + r, y_ekr + r, fill=styl["kolor"], outline="black")
    nazwa = obiekt["atrybuty"].get("nazwa")
    if nazwa:
        canvas.create_text(x_ekr, y_ekr - 12, text=nazwa, font=("Arial", 11, "bold"))


def widoczny_prostokat():
    """Prostokąt terenu, który aktualnie widać w okienku (x_min, y_min, x_max, y_max)."""
    x_min, y_max = ekran_na_teren(0, 0)                    # lewy górny róg okienka
    x_max, y_min = ekran_na_teren(SZEROKOSC, WYSOKOSC)     # prawy dolny róg okienka
    return x_min, y_min, x_max, y_max


def rysuj():
    """Czyści okienko i rysuje obiekty w kolejności z listy KLASY.
    Rysujemy tylko te obiekty, których prostokąt otaczający nachodzi na to, co widać w okienku."""
    start = time.time()
    canvas.delete("all")
    ekran = widoczny_prostokat()
    narysowane = 0
    for obiekt in wszystkie:
        if not prostokaty_nachodza(obiekt["prostokat"], ekran):
            continue                              # obiekt poza okienkiem – szkoda czasu
        narysowane += 1
        styl = STYL[obiekt["klasa"]]
        if obiekt["typ"] == "poligon":
            rysuj_poligon(obiekt, styl)
        elif obiekt["typ"] == "linia":
            rysuj_linie(obiekt, styl)
        elif obiekt["typ"] == "punkt":
            rysuj_punkt(obiekt, styl)
    print(f"Narysowano {narysowane} obiektów w {time.time() - start:.2f} s")


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

wszystkie = []
for klasa in KLASY:
    obiekty = wczytaj_klase(klasa)
    wszystkie = wszystkie + obiekty
    print(f"{klasa}: {len(obiekty)} obiektów")
print("Razem:", len(wszystkie), "obiektów")

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
