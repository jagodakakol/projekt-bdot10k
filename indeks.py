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

ROZMIAR_KOMORKI = 500     # metrów


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
    return siatka


def kandydaci(siatka, prostokat):
    """Obiekty z komórek, które przecina prostokąt (x_min, y_min, x_max, y_max), bez powtórzeń.
    To tylko kandydaci: obiekt może leżeć w tej samej komórce, a mimo to nie nachodzić na prostokąt –
    to sprawdzamy potem testem prostokątów."""
    k1, w1 = numer_komorki(siatka, prostokat[0], prostokat[1])
    k2, w2 = numer_komorki(siatka, prostokat[2], prostokat[3])
    if (k2 - k1 + 1) * (w2 - w1 + 1) >= len(siatka["komorki"]):
        return siatka["obiekty"]       # prostokąt obejmuje (prawie) cały obszar – szybciej wziąć wszystko
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
