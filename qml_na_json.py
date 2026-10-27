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
import json
import os
import re
import xml.etree.ElementTree as ET

FOLDER_ZNAKOW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "znaki")
PLIK_WARSTW = os.path.join(FOLDER_ZNAKOW, "layer_specs.py")
PLIK_WYNIKOWY = os.path.join(FOLDER_ZNAKOW, "znaki.json")
SKALA_ODNIESIENIA = 10000

KONCOWKI = {"flat": "butt", "round": "round", "square": "projecting"}   # nazwy z QGIS -> nazwy z tkintera

# tu zbieramy, czego nie umiemy zamienić – wypiszemy to na końcu
nieobslugiwane = {}


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


def nazwa_svg(tekst):
    """Nazwa symbolu SVG: plik wskazany ścieżką albo SVG wpisany w styl (base64:...), z którego
    bierzemy nazwę z atrybutu sodipodi:docname, np. "0010_330.svg" -> "0010_330"."""
    if tekst.startswith("base64:"):
        svg = base64.b64decode(tekst[7:]).decode("utf-8", "replace")
        wynik = re.search(r'docname="([^"]+)"', svg)
        if wynik is None:
            return "bez_nazwy"
        nazwa = wynik.group(1)
    else:
        nazwa = tekst.replace("\\", "/").split("/")[-1]
    return nazwa.replace(".svg", "").strip()


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
                   "przesuniecie": para_na_mm(u.get("offset"), u.get("offset_unit"))}
        if u.get("outline_style") != "no":
            znaczek["kontur"] = kolor_qgis(u.get("outline_color", "0,0,0,255"))
        rozmiar = wlasciwosc_z_danych(warstwa, "size", pola, u.get("size_unit"))
        if rozmiar is not None:
            znaczek["rozmiar_z_pola"] = rozmiar
        return znaczek
    if rodzaj == "SvgMarker":
        return {"rodzaj": "znaczek_svg",
                "svg": nazwa_svg(u.get("name", "")),
                "rozmiar": na_mm(u.get("size", "2"), u.get("size_unit")),
                "kolor": kolor_qgis(u.get("color", "0,0,0,255")),
                "kontur": kolor_qgis(u.get("outline_color", "0,0,0,255")),
                "kat": float(u.get("angle", "0")),
                "przesuniecie": para_na_mm(u.get("offset"), u.get("offset_unit"))}
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
        return {"rodzaj": "znaczek_w_srodku",
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
        return {"rodzaj": "kreskowanie",
                "kat": float(u.get("lineangle", "45")),
                "odstep": na_mm(u.get("distance", "5"), u.get("distance_unit")),
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
             "warstwy": []}
    znakow = 0
    for pozycja in warstwy_wtyczki:
        styl = przetworz_styl(pozycja)
        if styl is not None:
            wynik["warstwy"].append(styl)
            znakow += len(styl["znaki"])
    with open(PLIK_WYNIKOWY, "w", encoding="utf-8") as plik:
        json.dump(wynik, plik, ensure_ascii=False, indent=1)
    print(f"Zapisano {PLIK_WYNIKOWY}: {len(wynik['warstwy'])} warstw, {znakow} znaków")
    print("Czego nie zamieniamy (zostaje uproszczone):")
    for opis in sorted(nieobslugiwane):
        print(f"  {nieobslugiwane[opis]:4} × {opis}")


if __name__ == "__main__":
    main()
