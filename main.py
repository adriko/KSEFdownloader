import base64
import os
import secrets
import subprocess
import time
import zipfile
from datetime import datetime, timedelta, timezone

import requests
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

import zarzadca_ustawien as zu

KATALOG_PROJEKTU = os.path.dirname(os.path.abspath(__file__))
SKRYPT_KONWERTERA = os.path.join(KATALOG_PROJEKTU, "ksef-pdf-generator", "konwertuj.mjs")


class KSeFRateLimitError(Exception):
    """Zgłaszany, gdy serwer KSeF nałoży długą blokadę czasową, a operacja zostanie przerwana."""


def czekaj_z_odliczaniem(
    sekundy: int,
    stop_event=None,
    progress_callback=None,
    nazwa_firmy: str = "",
    status_prefix: str = "⏳ Limit KSeF (429)",
) -> bool:
    """Odlicza sekundy nałożone przez serwer KSeF (nagłówek Retry-After)."""
    laczny_czas = max(sekundy, 1)
    print(f"\n⚠️ Wykryto limit KSeF! Wstrzymanie pracy na {sekundy} s...")

    for pozostalo in range(laczny_czas, 0, -1):
        if stop_event and stop_event.is_set():
            return False

        if progress_callback:
            uplynelo = laczny_czas - pozostalo
            progress_callback(
                nazwa_firmy,
                uplynelo,
                laczny_czas,
                0,
                0,
                f"{status_prefix}! Wznowienie za: {pozostalo} s...",
            )

        time.sleep(1.0)

    print("✅ Limit minął – wznawiam pracę.\n")
    return True


def pobierz_certyfikat_szyfrowania_paczek():
    """Pobiera klucz publiczny MF do szyfrowania klucza symetrycznego paczki."""
    url_keys = "https://api.ksef.mf.gov.pl/v2/security/public-key-certificates"
    resp_keys = requests.get(url_keys, timeout=30).json()
    cert_info = next(
        (c for c in resp_keys if "SymmetricKeyEncryption" in c.get("usage", [])),
        resp_keys[0],
    )
    cert = x509.load_der_x509_certificate(
        base64.b64decode(cert_info["certificate"]), default_backend()
    )
    return cert, cert_info["publicKeyId"]


def zaloguj_do_ksef(nip, token):
    nip = str(nip).strip()
    token = str(token).strip()

    url_ch = "https://api.ksef.mf.gov.pl/v2/auth/challenge"
    resp_ch = requests.post(
        url_ch, json={"contextIdentifier": {"type": "Nip", "value": nip}}, timeout=30
    ).json()

    url_keys = "https://api.ksef.mf.gov.pl/v2/security/public-key-certificates"
    resp_keys = requests.get(url_keys, timeout=30).json()
    cert_info = next(
        c for c in resp_keys if "KsefTokenEncryption" in c.get("usage", [])
    )
    cert = x509.load_der_x509_certificate(
        base64.b64decode(cert_info["certificate"]), default_backend()
    )

    tekst = f"{token}|{resp_ch['timestampMs']}".encode()
    zaszyfrowany = cert.public_key().encrypt(
        tekst,
        padding.OAEP(
            mgf=padding.MGF1(hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )

    url_auth = "https://api.ksef.mf.gov.pl/v2/auth/ksef-token"
    resp_auth = requests.post(
        url_auth,
        json={
            "challenge": resp_ch["challenge"],
            "contextIdentifier": {"type": "Nip", "value": nip},
            "encryptedToken": base64.b64encode(zaszyfrowany).decode("utf-8"),
            "publicKeyId": cert_info["publicKeyId"],
        },
        timeout=30,
    ).json()

    ref_number = resp_auth["referenceNumber"]
    headers_auth = {
        "Authorization": f"Bearer {resp_auth['authenticationToken']['token']}"
    }

    while True:
        st = requests.get(
            f"https://api.ksef.mf.gov.pl/v2/auth/{ref_number}",
            headers=headers_auth,
            timeout=30,
        ).json()
        kod = st.get("status", {}).get("code")
        if kod == 200:
            break
        elif kod != 100:
            raise RuntimeError(f"Błąd uwierzytelniania: {st}")
        time.sleep(1)

    url_redeem = "https://api.ksef.mf.gov.pl/v2/auth/token/redeem"
    access_token = requests.post(url_redeem, headers=headers_auth, timeout=30).json()[
        "accessToken"
    ]["token"]
    return access_token


def pobierz_paczke_faktur(
    access_token,
    data_od,
    data_do,
    subject_type,
    folder_docelowy_xml,
    stop_event,
    progress_callback,
    nazwa_firmy,
    prefiks,
):
    """Pobiera i odszyfrowuje paczki faktur z bezpiecznymi przerwami między oknami (30 dni)."""
    okna_czasowe = []
    kursor_od = data_od
    while kursor_od < data_do:
        kursor_do = min(kursor_od + timedelta(days=30), data_do)
        okna_czasowe.append((kursor_od, kursor_do))
        kursor_od = kursor_do

    cert_mf, key_id = pobierz_certyfikat_szyfrowania_paczek()
    url_export = "https://api.ksef.mf.gov.pl/v2/invoices/exports"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    lacznie_wyodrebnionych = 0

    for nr_okna, (okno_od, okno_do) in enumerate(okna_czasowe, start=1):
        if stop_event and stop_event.is_set():
            return lacznie_wyodrebnionych

        print(
            f"Zlecam paczkę [{prefiks}] ({nr_okna}/{len(okna_czasowe)}): "
            f"{okno_od.strftime('%Y-%m-%d')} do {okno_do.strftime('%Y-%m-%d')}..."
        )

        aes_key = secrets.token_bytes(32)
        iv = secrets.token_bytes(16)

        enc_sym_key = cert_mf.public_key().encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

        payload = {
            "encryption": {
                "encryptedSymmetricKey": base64.b64encode(enc_sym_key).decode("utf-8"),
                "initializationVector": base64.b64encode(iv).decode("utf-8"),
                "publicKeyId": key_id,
            },
            "filters": {
                "subjectType": subject_type,
                "dateRange": {
                    "dateType": "PermanentStorage",
                    "from": okno_od.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "to": okno_do.strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            },
        }

        # 2. Wysłanie zlecenia eksportu z pełną obsługą kodu 429 (Rate Limit)
        while True:
            if stop_event and stop_event.is_set():
                return lacznie_wyodrebnionych

            resp = requests.post(url_export, headers=headers, json=payload, timeout=45)
            if resp.status_code == 429:
                # Odczytaj czas z nagłówka lub daj bezpieczne domyślnie 60 sekund
                retry = int(resp.headers.get("Retry-After", 60))
                if not czekaj_z_odliczaniem(retry, stop_event, progress_callback, nazwa_firmy):
                    return lacznie_wyodrebnionych
                continue
            elif resp.status_code not in (200, 201):
                print(f"Błąd zlecenia eksportu: {resp.text}")
                break
            break

        if resp.status_code not in (200, 201):
            continue

        ref_number = resp.json()["referenceNumber"]

        # 3. Oczekiwanie na przygotowanie paczki przez KSeF
        url_status = f"https://api.ksef.mf.gov.pl/v2/invoices/exports/{ref_number}"
        paczka = None
        while True:
            if stop_event and stop_event.is_set():
                return lacznie_wyodrebnionych

            r_stat = requests.get(url_status, headers=headers, timeout=30)
            if r_stat.status_code == 429:
                retry = int(r_stat.headers.get("Retry-After", 30))
                if not czekaj_z_odliczaniem(retry, stop_event, progress_callback, nazwa_firmy):
                    return lacznie_wyodrebnionych
                continue

            if r_stat.status_code == 200:
                dane_statusu = r_stat.json()
                kod = dane_statusu.get("status", {}).get("code")
                if kod == 200:
                    paczka = dane_statusu.get("package", {})
                    break
                elif kod not in (100, 150):
                    print(f"Błąd generowania paczki: {dane_statusu}")
                    break

            if progress_callback:
                progress_callback(
                    nazwa_firmy,
                    nr_okna - 1,
                    len(okna_czasowe),
                    lacznie_wyodrebnionych,
                    0,
                    f"⏳ KSeF generuje paczkę ({nr_okna}/{len(okna_czasowe)}) [{prefiks}]...",
                )
            time.sleep(3.0)

        if not paczka:
            continue

        # 4. Odszyfrowanie i rozpakowanie plików XML
        czesci = paczka.get("parts", [])
        for czesc in czesci:
            if stop_event and stop_event.is_set():
                return lacznie_wyodrebnionych

            r_plik = requests.get(czesc["url"], timeout=120)
            zaszyfrowane = r_plik.content

            cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            odszyfrowany_padded = decryptor.update(zaszyfrowane) + decryptor.finalize()

            unpadder = sym_padding.PKCS7(128).unpadder()
            dane_zip = unpadder.update(odszyfrowany_padded) + unpadder.finalize()

            sciezka_zip = os.path.join(folder_docelowy_xml, f"temp_{ref_number}.zip")
            with open(sciezka_zip, "wb") as f_zip:
                f_zip.write(dane_zip)

            with zipfile.ZipFile(sciezka_zip, "r") as zf:
                for nazwa_pliku in zf.namelist():
                    if nazwa_pliku.endswith(".xml"):
                        zf.extract(nazwa_pliku, folder_docelowy_xml)
                        lacznie_wyodrebnionych += 1

            if os.path.exists(sciezka_zip):
                os.remove(sciezka_zip)

        # KLUCZOWE: 5 sekund przerwy między kolejnymi oknami czasowymi, 
        # co chroni przed natychmiastowym ponownym banem 429 od KSeF.
        time.sleep(5.0)

    print(f"Łącznie wyodrębniono {lacznie_wyodrebnionych} faktur XML dla [{prefiks}].")
    return lacznie_wyodrebnionych


def konwertuj_xml_na_pdf_node(xml_bytes, sciezka_pdf):
    sciezka_tmp_xml = sciezka_pdf.replace(".pdf", "_temp.xml")
    with open(sciezka_tmp_xml, "wb") as f:
        f.write(xml_bytes)

    komenda = ["node", SKRYPT_KONWERTERA, sciezka_tmp_xml, sciezka_pdf]
    wynik = subprocess.run(komenda, capture_output=True, text=True, check=False)

    if os.path.exists(sciezka_tmp_xml):
        os.remove(sciezka_tmp_xml)

    if wynik.returncode != 0:
        raise RuntimeError(f"Błąd konwersji Node: {wynik.stderr.strip()}")


def konwertuj_brakujace_pdf(
    folder_xml,
    folder_pdf,
    stop_event,
    progress_callback,
    nazwa_firmy,
    prefiks,
):
    """Sprawdza pliki XML i generuje brakujące PDF-y."""
    os.makedirs(folder_pdf, exist_ok=True)
    istniejace_pdf = set(os.listdir(folder_pdf)) if os.path.exists(folder_pdf) else set()
    pliki_xml = [p for p in os.listdir(folder_xml) if p.endswith(".xml")]

    do_konwersji = [p for p in pliki_xml if p.replace(".xml", ".pdf") not in istniejace_pdf]
    razem = len(do_konwersji)
    nowe_pdf = 0

    if razem == 0:
        return 0

    for i, plik_xml in enumerate(do_konwersji, start=1):
        if stop_event and stop_event.is_set():
            break

        nazwa_podstawowa = plik_xml.replace(".xml", "")
        if progress_callback:
            progress_callback(
                nazwa_firmy,
                i,
                razem,
                nowe_pdf,
                0,
                f"📄 Generowanie PDF ({prefiks}) {i}/{razem}: {nazwa_podstawowa[:15]}...",
            )

        sciezka_xml = os.path.join(folder_xml, plik_xml)
        sciezka_pdf = os.path.join(folder_pdf, f"{nazwa_podstawowa}.pdf")

        try:
            with open(sciezka_xml, "rb") as f_xml:
                xml_bytes = f_xml.read()
            konwertuj_xml_na_pdf_node(xml_bytes, sciezka_pdf)
            nowe_pdf += 1
        except Exception as e:  # noqa: BLE001
            print(f"Błąd generowania PDF dla {nazwa_podstawowa}: {e}")

    return nowe_pdf


def main(
    progress_callback=None,
    stop_event=None,
    wybrana_firma_nip="WSZYSTKIE",
    data_od=None,
    data_do=None,
    pobieraj_zakupowe=True,
    pobieraj_sprzedazowe=False,
    zapisz_xml=True,
    zapisz_pdf=True,
    konfiguracja=None,
):
    teraz = datetime.now(timezone.utc)
    if data_do is None:
        data_do = teraz
    if data_od is None:
        data_od = data_do - timedelta(days=90)

    if konfiguracja is None:
        konfiguracja = zu.wczytaj_konfiguracje()

    folder_glowny = konfiguracja.get("folder_glowny", zu.pobierz_domyslny_katalog())
    lista_firm = konfiguracja.get("firmy", [])

    if wybrana_firma_nip == "WSZYSTKIE":
        firmy_do_przetworzenia = lista_firm
    else:
        firmy_do_przeniesienia = [
            f for f in lista_firm if str(f["nip"]).strip() == str(wybrana_firma_nip).strip()
        ]
        firmy_do_przetworzenia = firmy_do_przeniesienia

    zadania = []
    if pobieraj_zakupowe:
        zadania.append(("Subject2", "zakup"))
    if pobieraj_sprzedazowe:
        zadania.append(("Subject1", "sprzedaz"))

    przerwano = False

    for firma in firmy_do_przetworzenia:
        if stop_event and stop_event.is_set():
            przerwano = True
            break

        nazwa = firma["nazwa"]
        nip = str(firma["nip"]).strip()
        token = str(firma["token"]).strip()

        print("\n==================================================")
        print(f"Przetwarzam: {nazwa} (NIP: {nip})")
        print("==================================================")

        if progress_callback:
            progress_callback(nazwa, 0, 1, 0, 0, "Logowanie do KSeF...")

        try:
            access_token = zaloguj_do_ksef(nip, token)
            print("Zalogowano pomyślnie do KSeF.")
        except Exception as e:  # noqa: BLE001
            print(f"Błąd logowania dla NIP {nip}: {e}")
            continue

        for subject_type, prefiks in zadania:
            if stop_event and stop_event.is_set():
                przerwano = True
                break

            folder_xml = zu.pobierz_sciezke_firmy(folder_glowny, nip, f"{prefiks}_xml")
            folder_pdf = zu.pobierz_sciezke_firmy(folder_glowny, nip, f"{prefiks}_pdf")
            os.makedirs(folder_xml, exist_ok=True)
            os.makedirs(folder_pdf, exist_ok=True)

            print(f"\n--- Rozpoczynam pobieranie paczki: {prefiks.upper()} ---")
            pobierz_paczke_faktur(
                access_token=access_token,
                data_od=data_od,
                data_do=data_do,
                subject_type=subject_type,
                folder_docelowy_xml=folder_xml,
                stop_event=stop_event,
                progress_callback=progress_callback,
                nazwa_firmy=nazwa,
                prefiks=prefiks,
            )

            if zapisz_pdf:
                print(f"Generowanie brakujących plików PDF dla [{prefiks}]...")
                konwertuj_brakujace_pdf(
                    folder_xml=folder_xml,
                    folder_pdf=folder_pdf,
                    stop_event=stop_event,
                    progress_callback=progress_callback,
                    nazwa_firmy=nazwa,
                    prefiks=prefiks,
                )

            # Przerwa między zmianą rejestru (np. zakup -> sprzedaż)
            time.sleep(3.0)

        if przerwano:
            break

    if progress_callback:
        status_koncowy = (
            "🛑 Przerwano operację na żądanie!" if przerwano else "✅ Zakończono pobieranie!"
        )
        progress_callback("Zakończono" if not przerwano else "Przerwano", 1, 1, 0, 0, status_koncowy)

    if przerwano:
        print("\n🛑 Operacja została pomyślnie przerwana.")


if __name__ == "__main__":
    main()