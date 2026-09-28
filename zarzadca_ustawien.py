import json
import os
from typing import Any

PLIK_USTAWIEN = "ustawienia.json"
PODFOLDERY = ["zakup_pdf", "zakup_xml", "sprzedaz_pdf", "sprzedaz_xml"]


def pobierz_domyslny_katalog() -> str:
    """Zwraca domyślną ścieżkę do folderu KSeF na Pulpicie bieżącego użytkownika."""
    sciezka_pulpitu = os.path.join(os.path.expanduser("~"), "Desktop")
    return os.path.join(sciezka_pulpitu, "KSeF")


def migruj_ze_starego_configu() -> list[dict[str, str]]:
    """Próbuje zaimportować listę firm ze starego config.py, ignorując stare ścieżki."""
    try:
        from config import FIRMY  # type: ignore

        oczyszczone_firmy = []
        for f in FIRMY:
            oczyszczone_firmy.append({
                "nazwa": str(f.get("nazwa", "")).strip(),
                "nip": str(f.get("nip", "")).strip(),
                "token": str(f.get("token", "")).strip(),
            })
        return oczyszczone_firmy
    except ImportError:
        return []


def wczytaj_konfiguracje() -> dict[str, Any]:
    """
    Wczytuje konfigurację z ustawienia.json.
    Jeśli plik nie istnieje, migruje dane ze starego config.py i tworzy bazowy szablon.
    """
    if os.path.exists(PLIK_USTAWIEN):
        try:
            with open(PLIK_USTAWIEN, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"⚠️ Błąd odczytu pliku ustawień: {e}")

    # Fallback / pierwsze uruchomienie
    domyslne_firmy = migruj_ze_starego_configu()
    konfiguracja = {
        "folder_glowny": pobierz_domyslny_katalog(),
        "firmy": domyslne_firmy,
    }
    zapisz_konfiguracje(konfiguracja)
    return konfiguracja


def zapisz_konfiguracje(konfiguracja: dict[str, Any]) -> None:
    """Zapisuje słownik konfiguracji do pliku ustawienia.json."""
    with open(PLIK_USTAWIEN, "w", encoding="utf-8") as f:
        json.dump(konfiguracja, f, indent=4, ensure_ascii=False)


def pobierz_sciezke_firmy(folder_glowny: str, nip: str, podfolder: str = "") -> str:
    """Buduje pełną ścieżkę do katalogu firmy lub jej podfolderu."""
    nip_czysty = str(nip).strip()
    if podfolder:
        return os.path.join(folder_glowny, nip_czysty, podfolder)
    return os.path.join(folder_glowny, nip_czysty)


def utworz_strukture_katalogow(folder_glowny: str, lista_firm: list[dict[str, str]]) -> None:
    """Tworzy na dysku główny katalog KSeF oraz podkatalogi dla każdego NIP-u."""
    os.makedirs(folder_glowny, exist_ok=True)

    for firma in lista_firm:
        nip = str(firma.get("nip", "")).strip()
        if not nip:
            continue

        for sub in PODFOLDERY:
            pelna_sciezka = pobierz_sciezke_firmy(folder_glowny, nip, sub)
            os.makedirs(pelna_sciezka, exist_ok=True)


def sprawdz_integralnosc(folder_glowny: str, lista_firm: list[dict[str, str]]) -> dict[str, Any]:
    """
    Weryfikuje poprawność istnienia folderów na dysku.
    Zwraca słownik ze statusem oraz listą brakujących ścieżek.
    """
    brakujace = []

    if not os.path.exists(folder_glowny):
        brakujace.append(folder_glowny)

    for firma in lista_firm:
        nip = str(firma.get("nip", "")).strip()
        if not nip:
            continue

        for sub in PODFOLDERY:
            sciezka = pobierz_sciezke_firmy(folder_glowny, nip, sub)
            if not os.path.exists(sciezka):
                brakujace.append(sciezka)

    return {
        "poprawny": len(brakujace) == 0,
        "liczba_brakow": len(brakujace),
        "brakujace_katalogi": brakujace,
    }

def dodaj_firme(
    konfiguracja: dict[str, Any], nazwa: str, nip: str, token: str
) -> tuple[bool, str]:
    """
    Dodaje nową firmę do konfiguracji i tworzy dla niej strukturę folderów.
    Zwraca (sukces, komunikat).
    """
    nazwa_czysta = nazwa.strip()
    nip_czysty = nip.strip()
    token_czysty = token.strip()

    if not nazwa_czysta or not nip_czysty or not token_czysty:
        return False, "Wszystkie pola (nazwa, NIP, token) muszą być wypełnione."

    firmy = konfiguracja.get("firmy", [])

    # Sprawdzenie unikalności NIP-u
    for f in firmy:
        if str(f.get("nip", "")).strip() == nip_czysty:
            return False, f"Firma o numerze NIP {nip_czysty} już istnieje w bazie danych."

    nowa_firma = {
        "nazwa": nazwa_czysta,
        "nip": nip_czysty,
        "token": token_czysty,
    }
    firmy.append(nowa_firma)
    konfiguracja["firmy"] = firmy

    zapisz_konfiguracje(konfiguracja)

    # Utworzenie katalogów dla nowej firmy
    folder_glowny = konfiguracja.get("folder_glowny", pobierz_domyslny_katalog())
    utworz_strukture_katalogow(folder_glowny, [nowa_firma])

    return True, f"Pomyślnie dodano firmę: {nazwa_czysta}"


def edytuj_firme(
    konfiguracja: dict[str, Any],
    stary_nip: str,
    nowa_nazwa: str,
    nowy_nip: str,
    nowy_token: str,
) -> tuple[bool, str]:
    """
    Aktualizuje dane istniejącej firmy.
    Zwraca (sukces, komunikat).
    """
    stary_nip = stary_nip.strip()
    nowa_nazwa = nowa_nazwa.strip()
    nowy_nip = nowy_nip.strip()
    nowy_token = nowy_token.strip()

    if not nowa_nazwa or not nowy_nip or not nowy_token:
        return False, "Wszystkie pola muszą być wypełnione."

    firmy = konfiguracja.get("firmy", [])

    # Jeśli NIP uległ zmianie, upewnijmy się, że nowy nie koliduje z inną firmą
    if stary_nip != nowy_nip:
        for f in firmy:
            if str(f.get("nip", "")).strip() == nowy_nip:
                return False, f"Firma o numerze NIP {nowy_nip} już istnieje."

    znaleziono = False
    for f in firmy:
        if str(f.get("nip", "")).strip() == stary_nip:
            f["nazwa"] = nowa_nazwa
            f["nip"] = nowy_nip
            f["token"] = nowy_token
            znaleziono = True
            break

    if not znaleziono:
        return False, f"Nie znaleziono firmy o NIP: {stary_nip}"

    zapisz_konfiguracje(konfiguracja)

    # Jeśli zmieniono NIP, tworzymy strukturę dla nowego NIP-u
    folder_glowny = konfiguracja.get("folder_glowny", pobierz_domyslny_katalog())
    utworz_strukture_katalogow(folder_glowny, [{"nip": nowy_nip}])

    return True, f"Zaktualizowano dane firmy: {nowa_nazwa}"


def usun_firme(konfiguracja: dict[str, Any], nip: str) -> tuple[bool, str]:
    """
    Usuwa firmę z konfiguracji (pliki na dysku pozostają bez zmian).
    Zwraca (sukces, komunikat).
    """
    nip_czysty = nip.strip()
    firmy = konfiguracja.get("firmy", [])
    poczatkowa_liczba = len(firmy)

    konfiguracja["firmy"] = [f for f in firmy if str(f.get("nip", "")).strip() != nip_czysty]

    if len(konfiguracja["firmy"]) == poczatkowa_liczba:
        return False, f"Nie odnaleziono firmy o NIP {nip_czysty}."

    zapisz_konfiguracje(konfiguracja)
    return True, f"Pomyślnie usunięto firmę o NIP: {nip_czysty}"


def testuj_polaczenie(nip: str, token: str) -> tuple[bool, str]:
    """
    Wykonuje próbne logowanie do KSeF przy użyciu logiki z main.py.
    Zwraca (sukces, komunikat).
    """
    try:
        from main import zaloguj_do_ksef

        access_token = zaloguj_do_ksef(nip, token)
        if access_token:
            return True, "Połączenie nawiązane pomyślnie! Token KSeF jest poprawny."
        return False, "Nie udało się uzyskać tokenu dostępowego."
    except Exception as e:  # noqa: BLE001
        return False, f"Błąd połączenia z KSeF: {e}"