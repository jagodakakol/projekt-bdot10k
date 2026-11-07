# indeks.py – indeks przestrzenny: siatka regularna (własna implementacja)
# Projekt z Geometrii obliczeniowej, dr hab. inż. Waldemar Izdebski
#
# Obszar powiatu dzielimy na kwadratowe komórki ROZMIAR_KOMORKI × ROZMIAR_KOMORKI metrów.
# Każdy obiekt zapisujemy w każdej komórce, na którą nachodzi jego prostokąt otaczający.
# Gdy trzeba narysować fragment mapy, sprawdzamy tylko obiekty z komórek przeciętych przez ten
# fragment, zamiast wszystkich obiektów powiatu (w powiecie otwockim to prawie 167 tys.).
#
# Dlaczego siatka: jest najprostsza do zbudowania i do wyjaśnienia, a dla powiatu wystarcza.
# Jej słabość to nierówna gęstość danych (miasto – wieś): w mieście komórka ma dużo obiektów.
# Rozmiar 500 m dobrany pomiarem na powiecie otwockim (250, 500, 1000 i 2000 m – opis w notatkach).
#
# Planowanie zapytania: gdy widok jest duży (np. 1:50 000 – widać 40% obiektów powiatu), zbieranie kandydatów
# z setek komórek (i pomijanie powtórzeń) trwa dłużej niż przejrzenie wszystkich obiektów po kolei.
# Dlatego najpierw liczymy, ile wpisów jest w przeciętych komórkach – w stałym czasie, z tablicy sum
# prefiksowych – i gdy to więcej niż 1/3 obiektów klasy, bierzemy po prostu wszystkie obiekty.

from array import array

ROZMIAR_KOMORKI = 500     # metrów
PROG_PLANOWANIA = 1 / 3   # powyżej takiej części obiektów klasy szybciej przejrzeć wszystkie (z pomiaru)


def numer_komorki(siatka, x, y):
    """Komórka, w której leży punkt (x, y): numer kolumny i wiersza liczony od lewego dolnego rogu siatki.
    // to dzielenie z zaokrągleniem w dół. Punkty spoza siatki "przyklejamy" do jej brzegu."""
    kolumna = int((x - siatka["x0"]) // siatka["rozmiar"])
    wiersz = int((y - siatka["y0"]) // siatka["rozmiar"])
    kolumna = min(max(kolumna, 0), siatka["kolumny"] - 1)
    wiersz = min(max(wiersz, 0), siatka["wiersze"] - 1)
    return kolumna, wiersz


def zbuduj_siatke(obiekty, zasieg, rozmiar=ROZMIAR_KOMORKI):
    """Buduje siatkę dla listy obiektów. Komórki trzymamy w słowniku (kolumna, wiersz) -> lista obiektów,
    więc puste komórki nie zajmują pamięci."""
    siatka = {"rozmiar": rozmiar,
              "x0": zasieg[0],
              "y0": zasieg[1],
              "kolumny": int((zasieg[2] - zasieg[0]) // rozmiar) + 1,
              "wiersze": int((zasieg[3] - zasieg[1]) // rozmiar) + 1,
              "komorki": {},
              "obiekty": obiekty}
    for obiekt in obiekty:
        p = obiekt["prostokat"]
        k1, w1 = numer_komorki(siatka, p[0], p[1])       # komórka lewego dolnego rogu prostokąta
        k2, w2 = numer_komorki(siatka, p[2], p[3])       # komórka prawego górnego rogu
        for k in range(k1, k2 + 1):                      # wszystkie komórki pomiędzy nimi
            for w in range(w1, w2 + 1):
                if (k, w) not in siatka["komorki"]:
                    siatka["komorki"][(k, w)] = []
                siatka["komorki"][(k, w)].append(obiekt)
    siatka["sumy"] = sumy_prefiksowe(siatka)
    return siatka


def sumy_prefiksowe(siatka):
    """Tablica sum prefiksowych liczby wpisów (summed-area table): S[k][w] = ile wpisów jest we wszystkich
    komórkach o numerze kolumny < k i wiersza < w. Liczymy ją raz, wzorem
        S[k+1][w+1] = wpisy(k, w) + S[k][w+1] + S[k+1][w] − S[k][w]
    (prostokąt na lewo + prostokąt pod spodem − ich część wspólna policzona dwa razy).
    Tablicę dwuwymiarową trzymamy jako jedną płaską tablicę liczb: element [k][w] ma numer k·(wiersze+1) + w.
    array("q") to tablica 8-bajtowych liczb całkowitych – zajmuje dużo mniej pamięci niż zwykła lista."""
    kolumny = siatka["kolumny"]
    wiersze_1 = siatka["wiersze"] + 1
    sumy = array("q", [0]) * ((kolumny + 1) * wiersze_1)
    for k in range(kolumny):
        for w in range(siatka["wiersze"]):
            lista = siatka["komorki"].get((k, w))
            if lista is None:
                ile = 0
            else:
                ile = len(lista)
            sumy[(k + 1) * wiersze_1 + w + 1] = (ile + sumy[k * wiersze_1 + w + 1]
                                                 + sumy[(k + 1) * wiersze_1 + w] - sumy[k * wiersze_1 + w])
    return sumy


def ile_wpisow(siatka, k1, w1, k2, w2):
    """Liczba wpisów w komórkach od (k1, w1) do (k2, w2) włącznie – zawsze z 4 liczb, bez względu na to,
    ile komórek obejmuje prostokąt: cały prostokąt od początku siatki do (k2, w2), minus pas z lewej,
    minus pas z dołu, plus lewy dolny róg (odjęty dwa razy)."""
    s = siatka["sumy"]
    w_1 = siatka["wiersze"] + 1
    return (s[(k2 + 1) * w_1 + w2 + 1] - s[k1 * w_1 + w2 + 1]
            - s[(k2 + 1) * w_1 + w1] + s[k1 * w_1 + w1])


def kandydaci(siatka, prostokat):
    """Obiekty z komórek, które przecina prostokąt (x_min, y_min, x_max, y_max), bez powtórzeń.
    To tylko kandydaci: obiekt może leżeć w tej samej komórce, a mimo to nie nachodzić na prostokąt –
    to sprawdzamy potem testem prostokątów."""
    k1, w1 = numer_komorki(siatka, prostokat[0], prostokat[1])
    k2, w2 = numer_komorki(siatka, prostokat[2], prostokat[3])
    if ile_wpisow(siatka, k1, w1, k2, w2) >= PROG_PLANOWANIA * len(siatka["obiekty"]):
        return siatka["obiekty"]       # duży widok (albo cały powiat) – szybciej przejrzeć wszystkie obiekty
    wynik = []
    widziane = set()                   # obiekt leżący w kilku komórkach bierzemy tylko raz
    for k in range(k1, k2 + 1):
        for w in range(w1, w2 + 1):
            lista = siatka["komorki"].get((k, w))
            if lista is None:
                continue               # pusta komórka
            for obiekt in lista:
                if id(obiekt) not in widziane:    # id() = numer obiektu w pamięci, inny dla każdego obiektu
                    widziane.add(id(obiekt))
                    wynik.append(obiekt)
    return wynik


def najgestsze_miejsce(indeks):
    """Środek komórki siatki, w której jest najwięcej obiektów (wszystkich klas razem) – np. centrum miasta.
    Tam pomiar czasu rysowania jest najbardziej wymagający."""
    wpisy = {}
    siatka = None
    for klasa in indeks:
        siatka = indeks[klasa]
        for komorka, lista in siatka["komorki"].items():
            wpisy[komorka] = wpisy.get(komorka, 0) + len(lista)
    k, w = max(wpisy, key=wpisy.get)               # komórka z największą liczbą wpisów
    return (siatka["x0"] + (k + 0.5) * siatka["rozmiar"], siatka["y0"] + (w + 0.5) * siatka["rozmiar"])


def zbuduj_indeks(dane, zasieg):
    """Osobna siatka dla każdej klasy, bo mapę rysujemy klasa po klasie. Zwraca {klasa: siatka}."""
    indeks = {}
    for klasa in dane:
        indeks[klasa] = zbuduj_siatke(dane[klasa], zasieg)
    return indeks


def opis_indeksu(indeks):
    """Krótki opis: ile komórek i ile wpisów (obiekt w kilku komórkach liczy się kilka razy)."""
    komorki = 0
    wpisy = 0
    for klasa in indeks:
        komorki += len(indeks[klasa]["komorki"])
        for lista in indeks[klasa]["komorki"].values():
            wpisy += len(lista)
    return f"siatka {ROZMIAR_KOMORKI} m: {komorki:,} niepustych komórek, {wpisy:,} wpisów".replace(",", " ")
