# projekt-bdot10k – przeglądarka danych BDOT10k

Projekt z przedmiotu **Geometria obliczeniowa** (dr hab. inż. Waldemar Izdebski), autorka: Jagoda Kakol.

Program wczytuje cały powiat z bazy BDOT10k (pliki GML z Geoportalu, folder albo ZIP) i rysuje go jako mapę:
prostymi kolorami albo znakami umownymi GUGiK. Mapę można przybliżać kółkiem myszy, przesuwać, kliknięciem
sprawdzić atrybuty obiektu, a w panelu warstw włączać i wyłączać klasy oraz zmieniać ich kolor i grubość.
Wszystko jest napisane od zera w Pythonie, bez bibliotek GIS: własny parser GML, własna struktura danych,
własny indeks przestrzenny i własne algorytmy geometryczne.

## Uruchomienie

- Python 3.12–3.14, tylko biblioteka standardowa (okno: `tkinter`). Nic nie trzeba instalować.
- Dane: z Geoportalu pobrać BDOT10k dla powiatu w formacie GML (plik ZIP) i rozpakować do folderu `dane/`
  (folder jest w `.gitignore` – dane są za duże na GitHuba).
- `python mapa.py` – program zapyta o folder z danymi; można też podać ścieżkę: `python mapa.py dane/1417_GML`
  (folder albo plik ZIP).
- Plik ze znakami umownymi `znaki/znaki.json` jest w repozytorium; żeby zrobić go od nowa: `python qml_na_json.py`.

| Plik | Co robi |
|---|---|
| `gml.py` | wczytywanie plików GML powiatu (strumieniowo), zamiana na obiekty |
| `indeks.py` | indeks przestrzenny – siatka regularna z planowaniem zapytania |
| `geometria.py` | algorytmy geometrii obliczeniowej (lista niżej) |
| `qml_na_json.py` | zamiana stylów QGIS wtyczki GUGiK (`.qml`) na nasz czytelny plik `znaki/znaki.json` |
| `mapa.py` | okno programu: rysowanie, nawigacja, panel warstw, identyfikacja, pomiar czasu |
| `pomiary.txt` | wyniki przycisku „Pomiar czasu” (kolejne pomiary są dopisywane na końcu) |

## Wczytywanie danych (`gml.py`)

- Pliki są duże (same budynki powiatu otwockiego to 96 MB), więc czytamy je **strumieniowo** (`xml.etree.ElementTree.iterparse`):
  obiekt po obiekcie, a przeczytany fragment XML od razu usuwamy z pamięci (`korzen.clear()`).
- Współrzędne trzymamy w płaskich tablicach liczb `array('d')`: `[x1, y1, x2, y2, …]` – kilka razy mniej pamięci niż lista par.
  W tych plikach PUWG 1992 (EPSG:2180) najpierw jest współrzędna wschodnia, potem północna (ustawienie `NAJPIERW_WSCHODNIA`).
- Powtarzające się napisy atrybutów (np. „eksploatowany” w 60 tys. budynków) trzymamy raz (`sys.intern`).
- Prostokąt otaczający obiektu i zasięg całych danych liczymy w tym samym przejściu.
- Pomijamy obiekty archiwalne (z wypełnionym `koniecWersjiObiektu`).
- Powiat otwocki (1417): 66 klas, 166 908 obiektów, ok. 2 mln par współrzędnych; wczytanie ok. 13–16 s, ok. 260 MB pamięci.
- Warszawa (1465): 70 klas, 535 790 obiektów; wczytanie prosto z pliku ZIP (89 MB) 59,6 s, ok. 1,1 GB pamięci.
  Czas i pamięć rosną liniowo z liczbą obiektów (ok. 9–11 tys. obiektów na sekundę, ok. 1,5–2 KB pamięci na obiekt).

## Struktura danych

```
dane = { "BUBD_A": [obiekt, obiekt, …], "SKDR_L": […], … }      # klasa BDOT10k -> lista obiektów

obiekt = { "klasa": "BUBD_A",
           "typ": "poligon",                                    # "poligon" | "linia" | "punkt"
           "czesci": [[obwód, dziura1, …], …],                  # pierścienie: array('d') [x1, y1, x2, y2, …]
           "atrybuty": {"kodKarto10k": "0010_320_1", "funkcjaOgolnaBudynku": "…", …},
           "prostokat": (x_min, y_min, x_max, y_max),
           "sciezki": […] }                                     # obwód z dziurami jako jedna ścieżka do rysowania
```

Słownik według klas, bo mapę rysujemy klasa po klasie (w ustalonej kolejności), a panel warstw włącza całe klasy.
Prostokąt otaczający jest liczony raz przy wczytaniu – na nim działają indeks i szybki test „czy obiekt jest w oknie”.

## Indeks przestrzenny (`indeks.py`)

**Metoda: siatka regularna**, osobna dla każdej klasy. Obszar powiatu dzielimy na kwadraty 500 × 500 m.
Obiekt zapisujemy w każdej komórce, na którą nachodzi jego prostokąt otaczający (słownik `(kolumna, wiersz) -> lista obiektów`,
puste komórki nie zajmują pamięci). Powiat otwocki: 47 276 niepustych komórek, 265 005 wpisów (średnio 1,6 komórki na obiekt).

Zapytanie „co narysować w oknie”:
1. Z rogów okna liczymy zakres komórek: `kolumna = (x − x0) // 500` – w stałym czasie, bez przeszukiwania.
2. **Planowanie zapytania:** z tablicy sum prefiksowych liczymy (z 4 liczb, bez względu na wielkość okna), ile wpisów jest
   w tych komórkach: `S[k2+1][w2+1] − S[k1][w2+1] − S[k2+1][w1] + S[k1][w1]`. Jeśli to ponad 1/3 obiektów klasy,
   szybciej przejrzeć całą listę klasy (tak jest przy całym powiecie i w 1:50 000).
3. W przeciwnym razie zbieramy obiekty z tych komórek, każdy tylko raz (zbiór `id()` obiektów).
4. Kandydatów sprawdzamy testem prostokątów otaczających; rysujemy tylko te, które nachodzą na okno.

Ten sam indeks służy do identyfikacji obiektu kliknięciem (okno = kwadrat kilku pikseli wokół kursora).

**Dlaczego siatka:**
- jest najprostsza do zbudowania (jedno przejście po obiektach) i do wyjaśnienia, a komórkę punktu liczymy jednym dzieleniem;
- w powiecie gęstość danych jest w miarę równomierna, a obiekty są małe w porównaniu z komórką, więc większość leży w jednej komórce;
- drzewo czwórkowe albo R-drzewo lepiej znoszą bardzo nierówną gęstość (centrum miasta – las), ale są dużo bardziej złożone;
  dla powiatu siatka wystarcza – w centrum Otwocka w skali 1:2 000 wybór obiektów trwa 0,002 s (pomiary niżej).

**Rozmiar komórki** dobrany pomiarem (powiat otwocki, etap B1):

| Komórka | Budowa | Wpisy | Kandydaci – wieś w oknie | Kandydaci – mały widok |
|---|---|---|---|---|
| 250 m | 0,77 s | 461 779 | 1 869 | 243 |
| **500 m** | **0,26 s** | **265 005** | **2 451** | **336** |
| 1000 m | 0,16 s | 203 353 | 2 451 | 426 |
| 2000 m | 0,15 s | 182 121 | 3 531 | 1 674 |

500 m to kompromis: niewiele więcej kandydatów niż przy 250 m, a prawie dwa razy mniej wpisów i trzy razy szybsza budowa.

## Pomiar czasu z indeksem i bez

Przycisk **„Pomiar czasu”** rysuje te same widoki z indeksem i bez: cały powiat oraz 1:50 000, 1:10 000 i 1:2 000 wokół
środka bieżącego widoku (zaraz po wczytaniu – wokół najgęstszego miejsca powiatu). Każdy wariant 3 razy, po rozgrzewce,
na zmianę z indeksem i bez; liczy się najkrótszy czas. W trakcie pomiaru program blokuje kliknięcia, żeby nic nie zmieniło widoku.

Wyniki: laptop, Windows 11, Python 3.14.0, okno zmaksymalizowane (mapa 903 × 657 px), powiat otwocki,
najgęstsze miejsce: centrum Otwocka (X = 473 554, Y = 654 842). „Sprawdzono” = ile prostokątów porównano z oknem,
„wybór” = czas wyboru obiektów, „całość” = czas całego rysowania (wybór + rysowanie).

**Proste kolory** (6 listopada 2026)

| Widok | Z indeksem: sprawdzono | wybór [s] | całość [s] | Bez indeksu: sprawdzono | wybór [s] | całość [s] | Wybór szybciej |
|---|---:|---:|---:|---:|---:|---:|---:|
| cały powiat (1:229 055) | 166 908 | 0,085 | 2,095 | 166 908 | 0,071 | 2,106 | 1× |
| 1:50 000 | 137 958 | 0,065 | 0,934 | 166 908 | 0,074 | 0,913 | 1× |
| 1:10 000 | 8 972 | 0,017 | 0,314 | 166 908 | 0,068 | 0,349 | 4× |
| 1:2 000 | 749 | 0,002 | 0,140 | 166 908 | 0,070 | 0,207 | 33× |

**Znaki umowne GUGiK** (6 listopada 2026)

| Widok | Z indeksem: sprawdzono | wybór [s] | całość [s] | Bez indeksu: sprawdzono | wybór [s] | całość [s] | Wybór szybciej |
|---|---:|---:|---:|---:|---:|---:|---:|
| cały powiat (1:229 055) | 130 183 | 0,062 | 1,489 | 130 183 | 0,061 | 1,489 | 1× |
| 1:50 000 | 124 729 | 0,058 | 1,521 | 130 338 | 0,058 | 1,508 | 1× |
| 1:10 000 | 8 611 | 0,016 | 0,367 | 165 735 | 0,069 | 0,448 | 4× |
| 1:2 000 | 737 | 0,002 | 0,127 | 165 735 | 0,069 | 0,197 | 30× |

Ze znakami bez indeksu „sprawdzono” zależy od skali, bo część klas ma w stylu zakres skal (np. budowle znikają od 1:25 001).

### Duży powiat: Warszawa (1465)

Ten sam laptop i to samo okno, 7 listopada 2026; 535 790 obiektów (3,2× więcej niż powiat otwocki), dane wczytane prosto z ZIP.
Indeks: 55 740 niepustych komórek, 697 240 wpisów, budowa razem z tablicami sum prefiksowych 1,8 s.
Widoki wokół centrum Warszawy (X = 487 201, Y = 640 883).

**Proste kolory**

| Widok | Z indeksem: sprawdzono | wybór [s] | całość [s] | Bez indeksu: sprawdzono | wybór [s] | całość [s] | Wybór szybciej |
|---|---:|---:|---:|---:|---:|---:|---:|
| cały powiat (1:172 083) | 535 790 | 0,166 | 5,016 | 535 790 | 0,182 | 5,520 | 1× |
| 1:50 000 | 254 543 | 0,163 | 2,442 | 535 790 | 0,156 | 2,352 | 1× |
| 1:10 000 | 10 206 | 0,013 | 0,463 | 535 790 | 0,163 | 0,685 | 12× |
| 1:2 000 | 2 028 | 0,003 | 0,346 | 535 790 | 0,157 | 0,540 | 56× |

**Znaki umowne GUGiK**

| Widok | Z indeksem: sprawdzono | wybór [s] | całość [s] | Bez indeksu: sprawdzono | wybór [s] | całość [s] | Wybór szybciej |
|---|---:|---:|---:|---:|---:|---:|---:|
| cały powiat (1:172 083) | 327 377 | 0,113 | 2,884 | 327 377 | 0,114 | 3,267 | 1× |
| 1:50 000 | 111 960 | 0,108 | 1,762 | 332 563 | 0,106 | 1,718 | 1× |
| 1:10 000 | 9 928 | 0,015 | 0,552 | 532 412 | 0,150 | 0,645 | 10× |
| 1:2 000 | 2 006 | 0,003 | 0,096 | 532 412 | 0,145 | 0,243 | 54× |

**Wnioski:**
- Bez indeksu wybór zawsze kosztuje tyle samo (ok. 0,07 s – przegląd wszystkich obiektów), z indeksem jest tym tańszy, im mniejsze okno:
  w 1:2 000 ok. 30× szybszy, a całe rysowanie krótsze o ok. 1/3 (0,140 s zamiast 0,207 s).
- Przy całym powiecie i w 1:50 000 widać dużą część obiektów, więc indeks nic nie daje – planowanie zapytania sprawia, że też nic nie psuje
  (bez niego w 1:50 000 indeks był ok. 2× wolniejszy od przeglądu wszystkich obiektów).
- Przy dużych widokach czas zajmuje samo rysowanie w `tkinter` (dziesiątki tysięcy elementów), a nie wybór obiektów.
- Zysk z indeksu rośnie z wielkością danych: przegląd bez indeksu jest proporcjonalny do liczby wszystkich obiektów powiatu,
  a z indeksem – do liczby obiektów w pobliżu okna. Potwierdza to Warszawa: bez indeksu wybór w 1:2 000 trwa 0,157 s
  (w powiecie otwockim 0,070 s), a z indeksem nadal 0,003 s – zysk 56× zamiast 33×, a ze znakami całe rysowanie
  jest 2,5× krótsze (0,096 s zamiast 0,243 s).

## Algorytmy geometryczne (`geometria.py`)

| Funkcja | Do czego | Idea |
|---|---|---|
| `odleglosc_od_odcinka` | identyfikacja linii kliknięciem | rzut punktu na odcinek: t = AP·AB / \|AB\|², obcięte do [0, 1] |
| `punkt_w_wielokacie` | identyfikacja poligonu kliknięciem | półprosta w prawo, reguła parzystości przecięć (dziury same wypadają) |
| `punkty_co_odstep` | znaczki wzdłuż linii (ząbki, strzałki) | marsz po łamanej, reszta odległości przechodzi na następny odcinek |
| `przesun_lamana` | linia równoległa (np. pas wzdłuż granicy) | wierzchołek przesunięty wzdłuż dwusiecznej o d / cos(α/2) (miter) |
| `odcinki_wewnatrz` | wypełnienia wzorem, kreskowanie | przecięcia poziomej prostej z brzegami, posortowane i połączone w pary |
| `punkty_wzoru` | drzewka w lesie, krzyżyki na cmentarzu | siatka punktów, ale dla każdego wiersza raz `odcinki_wewnatrz` zamiast testu każdego punktu |
| `odcinki_kreskowania` | bagna, tereny podmokłe | obrót wielokąta o kąt kresek, cięcie poziomymi prostymi, obrót z powrotem |
| `srodek_ciezkosci` | znak w środku obszaru | wzory Gaussa (shoelace), dziury odejmowane z wagą pola |
| `punkt_na_powierzchni` | znak, który musi leżeć w obszarze | środek najdłuższego odcinka poziomej prostej w połowie wysokości (jak GEOS) |

## Znaki umowne (`qml_na_json.py` → `znaki/znaki.json`)

- Źródło: style QGIS wtyczki GUGiK „BDOT10k_GML_SHP” 2.1.1 (licencja GPL-3.0, szczegóły w `znaki/ZRODLO.txt`).
- `qml_na_json.py` czyta 96 stylów `.qml` (XML) i listę warstw wtyczki i zapisuje **nasz czytelny plik JSON**:
  dla każdej warstwy – klasa, pole atrybutu, wartości → znak (wypełnienie, linie, znaczki, wzory). Program mapy czyta tylko JSON.
  Wynik: 70 warstw, 248 znaków, 58 symboli SVG.
- Wielkości są w **milimetrach mapy w skali 1:10 000**; na ekranie: piksele = mm × (pikseli na metr ekranu × 10 000 / mianownik skali),
  więc znaki rosną przy przybliżaniu jak na mapie topograficznej.
- Grubości zależne od atrybutu (np. szerokość jezdni): wyrażenia liniowe a·x + b wyznaczamy, licząc wyrażenie dla x = 0, 1 i 2.
- Kolejność rysowania jak na mapie topograficznej: kolejność warstw wtyczki (tereny, wody, drogi, budynki, znaki) i poziomy symboli.
- Symbole SVG zamieniamy na wielokąty i linie (własny odczyt ścieżek, krzywe Béziera próbkowane w 8 punktach); przy rysowaniu
  skala, obrót (np. wzdłuż linii) i punkt zaczepienia ze stylu.
- Widoczność zależna od skali jak w QGIS: warstwa widoczna, gdy max_skala ≤ mianownik < min_skala; w panelu warstw klasy
  nierysowane w danej skali są szare.
- `tkinter` rysuje całymi pikselami i bez wygładzania, dlatego w jednym znaku szersza linia pod spodem (obwódka jezdni) jest zawsze
  o co najmniej 2 px szersza od węższej na wierzchu.

**Uproszczenia:** nie rysujemy napisów ze stylów (poza nazwami miejscowości), 21 złożonych wyrażeń (if/CASE) dostaje stałą
wartość, łuki w 8 symbolach SVG są przybliżone odcinkami, a obiekty BDOT10k nie mają atrybutu kąta – znaki obracają się tam,
gdzie każe styl, czyli wzdłuż linii.

## Źródła

- Dane: BDOT10k, Geoportal (GUGiK), format GML.
- Znaki umowne: wtyczka GUGiK BDOT10k_GML_SHP, https://github.com/GlownyUrzadGeodezjiIKartografii/BDOT10k_GML_SHP (GPL-3.0).
- Nazwy klas: „Vademecum użytkownika BDOT10k”, WODGiK Zielona Góra, 2024.
- Materiały do przedmiotu: izdebski.edu.pl.
