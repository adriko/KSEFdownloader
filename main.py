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


class KSeFRateLimitError(Exception):
    """Zgłaszany, gdy serwer KSeF nałoży długą blokadę czasową (429)."""
    pass


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


def pobierz_faktury_z_okna(access_token, od_kiedy, do_kiedy, subject_type="Subject2", stop_event=None):
    """Pobiera metadane faktur dla pojedynczego przedziału czasowego i typu podmiotu."""
    wszystkie = []
    page_offset = 0
    page_size = 100

    filtry = {
        "subjectType": subject_type,
        "dateRange": {
            "dateType": "PermanentStorage",
            "from": od_kiedy.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": do_kiedy.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    }

    while True:
        if stop_event and stop_event.is_set():
            break

        url_query = f"https://api.ksef.mf.gov.pl/v2/invoices/query/metadata?pageOffset={page_offset}&pageSize={page_size}"
        resp = requests.post(
            url_query,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=filtry,
        )

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 10))
            if retry_after > 60:
                minuty = max(1, round(retry_after / 60))
                print(
                    f"\n⚠️ Serwer KSeF nałożył blokadę na {retry_after}s (~{minuty} min). "
                    f"Przerywam sprawdzanie metadanych."
                )
                raise KSeFRateLimitError(f"Blokada KSeF na {minuty} minut.")
            print(f"Limit zapytań KSeF (429). Czekam krótko {retry_after}s...")
            time.sleep(retry_after)
            continue
        elif resp.status_code != 200:
            print(f"Błąd KSeF ({resp.status_code}): {resp.text}")
            break

        dane = resp.json()
        paczka = dane.get("invoices", [])
        if not paczka:
            break

        wszystkie.extend(paczka)

        if len(paczka) < page_size:
            break

        page_offset += 1
        time.sleep(1.0)

    return wszystkie


def pobierz_faktury_az_do_daty(access_token, data_od, data_do, subject_type="Subject2", stop_event=None):
    """Pobiera metadane cofając się o 90-dniowe okna od data_do aż do data_od."""
    unikalne_faktury = {}
    okno_koniec = data_do

    while okno_koniec > data_od:
        if stop_event and stop_event.is_set():
            break

        okno_poczatek = max(okno_koniec - timedelta(days=90), data_od)
        nazwa_typu = "ZAKUPOWE" if subject_type == "Subject2" else "SPRZEDAŻOWE"
        print(f"Sprawdzam zakres ({nazwa_typu}): od {okno_poczatek.strftime('%Y-%m-%d')} do {okno_koniec.strftime('%Y-%m-%d')}...")

        paczka = pobierz_faktury_z_okna(access_token, okno_poczatek, okno_koniec, subject_type, stop_event)
        for f in paczka:
            unikalne_faktury[f["ksefNumber"]] = f

        okno_koniec = okno_poczatek
        time.sleep(1.0)

    lista_faktur = list(unikalne_faktury.values())
    lista_faktur.reverse()
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
            if retry_after > 60:
                minuty = max(1, round(retry_after / 60))
                print(f"⚠️ Długa blokada pobierania XML (~{minuty} min). Przerywam pobieranie dla tej firmy.")
                raise KSeFRateLimitError(f"Blokada KSeF na {minuty} minut.")
            print(f"Przekroczono limit zapytań (429). Czekam {retry_after}s...")
            time.sleep(retry_after)
        else:
            print(f"Błąd pobierania XML ({resp.status_code}): {resp.text}")
            return None


def main(progress_callback=None, stop_event=None, wybrana_firma_nip="WSZYSTKIE", data_od=None, data_do=None,
         pobieraj_zakupowe=True, pobieraj_sprzedazowe=False, zapisz_xml=False, zapisz_pdf=True):
    teraz = datetime.now(timezone.utc)
    if data_do is None:
        data_do = teraz
    if data_od is None:
        data_od = data_do - timedelta(days=90)

    if wybrana_firma_nip == "WSZYSTKIE":
        firmy_do_przetworzenia = FIRMY
    else:
        firmy_do_przetworzenia = [f for f in FIRMY if str(f["nip"]).strip() == str(wybrana_firma_nip).strip()]

    zadania_typów = []
    if pobieraj_zakupowe:
        zadania_typów.append(("Subject2", "zakup"))
    if pobieraj_sprzedazowe:
        zadania_typów.append(("Subject1", "sprzedaz"))

    suma_nowych = 0
    suma_pominietych = 0
    przerwano = False

    for firma in firmy_do_przetworzenia:
        if stop_event and stop_event.is_set():
            przerwano = True
            break

        nazwa_firmy = firma["nazwa"]
        nip = str(firma["nip"]).strip()
        token = str(firma["token"]).strip()
        glowny_folder = firma["folder"]

        print("\n==================================================")
        print(f"Przetwarzam: {nazwa_firmy} (NIP: {nip})")
        print(f"Katalog bazowy: {glowny_folder}")
        print("==================================================")

        if progress_callback:
            progress_callback(nazwa_firmy, 0, 1, suma_nowych, suma_pominietych, "Logowanie do KSeF...")

        try:
            access_token = zaloguj_do_ksef(nip, token)
            print("Zalogowano pomyślnie do KSeF.")
        except Exception as e:
            print(f"Błąd logowania dla NIP {nip}: {e}")
            continue

        for subject_type, prefiks in zadania_typów:
            if stop_event and stop_event.is_set():
                przerwano = True
                break

            etykieta_grupy = "ZAKUPOWE" if prefiks == "zakup" else "SPRZEDAŻOWE"
            print(f"\n--- Pobieranie faktur: {etykieta_grupy} ---")

            folder_pdf = os.path.join(glowny_folder, f"{prefiks}_pdf")
            folder_xml = os.path.join(glowny_folder, f"{prefiks}_xml")

            if zapisz_pdf:
                os.makedirs(folder_pdf, exist_ok=True)
            if zapisz_xml:
                os.makedirs(folder_xml, exist_ok=True)

            istniejace_pdf = set(os.listdir(folder_pdf)) if os.path.exists(folder_pdf) else set()
            istniejace_xml = set(os.listdir(folder_xml)) if os.path.exists(folder_xml) else set()

            try:
                faktury = pobierz_faktury_az_do_daty(access_token, data_od, data_do, subject_type=subject_type, stop_event=stop_event)
                print(f"Znaleziono metadanych ({etykieta_grupy}): {len(faktury)}")
            except KSeFRateLimitError as e:
                print(f"🛑 Zatrzymano firmę {nazwa_firmy}: {e}")
                if progress_callback:
                    progress_callback(nazwa_firmy, 0, 1, suma_nowych, suma_pominietych, str(e))
                break
            except Exception as e:
                print(f"Błąd listy faktur ({etykieta_grupy}): {e}")
                continue

            razem = len(faktury)
            nowe_w_grupie = 0
            pominiete_w_grupie = 0

            if razem == 0 and progress_callback:
                progress_callback(nazwa_firmy, 1, 1, suma_nowych, suma_pominietych, f"Brak faktur ({etykieta_grupy}).")

            try:
                for i, f in enumerate(faktury, start=1):
                    if stop_event and stop_event.is_set():
                        przerwano = True
                        break

                    nr_ksef = f.get("ksefNumber")
                    nazwa_pdf = f"{nr_ksef}.pdf"
                    nazwa_xml = f"{nr_ksef}.xml"

                    sciezka_pdf = os.path.join(folder_pdf, nazwa_pdf)
                    sciezka_xml = os.path.join(folder_xml, nazwa_xml)

                    pdf_istnieje = (not zapisz_pdf) or (nazwa_pdf in istniejace_pdf)
                    xml_istnieje = (not zapisz_xml) or (nazwa_xml in istniejace_xml)

                    if pdf_istnieje and xml_istnieje:
                        pominiete_w_grupie += 1
                        if progress_callback:
                            progress_callback(
                                nazwa_firmy,
                                i,
                                razem,
                                suma_nowych + nowe_w_grupie,
                                suma_pominietych + pominiete_w_grupie,
                                f"Pominięto [{etykieta_grupy}] ({i}/{razem})",
                            )
                        continue

                    status_tekst = f"[{etykieta_grupy}] {i}/{razem}: {nr_ksef[:15]}..."
                    if progress_callback:
                        progress_callback(
                            nazwa_firmy,
                            i,
                            razem,
                            suma_nowych + nowe_w_grupie,
                            suma_pominietych + pominiete_w_grupie,
                            status_tekst,
                        )

                    print(f"Pobieram [{etykieta_grupy}]: {nr_ksef}...")
                    url_faktura = f"https://api.ksef.mf.gov.pl/v2/invoices/ksef/{nr_ksef}"
                    xml_bytes = pobierz_tresc_xml(url_faktura, access_token)

                    if xml_bytes:
                        if zapisz_xml:
                            with open(sciezka_xml, "wb") as f_xml:
                                f_xml.write(xml_bytes)
                            istniejace_xml.add(nazwa_xml)

                        if zapisz_pdf:
                            try:
                                konwertuj_xml_na_pdf_node(xml_bytes, sciezka_pdf)
                                istniejace_pdf.add(nazwa_pdf)
                            except Exception as e:
                                print(f"Błąd generowania PDF dla {nr_ksef}: {e}")

                        nowe_w_grupie += 1

                    if progress_callback:
                        progress_callback(
                            nazwa_firmy,
                            i,
                            razem,
                            suma_nowych + nowe_w_grupie,
                            suma_pominietych + pominiete_w_grupie,
                            f"Gotowe [{etykieta_grupy}] {i}/{razem}",
                        )

                    time.sleep(2.0)

            except KSeFRateLimitError as e:
                print(f"🛑 Zatrzymano pobieranie plików dla {nazwa_firmy}: {e}")
                if progress_callback:
                    progress_callback(
                        nazwa_firmy,
                        i,
                        razem,
                        suma_nowych + nowe_w_grupie,
                        suma_pominietych + pominiete_w_grupie,
                        f"Zatrzymano: {e}",
                    )
                break

            suma_nowych += nowe_w_grupie
            suma_pominietych += pominiete_w_grupie
            print(f"Koniec ({etykieta_grupy}): Nowych: {nowe_w_grupie}, Pominiętych: {pominiete_w_grupie}")

            if przerwano:
                break

        if przerwano:
            break

    if progress_callback:
        status_koncowy = "🛑 Przerwano operację na żądanie!" if przerwano else "Zakończono pobieranie!"
        progress_callback("Zakończono" if not przerwano else "Przerwano", 1, 1, suma_nowych, suma_pominietych, status_koncowy)
    if przerwano:
        print("\n🛑 Operacja została pomyślnie przerwana na żądanie użytkownika.")


if __name__ == "__main__":
    main()