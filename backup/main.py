import base64
from datetime import datetime, timedelta, timezone
import os
import subprocess
import time
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
import requests
from config import FIRMY

KATALOG_PROJEKTU = os.path.dirname(os.path.abspath(__file__))
SKRYPT_KONWERTERA = os.path.join(KATALOG_PROJEKTU, "ksef-pdf-generator", "konwertuj.mjs")


def zaloguj_do_ksef(nip, token):
    nip = str(nip).strip()
    token = str(token).strip()

    url_ch = "https://api.ksef.mf.gov.pl/v2/auth/challenge"
    resp_ch = requests.post(
        url_ch, json={"contextIdentifier": {"type": "Nip", "value": nip}}
    ).json()

    url_keys = "https://api.ksef.mf.gov.pl/v2/security/public-key-certificates"
    resp_keys = requests.get(url_keys).json()
    cert_info = next(
        c for c in resp_keys if "KsefTokenEncryption" in c.get("usage", [])
    )
    cert = x509.load_der_x509_certificate(
        base64.b64decode(cert_info["certificate"]), default_backend()
    )

    tekst = f"{token}|{resp_ch['timestampMs']}".encode("utf-8")
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
    ).json()

    ref_number = resp_auth["referenceNumber"]
    headers_auth = {
        "Authorization": f"Bearer {resp_auth['authenticationToken']['token']}"
    }

    while True:
        st = requests.get(
            f"https://api.ksef.mf.gov.pl/v2/auth/{ref_number}",
            headers=headers_auth,
        ).json()
        kod = st.get("status", {}).get("code")
        if kod == 200:
            break
        elif kod != 100:
            raise RuntimeError(f"Błąd uwierzytelniania: {st}")
        time.sleep(1)

    url_redeem = "https://api.ksef.mf.gov.pl/v2/auth/token/redeem"
    access_token = requests.post(url_redeem, headers=headers_auth).json()[
        "accessToken"
    ]["token"]
    return access_token


def pobierz_faktury_z_okna(access_token, od_kiedy, do_kiedy):
    """Pobiera metadane faktur dla pojedynczego przedziału czasowego (z obsługą stron)."""
    wszystkie = []
    page_offset = 0
    page_size = 100

    filtry = {
        "subjectType": "Subject2",
        "dateRange": {
            "dateType": "PermanentStorage",
            "from": od_kiedy.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": do_kiedy.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    }

    while True:
        url_query = f"https://api.ksef.mf.gov.pl/v2/invoices/query/metadata?pageOffset={page_offset}&pageSize={page_size}"
        resp = requests.post(
            url_query,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=filtry,
        ).json()

        paczka = resp.get("invoices", [])
        if not paczka:
            break

        wszystkie.extend(paczka)

        if len(paczka) < page_size:
            break

        page_offset += 1

    return wszystkie


def pobierz_faktury_az_do_daty(access_token, data_graniczna, teraz):
    """Pobiera metadane cofając się o 90-dniowe okna aż do wyznaczonej daty granicznej."""
    unikalne_faktury = {}
    okno_koniec = teraz

    while okno_koniec > data_graniczna:
        okno_poczatek = max(okno_koniec - timedelta(days=90), data_graniczna)
        print(f"Sprawdzam zakres: od {okno_poczatek.strftime('%Y-%m-%d')} do {okno_koniec.strftime('%Y-%m-%d')}...")

        paczka = pobierz_faktury_z_okna(access_token, okno_poczatek, okno_koniec)
        for f in paczka:
            unikalne_faktury[f["ksefNumber"]] = f

        okno_koniec = okno_poczatek

    lista_faktur = list(unikalne_faktury.values())
    lista_faktur.reverse()  # Układ od najstarszych do najnowszych
    return lista_faktur


def konwertuj_xml_na_pdf_node(xml_bytes, sciezka_pdf):
    sciezka_tmp_xml = sciezka_pdf.replace(".pdf", "_temp.xml")
    with open(sciezka_tmp_xml, "wb") as f:
        f.write(xml_bytes)

    komenda = ["node", SKRYPT_KONWERTERA, sciezka_tmp_xml, sciezka_pdf]
    wynik = subprocess.run(komenda, capture_output=True, text=True)

    if os.path.exists(sciezka_tmp_xml):
        os.remove(sciezka_tmp_xml)

    if wynik.returncode != 0:
        raise RuntimeError(f"Błąd konwersji Node: {wynik.stderr.strip()}")


def pobierz_tresc_xml(url_faktura, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    while True:
        resp = requests.get(url_faktura, headers=headers)
        if resp.status_code == 200:
            return resp.content
        elif resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 10))
            print(f"Przekroczono limit zapytań (429). Czekam {retry_after}s...")
            time.sleep(retry_after)
        else:
            print(f"Błąd pobierania XML ({resp.status_code}): {resp.text}")
            return None


def main(progress_callback=None):
    teraz = datetime.now(timezone.utc)
    data_graniczna = datetime(2026, 2, 1, 0, 0, 0, tzinfo=timezone.utc)

    for firma in FIRMY:
        nazwa_firmy = firma["nazwa"]
        nip = str(firma["nip"]).strip()
        token = str(firma["token"]).strip()
        folder = firma["folder"]

        print("\n==================================================")
        print(f"Przetwarzam: {nazwa_firmy} (NIP: {nip})")
        print(f"Folder docelowy: {folder}")
        print("==================================================")

        if progress_callback:
            progress_callback(nazwa_firmy, 0, 1, 0, 0, "Logowanie do KSeF...")

        os.makedirs(folder, exist_ok=True)
        istniejace_pliki = set(os.listdir(folder))

        try:
            access_token = zaloguj_do_ksef(nip, token)
            print("Zalogowano pomyślnie do KSeF.")
        except Exception as e:
            print(f"Błąd logowania dla NIP {nip}: {e}")
            continue

        try:
            faktury = pobierz_faktury_az_do_daty(access_token, data_graniczna, teraz)
            print(f"Łącznie pobrano metadanych faktur (od 2026-02-01): {len(faktury)}")
        except Exception as e:
            print(f"Błąd pobierania listy faktur dla {nazwa_firmy}: {e}")
            continue

        razem = len(faktury)
        nowe_pobrane = 0
        pominiete = 0

        if razem == 0 and progress_callback:
            progress_callback(nazwa_firmy, 1, 1, 0, 0, "Brak faktur w wybranym okresie.")

        for i, f in enumerate(faktury, start=1):
            nr_ksef = f.get("ksefNumber")
            nazwa_pdf = f"{nr_ksef}.pdf"
            sciezka_pdf = os.path.join(folder, nazwa_pdf)

            if nazwa_pdf in istniejace_pliki:
                pominiete += 1
                if progress_callback:
                    progress_callback(nazwa_firmy, i, razem, nowe_pobrane, pominiete, f"Pominięto istniejącą ({i}/{razem})")
                continue

            status_tekst = f"Pobieranie {i}/{razem}: {nr_ksef[:15]}..."
            if progress_callback:
                progress_callback(nazwa_firmy, i, razem, nowe_pobrane, pominiete, status_tekst)

            print(f"Pobieram i generuję PDF: {nazwa_pdf}...")
            url_faktura = f"https://api.ksef.mf.gov.pl/v2/invoices/ksef/{nr_ksef}"
            xml_bytes = pobierz_tresc_xml(url_faktura, access_token)

            if xml_bytes:
                try:
                    konwertuj_xml_na_pdf_node(xml_bytes, sciezka_pdf)
                    nowe_pobrane += 1
                    istniejace_pliki.add(nazwa_pdf)
                except Exception as e:
                    print(f"Błąd generowania PDF dla {nr_ksef}: {e}")

            if progress_callback:
                progress_callback(nazwa_firmy, i, razem, nowe_pobrane, pominiete, f"Gotowe {i}/{razem}")

            time.sleep(3.8)

        print(f"Koniec dla {nazwa_firmy}: Pobrano nowych PDF: {nowe_pobrane}, Pominięto: {pominiete}")

    if progress_callback:
        progress_callback("Wszystkie firmy przetworzone", 1, 1, 0, 0, "Zakończono pobieranie!")


if __name__ == "__main__":
    main()