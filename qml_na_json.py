# qml_na_json.py – zamienia style QML wtyczki GUGiK na nasz własny, czytelny plik znaki.json
# Projekt z Geometrii obliczeniowej, dr hab. inż. Waldemar Izdebski
#
# PDF z kryteriami: "Reguły należy odczytać ze stylów wtyczki i zapisać we własnym, czytelnym formacie
# (np. JSON lub tabela)". Ten skrypt uruchamiamy raz (albo po zmianie stylów); mapa.py czyta już tylko znaki.json.
#
# Skąd co bierzemy (folder znaki, pliki z repozytorium wtyczki BDOT10k_GML_SHP, licencja GPL-3.0):
#   layer_specs.py – lista warstw wtyczki: która klasa, który plik stylu, jaki filtr, w jakiej kolejności
#   *.qml          – style: kod obiektu (kodKarto10k) -> znak umowny złożony z warstw
# Wszystkie wielkości zapisujemy w MILIMETRACH MAPY w skali 1:10 000 (tak każe PDF):
#   jednostka mapy (MapUnit) to metry w terenie, a 1 mm na mapie 1:10 000 = 10 m w terenie, więc mm = m / 10;
#   jednostka MM w QGIS to już milimetry.

import ast
import base64
import hashlib
import json
import math
import os
import re
import xml.etree.ElementTree as ET

FOLDER_ZNAKOW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "znaki")
PLIK_WARSTW = os.path.join(FOLDER_ZNAKOW, "layer_specs.py")
PLIK_WYNIKOWY = os.path.join(FOLDER_ZNAKOW, "znaki.json")
FOLDER_SVG = os.path.join(FOLDER_ZNAKOW, "svg")          # symbole SVG, które style wskazują jako pliki
SKALA_ODNIESIENIA = 10000

KONCOWKI = {"flat": "butt", "round": "round", "square": "projecting"}   # nazwy z QGIS -> nazwy z tkintera

# tu zbieramy, czego nie umiemy zamienić – wypiszemy to na końcu
nieobslugiwane = {}
# symbole SVG zamienione na nasze kształty: nazwa -> opis (trafia do znaki.json, sekcja "svg")
symbole_svg = {}


def zapamietaj_brak(opis):
    nieobslugiwane[opis] = nieobslugiwane.get(opis, 0) + 1


def wczytaj_liste_warstw():
    """Lista warstw wtyczki z pliku layer_specs.py. To plik Pythona, ale go NIE uruchamiamy:
    ast.literal_eval odczytuje z niego samą listę słowników (tylko dane, żadnego kodu).
    We wtyczce lista idzie od warstwy na wierzchu do warstwy na spodzie – odwracamy ją,
    bo my rysujemy od spodu. Bierzemy tylko warstwy mapy ("main"), bez napisów ("labels")."""
    tekst = open(PLIK_WARSTW, encoding="utf-8").read()
    for wezel in ast.parse(tekst).body:
        if isinstance(wezel, ast.Assign) and wezel.targets[0].id == "LAYER_SPECS":
            lista = ast.literal_eval(wezel.value)
            warstwy = []
            for pozycja in lista:
                if pozycja["target"] == "main":
                    warstwy.append(pozycja)
            warstwy.reverse()
            return warstwy
    return []


def kolor_qgis(tekst):
    """"204,100,21,255" -> "#cc6415" (przezroczystość pomijamy – tkinter jej nie zna)."""
    czesci = tekst.split(",")
    return f"#{int(czesci[0]):02x}{int(czesci[1]):02x}{int(czesci[2]):02x}"


def ustawienia_warstwy(warstwa):
    """Ustawienia warstwy symbolu: <prop k="nazwa" v="wartość"/> -> słownik."""
    ustawienia = {}
    for prop in warstwa.findall("prop"):
        ustawienia[prop.get("k")] = prop.get("v")
    return ustawienia


def na_mm(wartosc, jednostka):
    """Wielkość z QGIS -> milimetry mapy w skali 1:10 000."""
    wartosc = float(wartosc)
    if jednostka == "MM":
        return round(wartosc, 4)
    return round(wartosc / 10, 4)          # MapUnit: metry w terenie / 10


def para_na_mm(tekst, jednostka):
    """"0,3.5" (przesunięcie x,y) -> [0.0, 0.35] w mm."""
    czesci = (tekst or "0,0").split(",")
    return [na_mm(czesci[0], jednostka), na_mm(czesci[1], jednostka)]


def tlumacz_pole(nazwa, pola):
    """Nazwa pola z wyrażenia -> nazwa atrybutu w GML. Pola wirtualne (np. SZERNAWIE) mają w stylu
    "tłumaczenie"; nazwy pisane wielkimi literami (jak w SHP, np. SZEROKOSC) zamieniamy na małe."""
    if nazwa in pola:
        return pola[nazwa]
    if nazwa.isupper():
        return nazwa.lower()
    return nazwa


def wzor_liniowy(wyrazenie, pola, jednostka):
    """Zamienia proste wyrażenie QGIS, np. "SZERNAWIE"*0.9 + 2 albo -1*SZEROKOSC/2, na wzór
    wartość = mnożnik · pole + dodatek (od razu w mm). Sposób: w miejsce pola wstawiamy x,
    sprawdzamy, że zostały same liczby i działania, i liczymy wartość dla x = 0, 1 i 2:
    dodatek = f(0), mnożnik = f(1) − f(0), a f(2) musi wyjść 2·mnożnik + dodatek (czyli wzór jest liniowy).
    Bardziej złożonych wyrażeń (if, CASE, funkcje) nie obsługujemy – zwracamy None i zostaje stała wartość."""
    nazwy = []
    for w_cudzyslowie, bez_cudzyslowu in re.findall(r'"([^"]+)"|([A-Za-z_][A-Za-z_0-9]*)', wyrazenie):
        nazwy.append(w_cudzyslowie or bez_cudzyslowu)
    if len(nazwy) == 0 or len(set(nazwy)) > 1:
        return None                                  # brak pola albo kilka różnych pól, np. if(...)
    tekst = re.sub(r'"[^"]+"|[A-Za-z_][A-Za-z_0-9]*', "x", wyrazenie)
    if re.fullmatch(r"[0-9x.+\-*/()\s]*", tekst) is None:
        return None                                  # zostało coś innego niż liczby i działania
    try:
        # eval liczy napis jak wyrażenie Pythona; sprawdziłyśmy wyżej, że są w nim tylko liczby, x i działania
        f0 = eval(tekst, {"__builtins__": {}}, {"x": 0.0})
        f1 = eval(tekst, {"__builtins__": {}}, {"x": 1.0})
        f2 = eval(tekst, {"__builtins__": {}}, {"x": 2.0})
    except Exception:
        return None
    mnoznik = f1 - f0
    dodatek = f0
    if abs(f2 - (2 * mnoznik + dodatek)) > 1e-9:
        return None                                  # wzór nie jest liniowy
    return {"pole": tlumacz_pole(nazwy[0], pola),
            "mnoznik": na_mm(mnoznik, jednostka), "dodatek": na_mm(dodatek, jednostka)}


def wlasciwosc_z_danych(warstwa, nazwa, pola, jednostka):
    """Wartość liczona z atrybutu obiektu (w QGIS "data defined"), np. nazwa="outlineWidth" (grubość)
    albo "offset" (przesunięcie linii). Zwraca wzór liniowy albo None."""
    dd = warstwa.find("data_defined_properties")
    if dd is None:
        return None
    for wlasciwosc in dd.iter("Option"):
        if wlasciwosc.get("name") != nazwa:
            continue
        aktywna = wlasciwosc.find("./Option[@name='active']")
        wyrazenie = wlasciwosc.find("./Option[@name='expression']")
        if aktywna is None or aktywna.get("value") != "true" or wyrazenie is None:
            return None
        wzor = wzor_liniowy(wyrazenie.get("value"), pola, jednostka)
        if wzor is None:
            zapamietaj_brak(f"wyrażenie dla {nazwa} (zostaje stała wartość)")
        return wzor
    return None


# --- SYMBOLE SVG -> nasze kształty (wielokąty i linie) ---
# tkinter nie umie rysować SVG, więc każdy symbol zamieniamy tu raz na listę wielokątów i linii,
# zapisanych względem środka symbolu i podzielonych przez jego szerokość (szerokość symbolu = 1).
# W programie wystarczy je potem przeskalować do wielkości znaczka, obrócić i przesunąć.

def tekst_svg(nazwa_w_stylu):
    """Treść SVG: wpisana w styl (base64:...) albo z pliku w folderze znaki/svg. None, jeśli nie ma."""
    if nazwa_w_stylu.startswith("base64:"):
        return base64.b64decode(nazwa_w_stylu[7:]).decode("utf-8", "replace")
    plik = nazwa_w_stylu.replace("\\", "/").split("/")[-1]
    sciezka = os.path.join(FOLDER_SVG, plik)
    if plik == "" or not os.path.exists(sciezka):
        return None
    return open(sciezka, encoding="utf-8").read()


def nazwa_svg(nazwa_w_stylu):
    """Nazwa symbolu SVG: z nazwy pliku albo z atrybutu sodipodi:docname, np. "0010_330.svg" -> "0010_330"."""
    if nazwa_w_stylu.startswith("base64:"):
        tekst = tekst_svg(nazwa_w_stylu)
        wynik = re.search(r'docname="([^"]+)"', tekst)
        if wynik is None:
            # symbol bez nazwy: nazwę robimy z "odcisku" treści (skrót MD5) – inne rysunki dają inne nazwy
            return "svg_" + hashlib.md5(tekst.encode("utf-8")).hexdigest()[:8]
        nazwa = wynik.group(1)
    else:
        nazwa = nazwa_w_stylu.replace("\\", "/").split("/")[-1]
    return nazwa.replace(".svg", "").strip()


def kolor_svg(tekst):
    """Kolor z SVG ("#1a171b", "#fff", "black", "none") -> "#rrggbb" albo "" (brak koloru)."""
    t = tekst.strip().lower()
    if t in ("none", "transparent", ""):
        return ""
    if t.startswith("#") and len(t) == 4:
        return "#" + t[1] * 2 + t[2] * 2 + t[3] * 2
    if t.startswith("#") and len(t) == 7:
        return t
    if t.startswith("rgb("):
        liczby = re.findall(r"[\d.]+", t)
        return f"#{int(float(liczby[0])):02x}{int(float(liczby[1])):02x}{int(float(liczby[2])):02x}"
    nazwy = {"black": "#000000", "white": "#ffffff", "red": "#ff0000", "green": "#008000", "blue": "#0000ff",
             "gray": "#808080", "grey": "#808080"}
    return nazwy.get(t, "#000000")


def styl_elementu(element, styl_rodzica):
    """Styl w SVG dziedziczy się z elementów nadrzędnych (np. z <g>). Zbieramy fill, stroke, stroke-width...
    z atrybutów i z atrybutu style="fill:#000;stroke:none"."""
    styl = dict(styl_rodzica)
    for nazwa in ("fill", "stroke", "stroke-width", "fill-opacity", "display"):
        if element.get(nazwa) is not None:
            styl[nazwa] = element.get(nazwa)
    for kawalek in (element.get("style") or "").split(";"):
        if ":" in kawalek:
            klucz, wartosc = kawalek.split(":", 1)
            styl[klucz.strip()] = wartosc.strip()
    return styl


def zloz(m1, m2):
    """Złożenie dwóch przekształceń afinicznych (a, b, c, d, e, f): x' = a·x + c·y + e, y' = b·x + d·y + f.
    Wynik działa tak, jakby najpierw wykonać m2, a potem m1 (mnożenie macierzy 3×3)."""
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)


def przeksztalcenie(tekst):
    """Atrybut transform, np. "translate(-36.1,-0.6) rotate(45)" -> jedno przekształcenie afiniczne."""
    m = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)              # przekształcenie tożsamościowe
    for nazwa, argumenty in re.findall(r"(\w+)\s*\(([^)]*)\)", tekst or ""):
        liczby = [float(x) for x in re.findall(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", argumenty)]
        if nazwa == "translate":
            nowe = (1, 0, 0, 1, liczby[0], liczby[1] if len(liczby) > 1 else 0)
        elif nazwa == "scale":
            sy = liczby[1] if len(liczby) > 1 else liczby[0]
            nowe = (liczby[0], 0, 0, sy, 0, 0)
        elif nazwa == "rotate":
            k = math.radians(liczby[0])
            nowe = (math.cos(k), math.sin(k), -math.sin(k), math.cos(k), 0, 0)
            if len(liczby) == 3:                         # obrót wokół punktu (cx, cy)
                nowe = zloz((1, 0, 0, 1, liczby[1], liczby[2]), zloz(nowe, (1, 0, 0, 1, -liczby[1], -liczby[2])))
        elif nazwa == "matrix":
            nowe = tuple(liczby[:6])
        else:
            zapamietaj_brak(f"SVG transform {nazwa}")
            continue
        m = zloz(m, nowe)
    return m


def punkt_bezier(p0, p1, p2, p3, t):
    """Punkt krzywej Béziera trzeciego stopnia: (1−t)³·P0 + 3(1−t)²t·P1 + 3(1−t)t²·P2 + t³·P3."""
    u = 1 - t
    return (u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
            u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1])


def sciezka_svg(d):
    """Polecenia ścieżki SVG (atrybut d) -> lista podścieżek [(punkty, czy_zamknieta)].
    Wielkie litery = współrzędne bezwzględne, małe = względem poprzedniego punktu.
    M przesuń, L linia, H poziomo, V pionowo, Z zamknij, C krzywa Béziera (przybliżamy 8 odcinkami),
    A łuk (przybliżamy prostą do końca łuku – w symbolach GUGiK łuki są tylko 4 i małe)."""
    tokeny = re.findall(r"[A-Za-z]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", d or "")
    ile_liczb = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7}
    podsciezki = []
    punkty = []
    x = 0.0
    y = 0.0
    start = (0.0, 0.0)
    polecenie = None
    i = 0
    while i < len(tokeny):
        if tokeny[i].isalpha():
            polecenie = tokeny[i]
            i += 1
            if polecenie in "Zz":
                if len(punkty) > 0:
                    podsciezki.append((punkty, True))
                punkty = []
                x, y = start
                continue
        if polecenie is None or polecenie.upper() not in ile_liczb:
            break
        n = ile_liczb[polecenie.upper()]
        if i + n > len(tokeny):
            break
        liczby = [float(t) for t in tokeny[i:i + n]]
        i += n
        wzgledne = polecenie.islower()
        p = polecenie.upper()
        if p == "M":
            if len(punkty) > 0:
                podsciezki.append((punkty, False))
            x = liczby[0] + (x if wzgledne else 0)
            y = liczby[1] + (y if wzgledne else 0)
            punkty = [(x, y)]
            start = (x, y)
            polecenie = "l" if wzgledne else "L"         # kolejne pary liczb po M to już linie
        elif p == "L" or p == "T":
            x = liczby[-2] + (x if wzgledne else 0)
            y = liczby[-1] + (y if wzgledne else 0)
            punkty.append((x, y))
        elif p == "H":
            x = liczby[0] + (x if wzgledne else 0)
            punkty.append((x, y))
        elif p == "V":
            y = liczby[0] + (y if wzgledne else 0)
            punkty.append((x, y))
        elif p == "C":
            dx = x if wzgledne else 0
            dy = y if wzgledne else 0
            p0 = (x, y)
            p1 = (liczby[0] + dx, liczby[1] + dy)
            p2 = (liczby[2] + dx, liczby[3] + dy)
            p3 = (liczby[4] + dx, liczby[5] + dy)
            for k in range(1, 9):
                punkty.append(punkt_bezier(p0, p1, p2, p3, k / 8))
            x, y = p3
        else:                                            # S, Q, A – prosta do punktu końcowego
            x = liczby[-2] + (x if wzgledne else 0)
            y = liczby[-1] + (y if wzgledne else 0)
            punkty.append((x, y))
            if p == "A":
                zapamietaj_brak("SVG łuk (A) przybliżony prostą")
    if len(punkty) > 0:
        podsciezki.append((punkty, False))
    return podsciezki


def podsciezki_elementu(element, nazwa):
    """Kształt elementu SVG jako lista podścieżek [(punkty, czy_zamknieta)]."""
    if nazwa == "path":
        return sciezka_svg(element.get("d"))
    if nazwa in ("polyline", "polygon"):
        liczby = [float(x) for x in re.findall(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", element.get("points", ""))]
        punkty = []
        for i in range(0, len(liczby) - 1, 2):
            punkty.append((liczby[i], liczby[i + 1]))
        return [(punkty, nazwa == "polygon")]
    if nazwa == "rect":
        x = float(element.get("x", "0"))
        y = float(element.get("y", "0"))
        w = float(element.get("width", "0"))
        h = float(element.get("height", "0"))
        return [([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], True)]
    if nazwa in ("circle", "ellipse"):
        cx = float(element.get("cx", "0"))
        cy = float(element.get("cy", "0"))
        rx = float(element.get("r", element.get("rx", "0")))
        ry = float(element.get("r", element.get("ry", "0")))
        punkty = []
        for k in range(24):                              # okrąg przybliżamy 24-kątem foremnym
            kat = 2 * math.pi * k / 24
            punkty.append((cx + rx * math.cos(kat), cy + ry * math.sin(kat)))
        return [(punkty, True)]
    if nazwa == "line":
        return [([(float(element.get("x1", "0")), float(element.get("y1", "0"))),
                  (float(element.get("x2", "0")), float(element.get("y2", "0")))], False)]
    return []


def zbierz_ksztalty(element, styl_rodzica, m_rodzica, ksztalty):
    """Przechodzi drzewo SVG (rekurencyjnie, jak foldery) i zbiera kształty z ich stylem i przekształceniem."""
    nazwa = element.tag.split("}")[-1]
    if nazwa in ("defs", "metadata", "namedview", "text", "title", "desc"):
        return
    styl = styl_elementu(element, styl_rodzica)
    if styl.get("display") == "none":
        return
    m = zloz(m_rodzica, przeksztalcenie(element.get("transform")))
    for podsciezki in [podsciezki_elementu(element, nazwa)]:
        if len(podsciezki) > 0:
            ksztalty.append((podsciezki, styl, m))
    for dziecko in element:
        zbierz_ksztalty(dziecko, styl, m, ksztalty)


def svg_na_ksztalty(tekst):
    """Cały symbol SVG -> {"proporcja": wysokość/szerokość, "ksztalty": [...]}.
    Każdy kształt: "wielokat" (do wypełnienia, podścieżki połączone mostkami), "linie" (kontury),
    kolory i grubość konturu. Współrzędne względem środka symbolu, podzielone przez szerokość."""
    korzen = ET.fromstring(tekst)
    if korzen.get("viewBox"):
        x0, y0, szer, wys = [float(v) for v in re.findall(r"[-+]?[\d.]+(?:[eE][-+]?\d+)?", korzen.get("viewBox"))]
    else:
        x0 = 0.0
        y0 = 0.0
        szer = float(re.sub(r"[^\d.]", "", korzen.get("width", "30")) or 30)
        wys = float(re.sub(r"[^\d.]", "", korzen.get("height", "30")) or 30)
    sx = x0 + szer / 2                                   # środek symbolu
    sy = y0 + wys / 2
    surowe = []
    zbierz_ksztalty(korzen, {"fill": "#000000", "stroke": "none", "stroke-width": "1"},
                    (1.0, 0.0, 0.0, 1.0, 0.0, 0.0), surowe)
    wynik = []
    for podsciezki, styl, m in surowe:
        wypelnienie = kolor_svg(styl.get("fill", "#000000"))
        if styl.get("fill-opacity", "1").strip() in ("0", "0.0"):
            wypelnienie = ""
        kontur = kolor_svg(styl.get("stroke", "none"))
        skala_m = math.sqrt(abs(m[0] * m[3] - m[1] * m[2]))   # o ile przekształcenie powiększa (do grubości)
        grubosc = float(re.sub(r"[^\d.eE+-]", "", styl.get("stroke-width", "1")) or 0) * skala_m / szer
        linie = []
        wielokat = []
        for punkty, zamknieta in podsciezki:
            plaska = []
            for px, py in punkty:
                tx = m[0] * px + m[2] * py + m[4]
                ty = m[1] * px + m[3] * py + m[5]
                plaska.append(round((tx - sx) / szer, 4))
                plaska.append(round((ty - sy) / szer, 4))
            if zamknieta and len(plaska) >= 4:
                plaska.append(plaska[0])
                plaska.append(plaska[1])
            linie.append(plaska)
            # wypełnienie: wszystkie podścieżki w jeden wielokąt; każdą następną doczepiamy "mostkiem"
            # do pierwszego punktu i wracamy – mostek idzie tam i z powrotem, więc przy regule
            # parzystości się znosi, a podścieżka w środku innej robi dziurę (np. w literze O)
            if len(wielokat) == 0:
                wielokat.extend(plaska)
            else:
                wielokat.extend(plaska)
                wielokat.append(wielokat[0])
                wielokat.append(wielokat[1])
        ksztalt = {"wypelnienie": wypelnienie, "kontur": kontur, "grubosc": round(grubosc, 4)}
        if wypelnienie != "" and len(wielokat) >= 6:
            ksztalt["wielokat"] = wielokat
        if kontur != "":
            ksztalt["linie"] = linie
        if "wielokat" in ksztalt or "linie" in ksztalt:
            wynik.append(ksztalt)
    return {"proporcja": round(wys / szer, 4), "ksztalty": wynik}


def kotwica(u):
    """Punkt zaczepienia znaczka: [poziomo, pionowo], 0 = lewa/górna krawędź, 1 = środek, 2 = prawa/dolna.
    Np. krzyż przydrożny ma [1, 2] – stoi podstawą na punkcie, zamiast być nim wyśrodkowany."""
    return [int(u.get("horizontal_anchor_point", "1")), int(u.get("vertical_anchor_point", "1"))]


def przetworz_znaczek(warstwa, pola):
    """Znaczek (marker): prosty kształt (SimpleMarker), symbol SVG (SvgMarker) albo znak czcionki."""
    rodzaj = warstwa.get("class")
    u = ustawienia_warstwy(warstwa)
    if rodzaj == "SimpleMarker":
        znaczek = {"rodzaj": "znaczek",
                   "ksztalt": u.get("name"),                 # line, circle, triangle
                   "rozmiar": na_mm(u.get("size", "2"), u.get("size_unit")),
                   "kolor": kolor_qgis(u.get("color", "0,0,0,255")),
                   "kontur": "",
                   "grubosc_konturu": na_mm(u.get("outline_width", "0"), u.get("outline_width_unit")),
                   "kat": float(u.get("angle", "0")),
                   "przesuniecie": para_na_mm(u.get("offset"), u.get("offset_unit")),
                   "kotwica": kotwica(u)}
        if u.get("outline_style") != "no":
            znaczek["kontur"] = kolor_qgis(u.get("outline_color", "0,0,0,255"))
        rozmiar = wlasciwosc_z_danych(warstwa, "size", pola, u.get("size_unit"))
        if rozmiar is not None:
            znaczek["rozmiar_z_pola"] = rozmiar
        return znaczek
    if rodzaj == "SvgMarker":
        nazwa = nazwa_svg(u.get("name", ""))
        if nazwa not in symbole_svg:                      # każdy symbol zamieniamy tylko raz
            tekst = tekst_svg(u.get("name", ""))
            if tekst is None:
                zapamietaj_brak("symbol SVG bez pliku")
            else:
                symbole_svg[nazwa] = svg_na_ksztalty(tekst)
        return {"rodzaj": "znaczek_svg",
                "svg": nazwa,
                "rozmiar": na_mm(u.get("size", "2"), u.get("size_unit")),
                "kolor": kolor_qgis(u.get("color", "0,0,0,255")),
                "kontur": kolor_qgis(u.get("outline_color", "0,0,0,255")),
                "kat": float(u.get("angle", "0")),
                "przesuniecie": para_na_mm(u.get("offset"), u.get("offset_unit")),
                "kotwica": kotwica(u)}
    zapamietaj_brak(f"znaczek {rodzaj}")
    return {"rodzaj": "nieobslugiwany", "klasa_qgis": rodzaj}


def przetworz_linie(warstwa, pola):
    """Linia (SimpleLine): kolor, grubość, przerywanie, przesunięcie w bok, końcówki."""
    u = ustawienia_warstwy(warstwa)
    linia = {"rodzaj": "linia",
             "kolor": kolor_qgis(u.get("line_color", "0,0,0,255")),
             "grubosc": na_mm(u.get("line_width", "0"), u.get("line_width_unit")),
             "kreski": None,
             "przesuniecie": na_mm(u.get("offset", "0"), u.get("offset_unit")),
             "koncowki": KONCOWKI.get(u.get("capstyle"), "round"),
             "narozniki": u.get("joinstyle", "round")}
    if u.get("line_style") == "no":
        linia["kolor"] = ""
    if u.get("use_custom_dash") == "1":
        linia["kreski"] = []
        for dlugosc in u.get("customdash", "1;1").split(";"):
            linia["kreski"].append(na_mm(dlugosc, u.get("customdash_unit")))
    grubosc = wlasciwosc_z_danych(warstwa, "outlineWidth", pola, u.get("line_width_unit"))
    if grubosc is not None:
        linia["grubosc_z_pola"] = grubosc
    przesuniecie = wlasciwosc_z_danych(warstwa, "offset", pola, u.get("offset_unit"))
    if przesuniecie is not None:
        linia["przesuniecie_z_pola"] = przesuniecie
    return linia


def pierwsza_warstwa(warstwa):
    """Pierwsza warstwa symbolu zagnieżdżonego w środku (np. znaczek w MarkerLine)."""
    return warstwa.find("symbol/layer")


def przetworz_warstwe(warstwa, pola):
    """Jedna warstwa symbolu z QML -> słownik do znaki.json."""
    rodzaj = warstwa.get("class")
    u = ustawienia_warstwy(warstwa)
    if rodzaj == "SimpleFill":
        w = {"rodzaj": "wypelnienie", "kolor": "", "kontur": "",
             "grubosc_konturu": na_mm(u.get("outline_width", "0"), u.get("outline_width_unit"))}
        if u.get("style") != "no":
            w["kolor"] = kolor_qgis(u.get("color", "0,0,0,255"))
        if u.get("outline_style") != "no":
            w["kontur"] = kolor_qgis(u.get("outline_color", "0,0,0,255"))
        return w
    if rodzaj == "SimpleLine":
        return przetworz_linie(warstwa, pola)
    if rodzaj == "MarkerLine":
        rozmieszczenie = {"interval": "co_odstep", "vertex": "w_wierzcholkach",
                          "firstvertex": "na_poczatku", "lastvertex": "na_koncu"}
        return {"rodzaj": "znaczki_na_linii",
                "rozmieszczenie": rozmieszczenie.get(u.get("placement"), u.get("placement")),
                "odstep": na_mm(u.get("interval", "0"), u.get("interval_unit")),
                "przesuniecie_wzdluz": na_mm(u.get("offset_along_line", "0"), u.get("offset_along_line_unit")),
                "obracaj": u.get("rotate", "1") == "1",
                "znaczek": przetworz_znaczek(pierwsza_warstwa(warstwa), pola)}
    if rodzaj in ("SimpleMarker", "SvgMarker", "FontMarker"):
        return przetworz_znaczek(warstwa, pola)
    if rodzaj == "CentroidFill":
        # point_on_surface = 1: znaczek w punkcie, który na pewno leży w poligonie (nie w środku ciężkości);
        # point_on_all_parts = 1: obiekt wieloczęściowy dostaje znaczek w każdej części
        return {"rodzaj": "znaczek_w_srodku",
                "na_powierzchni": u.get("point_on_surface", "0") == "1",
                "w_kazdej_czesci": u.get("point_on_all_parts", "1") == "1",
                "znaczek": przetworz_znaczek(pierwsza_warstwa(warstwa), pola)}
    if rodzaj == "PointPatternFill":
        return {"rodzaj": "wzor_z_punktow",
                "odstep_x": na_mm(u.get("distance_x", "10"), u.get("distance_x_unit")),
                "odstep_y": na_mm(u.get("distance_y", "10"), u.get("distance_y_unit")),
                "przesuniecie_rzedow_x": na_mm(u.get("displacement_x", "0"), u.get("displacement_x_unit")),
                "przesuniecie_rzedow_y": na_mm(u.get("displacement_y", "0"), u.get("displacement_y_unit")),
                "przesuniecie_x": na_mm(u.get("offset_x", "0"), u.get("offset_x_unit")),
                "przesuniecie_y": na_mm(u.get("offset_y", "0"), u.get("offset_y_unit")),
                "znaczek": przetworz_znaczek(pierwsza_warstwa(warstwa), pola)}
    if rodzaj == "LinePatternFill":
        # kąt kresek: w QGIS 3.x zapisany jako "angle" (stare projekty: "lineangle"), domyślnie 45°
        return {"rodzaj": "kreskowanie",
                "kat": float(u.get("lineangle", u.get("angle", "45"))),
                "odstep": na_mm(u.get("distance", "5"), u.get("distance_unit")),
                "przesuniecie": na_mm(u.get("offset", "0"), u.get("offset_unit")),
                "linia": przetworz_linie(pierwsza_warstwa(warstwa), pola)}
    zapamietaj_brak(f"warstwa {rodzaj}")
    return {"rodzaj": "nieobslugiwany", "klasa_qgis": rodzaj}


def nazwa_kategorii(etykieta):
    """"budynek mieszkalny jednorodzinny (w skali) - 0010_318_1 (42)" -> "budynek mieszkalny jednorodzinny (w skali)"."""
    return re.sub(r"\s*-?\s*0010_.*$", "", etykieta or "").strip()


def przetworz_filtr(tekst):
    """Filtr z layer_specs, np. "polozenie = 'na powierzchni gruntu'" albo kilka takich połączonych "or"
    -> {"pole": "polozenie", "wartosci": [...]}. Obiekt pasuje, gdy jego pole ma jedną z tych wartości."""
    if not tekst:
        return None
    pole = None
    wartosci = []
    for warunek in tekst.split(" or "):
        wynik = re.fullmatch(r"\s*\(?\s*(\w+)\s*=\s*'([^']*)'\s*\)?\s*", warunek)
        if wynik is None:
            zapamietaj_brak(f"filtr: {tekst}")
            return None
        if pole is not None and wynik.group(1) != pole:
            zapamietaj_brak(f"filtr: {tekst}")
            return None
        pole = wynik.group(1)
        wartosci.append(wynik.group(2))
    return {"pole": pole, "wartosci": wartosci}


def przetworz_styl(pozycja):
    """Jeden plik stylu (jedna warstwa mapy wtyczki) -> słownik do znaki.json albo None."""
    plik = pozycja["style"]
    sciezka = os.path.join(FOLDER_ZNAKOW, plik)
    if not os.path.exists(sciezka):
        print("  brak pliku stylu (pomijam):", plik)
        return None
    korzen = ET.parse(sciezka).getroot()

    # pola wirtualne, np. KOD10K = "kodKarto10k", SZERNAWIE = "szerokoscNawierzchni"
    pola = {}
    for pole in korzen.findall("expressionfields/field"):
        pola[pole.get("name")] = pole.get("expression").strip().strip('"')

    renderer = korzen.find("renderer-v2")
    if renderer.get("type") == "pointCluster":           # grupowanie punktów – bierzemy renderer ze środka
        renderer = renderer.find("renderer-v2")
    typ = renderer.get("type")
    if typ not in ("categorizedSymbol", "singleSymbol"):
        return None                                      # np. nullSymbol – styl z samymi napisami

    # poziomy symboli: jeśli są włączone, rysujemy przebiegami; jeśli nie – wszystko w przebiegu 0
    poziomy_symboli = renderer.get("symbollevels") == "1"
    symbole = {}
    przebiegi = []
    for symbol in renderer.findall("symbols/symbol"):
        warstwy = []
        for warstwa in symbol.findall("layer"):
            if warstwa.get("enabled") != "1":
                continue
            w = przetworz_warstwe(warstwa, pola)
            w["przebieg"] = 0
            if poziomy_symboli:
                w["przebieg"] = int(warstwa.get("pass", "0"))
            if w["przebieg"] not in przebiegi:
                przebiegi.append(w["przebieg"])
            warstwy.append(w)
        symbole[symbol.get("name")] = warstwy
    przebiegi.sort()

    znaki = {}
    if typ == "categorizedSymbol":
        pole_kodu = tlumacz_pole(renderer.get("attr"), pola)
        for kategoria in renderer.findall("categories/category"):
            if kategoria.get("render") == "true":
                znaki[kategoria.get("value")] = {"nazwa": nazwa_kategorii(kategoria.get("label")),
                                                 "warstwy": symbole[kategoria.get("symbol")]}
    else:
        pole_kodu = None                                 # jeden znak dla wszystkich obiektów klasy
        znaki["*"] = {"nazwa": "", "warstwy": symbole["0"]}

    # widoczność zależna od skali: warstwa znika, gdy mianownik skali jest większy niż min_skala
    min_skala = None
    if korzen.get("hasScaleBasedVisibilityFlag") == "1" and float(korzen.get("minScale", "0")) > 0:
        min_skala = float(korzen.get("minScale"))

    return {"klasa": pozycja["source"].replace("OT_", ""),
            "styl": plik,
            "pole": pole_kodu,
            "filtr": przetworz_filtr(pozycja.get("xml_filter_without_current")),
            "min_skala": min_skala,
            "przebiegi": przebiegi,
            "znaki": znaki}


def main():
    warstwy_wtyczki = wczytaj_liste_warstw()
    print("Warstw mapy we wtyczce:", len(warstwy_wtyczki))
    wynik = {"opis": "Znaki umowne BDOT10k zbliżone do mapy topograficznej 1:10 000, odczytane ze stylów QML "
                     "wtyczki GUGiK BDOT10k_GML_SHP 2.1.1 (licencja GPL-3.0) skryptem qml_na_json.py. "
                     "Wielkości w milimetrach mapy w skali 1:10 000. Warstwy od spodu do wierzchu.",
             "skala_odniesienia": SKALA_ODNIESIENIA,
             "warstwy": [],
             "svg": symbole_svg}
    znakow = 0
    for pozycja in warstwy_wtyczki:
        styl = przetworz_styl(pozycja)
        if styl is not None:
            wynik["warstwy"].append(styl)
            znakow += len(styl["znaki"])
    with open(PLIK_WYNIKOWY, "w", encoding="utf-8") as plik:
        json.dump(wynik, plik, ensure_ascii=False, indent=1)
    print(f"Zapisano {PLIK_WYNIKOWY}: {len(wynik['warstwy'])} warstw, {znakow} znaków, {len(symbole_svg)} symboli SVG")
    print("Czego nie zamieniamy (zostaje uproszczone):")
    for opis in sorted(nieobslugiwane):
        print(f"  {nieobslugiwane[opis]:4} × {opis}")


if __name__ == "__main__":
    main()
