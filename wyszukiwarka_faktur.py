import json
import os
import xml.etree.ElementTree as ET
from typing import Any

import zarzadca_ustawien as zu

PLIK_INDEKSU = "indeks_faktur.json"


def znajdz_wartosc(element, nazwa_pola: str, domyslna: str = "") -> str:
    """Wyszukuje pierwszy element o danej nazwie końcowej (ignorując namespace)."""
    if element is None:
        return domyslna
    znaleziony = element.find(f".//{{*}}{nazwa_pola}")
    if znaleziony is not None and znaleziony.text:
        return znaleziony.text.strip()
    return domyslna


def parsuj_fakture_xml(sciezka_xml: str, typ_rejestru: str = "zakup") -> dict[str, Any] | None:
    """Odczytuje kluczowe metadane faktury z lokalnego pliku XML KSeF."""
    try:
        drzewo = ET.parse(sciezka_xml)
        root = drzewo.getroot()
    except (ET.ParseError, OSError):
        return None

    nr_ksef = os.path.splitext(os.path.basename(sciezka_xml))[0]
    fa_wezel = root.find(".//{*}Fa")
    nr_faktury = znajdz_wartosc(fa_wezel, "P_2", nr_ksef)

    # 1. Data wystawienia
    data_wystawienia = znajdz_wartosc(fa_wezel, "P_1")

    # 2. Data sprzedaży / wykonania usługi
    data_sprzedazy = znajdz_wartosc(fa_wezel, "P_6")
    if not data_sprzedazy:
        data_sprzedazy = znajdz_wartosc(fa_wezel, "P_6_Do")
    if not data_sprzedazy:
        data_sprzedazy = znajdz_wartosc(root.find(".//{*}FaWiersz"), "P_6A")
    if not data_sprzedazy:
        data_sprzedazy = data_wystawienia

    # 3. Kontrahent: dla zakupu kontrahentem jest Sprzedawca (Podmiot1), dla sprzedaży Nabywca (Podmiot2)
    wezel_kontrahenta = root.find(".//{*}Podmiot1") if typ_rejestru == "zakup" else root.find(".//{*}Podmiot2")
    nip_kontrahenta = znajdz_wartosc(wezel_kontrahenta, "NIP")
    nazwa_kontrahenta = znajdz_wartosc(wezel_kontrahenta, "Nazwa")

    # 4. Kwoty finansowe
    def konwertuj_kwote(tekst: str) -> float:
        try:
            return float(tekst.replace(",", "."))
        except (ValueError, AttributeError):
            return 0.0

    brutto = konwertuj_kwote(znajdz_wartosc(fa_wezel, "P_15", "0.0"))
    netto = konwertuj_kwote(znajdz_wartosc(fa_wezel, "P_13_1", "0.0"))
    vat = konwertuj_kwote(znajdz_wartosc(fa_wezel, "P_14_1", "0.0"))

    sciezka_pdf = sciezka_xml.replace("_xml", "_pdf").replace(".xml", ".pdf")

    return {
        "nr_ksef": nr_ksef,
        "nr_faktury": nr_faktury,
        "typ_rejestru": typ_rejestru,
        "data_sprzedazy": data_sprzedazy,
        "data_wystawienia": data_wystawienia,
        "kontrahent_nip": nip_kontrahenta,
        "kontrahent_nazwa": nazwa_kontrahenta,
        "netto": netto,
        "vat": vat,
        "brutto": brutto,
        "sciezka_xml": sciezka_xml,
        "sciezka_pdf": sciezka_pdf if os.path.exists(sciezka_pdf) else None,
    }


def wczytaj_indeks() -> dict[str, Any]:
    """Wczytuje zindeksowane faktury z pliku JSON."""
    if os.path.exists(PLIK_INDEKSU):
        try:
            with open(PLIK_INDEKSU, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def zapisz_indeks(indeks: dict[str, Any]) -> None:
    """Zapisuje zaktualizowany indeks do pliku JSON."""
    with open(PLIK_INDEKSU, "w", encoding="utf-8") as f:
        json.dump(indeks, f, indent=2, ensure_ascii=False)


def aktualizuj_indeks(konfiguracja: dict[str, Any] | None = None) -> tuple[dict[str, Any], int, int]:
    """
    Skanuje foldery z plikami XML:
    - dodaje nowe dokumenty,
    - usuwa wpisy, których pliki zniknęły z dysku.
    Zwraca: (zaktualizowany_indeks, liczba_dodanych, liczba_usunietych)
    """
    if konfiguracja is None:
        konfiguracja = zu.wczytaj_konfiguracje()

    folder_glowny = konfiguracja.get("folder_glowny", zu.pobierz_domyslny_katalog())
    firmy = konfiguracja.get("firmy", [])
    indeks = wczytaj_indeks()

    liczba_dodanych = 0
    liczba_usunietych = 0

    # 1. Czyszczenie: usunięcie faktur, których plik XML już nie istnieje na dysku
    klucze_do_usuniecia = []
    for klucz, dane in indeks.items():
        sciezka = dane.get("sciezka_xml", "")
        if not os.path.exists(sciezka):
            klucze_do_usuniecia.append(klucz)

    for k in klucze_do_usuniecia:
        del indeks[k]
        liczba_usunietych += 1

    # 2. Skanowanie folderów i indeksowanie nowości
    for firma in firmy:
        nip_wlasny = str(firma.get("nip", "")).strip()
        nazwa_wlasna = firma.get("nazwa", "")

        for typ_rejestru in ["zakup", "sprzedaz"]:
            folder_xml = zu.pobierz_sciezke_firmy(folder_glowny, nip_wlasny, f"{typ_rejestru}_xml")
            if not os.path.exists(folder_xml):
                continue

            for nazwa_pliku in os.listdir(folder_xml):
                if not nazwa_pliku.lower().endswith(".xml"):
                    continue

                nr_ksef = os.path.splitext(nazwa_pliku)[0]
                unikalny_klucz = f"{nip_wlasny}_{typ_rejestru}_{nr_ksef}"

                # Jeśli faktura jest już w indeksie, pomijamy parsowanie
                if unikalny_klucz in indeks:
                    # Aktualizujemy tylko ścieżkę do PDF, gdyby pojawił się później
                    sciezka_pdf = os.path.join(
                        zu.pobierz_sciezke_firmy(folder_glowny, nip_wlasny, f"{typ_rejestru}_pdf"),
                        f"{nr_ksef}.pdf"
                    )
                    if os.path.exists(sciezka_pdf):
                        indeks[unikalny_klucz]["sciezka_pdf"] = sciezka_pdf
                    continue

                sciezka_pelna = os.path.join(folder_xml, nazwa_pliku)
                sparsowane = parsuj_fakture_xml(sciezka_pelna, typ_rejestru=typ_rejestru)
                if sparsowane:
                    sparsowane["moja_firma_nip"] = nip_wlasny
                    sparsowane["moja_firma_nazwa"] = nazwa_wlasna
                    indeks[unikalny_klucz] = sparsowane
                    liczba_dodanych += 1

    if liczba_dodanych > 0 or liczba_usunietych > 0 or not os.path.exists(PLIK_INDEKSU):
        zapisz_indeks(indeks)

    return indeks, liczba_dodanych, liczba_usunietych


def szukaj_faktur(
    indeks: dict[str, Any],
    fraza: str = "",
    nip_firmy: str = "WSZYSTKIE",
    typ_rejestru: str = "WSZYSTKIE",
    data_od: str = "",
    data_do: str = "",
) -> list[dict[str, Any]]:
    """Filtruje pamięć podręczną faktur według podanych kryteriów."""
    wyniki = []
    fraza_czysta = fraza.strip().lower()

    for dane in indeks.values():
        # Filtr firmy
        if nip_firmy != "WSZYSTKIE" and dane.get("moja_firma_nip") != nip_firmy:
            continue

        # Filtr typu rejestru (zakup / sprzedaz)
        if typ_rejestru != "WSZYSTKIE" and dane.get("typ_rejestru") != typ_rejestru:
            continue

        # Filtr zakresu dat (wg daty sprzedaży / dostawy)
        data_sprz = dane.get("data_sprzedazy", "")
        if data_od and data_sprz and data_sprz < data_od:
            continue
        if data_do and data_sprz and data_sprz > data_do:
            continue

        # Wyszukiwanie frazy tekstowej (numer, NIP, nazwa kontrahenta)
        if fraza_czysta:
            znaleziono = (
                fraza_czysta in dane.get("nr_faktury", "").lower()
                or fraza_czysta in dane.get("nr_ksef", "").lower()
                or fraza_czysta in dane.get("kontrahent_nip", "").lower()
                or fraza_czysta in dane.get("kontrahent_nazwa", "").lower()
            )
            if not znaleziono:
                continue

        wyniki.append(dane)

    # Sortowanie domyślne: od najnowszej daty sprzedaży
    wyniki.sort(key=lambda x: x.get("data_sprzedazy", ""), reverse=True)
    return wyniki