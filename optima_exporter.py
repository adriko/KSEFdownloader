import os
import re
from typing import Any
import xml.etree.ElementTree as ET


def _wyczysc_namespace(korzen: ET.Element) -> None:
    """Usuwa przestrzenie nazw (namespace) z tagów XML KSeF."""
    for el in korzen.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]


def oczysc_adres(adres_l1: str, adres_l2: str = "") -> dict[str, str]:
    """
    Czyści i rozdziela sklejony adres z KSeF na: ulicę, kod pocztowy i miasto.
    Usuwa zbędne dopiski administracyjne (województwo, gmina, powiat).
    """
    caly_tekst = f"{adres_l1} {adres_l2}".strip()

    kod_pocztowy = ""
    miasto = ""
    ulica = adres_l1.strip()

    m_kod = re.search(r"\b(\d{2}-\d{3})\b", caly_tekst)
    if m_kod:
        kod_pocztowy = m_kod.group(1)

        tekst_po_kodzie = caly_tekst[m_kod.end():].strip()
        m_miasto = re.match(r"^([^,;]+)", tekst_po_kodzie)
        if m_miasto:
            miasto = m_miasto.group(1).strip()

        if kod_pocztowy in ulica:
            ulica = ulica.split(kod_pocztowy)[0].strip().rstrip(",")
            if not ulica:
                reszta = adres_l1.split(miasto, 1)[-1].strip().lstrip(", ")
                if reszta:
                    ulica = reszta

    if not miasto:
        miasto = adres_l2.strip() or "Brak"

    ulica = re.sub(r",\s*$", "", ulica).strip()
    miasto = re.sub(r",\s*$", "", miasto).strip()

    return {
        "ulica": ulica,
        "kod_pocztowy": kod_pocztowy,
        "miasto": miasto,
    }


def parsuj_fakture_ksef(sciezka_xml: str, typ_rejestru: str = "sprzedaz") -> dict[str, Any]:
    """
    Parsuje fakturę KSeF.
    Dla sprzedaży (sprzedaz): kontrahentem jest nabywca (Podmiot2).
    Dla zakupu (zakup): kontrahentem jest dostawca (Podmiot1).
    """
    drzewo = ET.parse(sciezka_xml)
    korzen = drzewo.getroot()
    _wyczysc_namespace(korzen)

    wezel_kontrahenta = korzen.find("Podmiot1" if typ_rejestru == "zakup" else "Podmiot2")
    dane_id = wezel_kontrahenta.find("DaneIdentyfikacyjne") if wezel_kontrahenta is not None else None
    adres = wezel_kontrahenta.find("Adres") if wezel_kontrahenta is not None else None

    kod_kraju = adres.findtext("KodKraju", default="PL") if adres is not None else "PL"
    nazwa = dane_id.findtext("Nazwa", default="") if dane_id is not None else ""

    if kod_kraju.upper() == "PL":
        nip = dane_id.findtext("NIP", default="") if dane_id is not None else ""
    else:
        nip = (
            dane_id.findtext("NrVatUE")
            or dane_id.findtext("NrID")
            or dane_id.findtext("NIP", default="")
            if dane_id is not None
            else ""
        )

    if nip:
        akronim = f"{kod_kraju}{nip}"
    else:
        akronim = re.sub(r"[^A-Za-z0-9]", "", nazwa)[:20]

    adres_l1 = adres.findtext("AdresL1", default="") if adres is not None else ""
    adres_l2 = adres.findtext("AdresL2", default="") if adres is not None else ""

    dane_adresowe = oczysc_adres(adres_l1, adres_l2)
    ulica = dane_adresowe["ulica"]
    kod_pocztowy = dane_adresowe["kod_pocztowy"]
    miasto = dane_adresowe["miasto"]

    fa = korzen.find("Fa")
    numer = fa.findtext("P_2", default="")
    data_wystawienia = fa.findtext("P_1", default="")
    data_sprzedazy = fa.findtext("P_6", default=data_wystawienia)
    termin = (
        fa.findtext("Platnosc/TerminPlatnosci/Termin", default="")
        or fa.findtext("Platnosc/DataZaplaty", default=data_wystawienia)
    )
    waluta = fa.findtext("KodWaluty", default="PLN")
    deklaracja_vat7 = data_wystawienia[:7] if len(data_wystawienia) >= 7 else ""
    rodzaj_faktury = fa.findtext("RodzajFaktury", default="VAT")
    korekta = "Tak" if rodzaj_faktury == "KOR" else "Nie"

    wiersz = fa.find("FaWiersz")
    kurs_str = wiersz.findtext("KursWaluty", default="1.0000") if wiersz is not None else "1.0000"
    kurs = float(kurs_str)

    data_kursu = data_wystawienia
    for opis in fa.findall("DodatkowyOpis"):
        tekst = opis.findtext("Wartosc", default="")
        m_kurs = re.search(r"data przelicznika\s*:\s*(\d{4}-\d{2}-\d{2})", tekst, re.IGNORECASE)
        if m_kurs:
            data_kursu = m_kurs.group(1)
            break

    p_13_1 = fa.findtext("P_13_1")
    p_13_7 = fa.findtext("P_13_7")
    p_13_9 = fa.findtext("P_13_9")

    if p_13_1 is not None:
        netto = float(p_13_1)
        vat = float(fa.findtext("P_14_1", default="0.00") or "0.00")
        stawka_vat = "23"
        status_vat = "opodatkowana"
    elif p_13_7 is not None:
        netto = float(p_13_7)
        vat = 0.00
        stawka_vat = "zw"
        status_vat = "zwolniona"
    elif p_13_9 is not None:
        netto = float(p_13_9)
        vat = 0.00
        stawka_vat = "0"
        status_vat = "nie podlega"
    else:
        netto = float(wiersz.findtext("P_11", default="0.00") if wiersz is not None else "0.00")
        vat = float(wiersz.findtext("P_11Vat", default="0.00") if wiersz is not None else "0.00")
        stawka_vat = "23" if vat != 0 else "0"
        status_vat = "opodatkowana" if vat != 0 else "nie podlega"

    vat_sys_str = fa.findtext("P_14_1W")
    vat_sys = float(vat_sys_str) if vat_sys_str else round(vat * kurs, 2)
    netto_sys = round(netto * kurs, 2)

    nazwa_pliku = os.path.basename(sciezka_xml)
    m_ksef = re.search(r"(\d{10}-\d{8}-[0-9A-Fa-f]{12}-[0-9A-Fa-f]{2})", nazwa_pliku)
    nr_ksef = m_ksef.group(1) if m_ksef else ""

    is_krajowy = kod_kraju.upper() == "PL"
    platnosc_vat_w_pln = is_krajowy and waluta != "PLN" and vat > 0

    return {
        "kontrahent": {
            "akronim": akronim,
            "nip": nip,
            "kod_kraju": kod_kraju,
            "nazwa": nazwa,
            "ulica": ulica,
            "kod_pocztowy": kod_pocztowy,
            "poczta": miasto,
        },
        "rejestr": {
            "numer": numer,
            "nr_ksef": nr_ksef,
            "data_wystawienia": data_wystawienia,
            "data_sprzedazy": data_sprzedazy,
            "deklaracja_vat7": deklaracja_vat7,
            "data_kursu": data_kursu,
            "termin": termin,
            "waluta": waluta,
            "kurs": f"{kurs:.4f}",
            "korekta": korekta,
            "stawka_vat": stawka_vat,
            "status_vat": status_vat,
            "netto": f"{netto:.2f}",
            "vat": f"{vat:.2f}",
            "netto_sys": f"{netto_sys:.2f}",
            "vat_sys": f"{vat_sys:.2f}",
            "kwota_brutto": f"{netto + vat:.2f}",
            "kwota_brutto_pln": f"{netto_sys + vat_sys:.2f}",
            "is_krajowy": is_krajowy,
            "platnosc_vat_w_pln": platnosc_vat_w_pln,
        },
    }


def generuj_xml_optima(lista_danych: list[dict[str, Any]], plik_wyjsciowy: str, typ_rejestru: str = "sprzedaz") -> None:
    """Generuje plik XML dla Comarch Optima offline (rejestr sprzedaży lub zakupu)."""
    root = ET.Element("ROOT", attrib={"xmlns": "http://www.comarch.pl/cdn/optima/offline"})

    kontrahenci_el = ET.SubElement(root, "KONTRAHENCI")
    ET.SubElement(kontrahenci_el, "WERSJA").text = "2.00"
    ET.SubElement(kontrahenci_el, "BAZA_ZRD_ID").text = "KS"
    ET.SubElement(kontrahenci_el, "BAZA_DOC_ID").text = "KS"

    unikalni = {elem["kontrahent"]["akronim"]: elem["kontrahent"] for elem in lista_danych}
    for k in unikalni.values():
        k_el = ET.SubElement(kontrahenci_el, "KONTRAHENT")
        ET.SubElement(k_el, "AKRONIM").text = k["akronim"]
        ET.SubElement(k_el, "RODZAJ").text = "odbiorca dostawca"
        ET.SubElement(k_el, "EKSPORT").text = "krajowy" if k["kod_kraju"] == "PL" else "wewnątrzunijny"
        ET.SubElement(k_el, "PLATNIK_VAT").text = "Tak"
        ET.SubElement(k_el, "FORMA_PLATNOSCI").text = "przelew"
        ET.SubElement(k_el, "KRAJ_ISO").text = k["kod_kraju"]

        adresy = ET.SubElement(k_el, "ADRESY")
        adres = ET.SubElement(adresy, "ADRES")
        ET.SubElement(adres, "STATUS").text = "aktualny"
        ET.SubElement(adres, "NAZWA1").text = k["nazwa"]
        ET.SubElement(adres, "KRAJ").text = k["kod_kraju"]
        ET.SubElement(adres, "ULICA").text = k["ulica"]
        ET.SubElement(adres, "KOD_POCZTOWY").text = k["kod_pocztowy"]
        ET.SubElement(adres, "POCZTA").text = k["poczta"]
        ET.SubElement(adres, "NIP_KRAJ").text = k["kod_kraju"]
        ET.SubElement(adres, "NIP").text = k["nip"]

    tag_zbiorczy = "REJESTRY_ZAKUPU_VAT" if typ_rejestru == "zakup" else "REJESTRY_SPRZEDAZY_VAT"
    tag_elementu = "REJESTR_ZAKUPU_VAT" if typ_rejestru == "zakup" else "REJESTR_SPRZEDAZY_VAT"
    kierunek_platnosci = "rozchód" if typ_rejestru == "zakup" else "przychód"

    rejestry_el = ET.SubElement(root, tag_zbiorczy)
    ET.SubElement(rejestry_el, "WERSJA").text = "2.00"
    ET.SubElement(rejestry_el, "BAZA_ZRD_ID").text = "KS"
    ET.SubElement(rejestry_el, "BAZA_DOC_ID").text = "KS"

    for elem in lista_danych:
        k = elem["kontrahent"]
        r = elem["rejestr"]

        rej = ET.SubElement(rejestry_el, tag_elementu)
        ET.SubElement(rej, "MODUL").text = "Rejestr Vat"
        ET.SubElement(rej, "REJESTR").text = "KRAJOWY" if r["is_krajowy"] else "ZAGRANICZNY"
        ET.SubElement(rej, "DATA_WYSTAWIENIA").text = r["data_wystawienia"]
        ET.SubElement(rej, "DATA_SPRZEDAZY").text = r["data_sprzedazy"]
        ET.SubElement(rej, "TERMIN").text = r["termin"]
        ET.SubElement(rej, "NUMER").text = r["numer"]
        ET.SubElement(rej, "KOREKTA").text = r["korekta"]
        ET.SubElement(rej, "TYP_PODMIOTU").text = "kontrahent"
        ET.SubElement(rej, "PODMIOT").text = k["akronim"]
        ET.SubElement(rej, "NAZWA1").text = k["nazwa"]
        ET.SubElement(rej, "NIP_KRAJ").text = k["kod_kraju"]
        ET.SubElement(rej, "NIP").text = k["nip"]
        ET.SubElement(rej, "KRAJ").text = "POLSKA" if r["is_krajowy"] else k["kod_kraju"]
        ET.SubElement(rej, "ULICA").text = k["ulica"]
        ET.SubElement(rej, "KOD_POCZTOWY").text = k["kod_pocztowy"]
        ET.SubElement(rej, "MIASTO").text = k["poczta"]
        ET.SubElement(rej, "KATEGORIA").text = "400" if typ_rejestru == "zakup" else "710"
        ET.SubElement(rej, "FORMA_PLATNOSCI").text = "przelew"
        ET.SubElement(rej, "DEKLARACJA_VAT7").text = r["deklaracja_vat7"]
        ET.SubElement(rej, "DEKLARACJA_VATUE").text = "Nie" if r["is_krajowy"] else "Tak"
        ET.SubElement(rej, "WALUTA").text = r["waluta"]
        ET.SubElement(rej, "KURS_WALUTY").text = "NBP"
        ET.SubElement(rej, "NOTOWANIE_WALUTY_ILE").text = r["kurs"]
        ET.SubElement(rej, "NOTOWANIE_WALUTY_ZA_ILE").text = "1"
        ET.SubElement(rej, "DATA_KURSU").text = r["data_kursu"]

        if r["platnosc_vat_w_pln"]:
            ET.SubElement(rej, "PLATNOSC_VAT_W_PLN").text = "Tak"

        ET.SubElement(rej, "JPK_FA").text = "Tak"
        ET.SubElement(rej, "NR_KSEF").text = r["nr_ksef"]

        pozycje = ET.SubElement(rej, "POZYCJE")
        poz = ET.SubElement(pozycje, "POZYCJA")
        ET.SubElement(poz, "KATEGORIA_POS").text = "400" if typ_rejestru == "zakup" else "710"
        ET.SubElement(poz, "STAWKA_VAT").text = r["stawka_vat"]
        ET.SubElement(poz, "STATUS_VAT").text = r["status_vat"]
        ET.SubElement(poz, "NETTO").text = r["netto"]
        ET.SubElement(poz, "VAT").text = r["vat"]
        ET.SubElement(poz, "NETTO_SYS").text = r["netto_sys"]
        ET.SubElement(poz, "VAT_SYS").text = r["vat_sys"]
        ET.SubElement(poz, "RODZAJ_SPRZEDAZY" if typ_rejestru == "sprzedaz" else "RODZAJ_ZAKUPU").text = "usługi"

        platnosci = ET.SubElement(rej, "PLATNOSCI")
        if r["platnosc_vat_w_pln"]:
            p1 = ET.SubElement(platnosci, "PLATNOSC")
            ET.SubElement(p1, "TERMIN_PLAT").text = r["termin"]
            ET.SubElement(p1, "FORMA_PLATNOSCI_PLAT").text = "przelew"
            ET.SubElement(p1, "WALUTA_PLAT").text = r["waluta"]
            ET.SubElement(p1, "KURS_WALUTY_PLAT").text = "NBP"
            ET.SubElement(p1, "NOTOWANIE_WALUTY_ILE_PLAT").text = r["kurs"]
            ET.SubElement(p1, "NOTOWANIE_WALUTY_ZA_ILE_PLAT").text = "1"
            ET.SubElement(p1, "KWOTA_PLN_PLAT").text = r["netto_sys"]
            ET.SubElement(p1, "KWOTA_PLAT").text = r["netto"]
            ET.SubElement(p1, "KIERUNEK").text = kierunek_platnosci
            ET.SubElement(p1, "PODLEGA_ROZLICZENIU").text = "Tak"
            ET.SubElement(p1, "DATA_KURSU_PLAT").text = r["data_kursu"]
            ET.SubElement(p1, "WALUTA_DOK").text = r["waluta"]

            p2 = ET.SubElement(platnosci, "PLATNOSC")
            ET.SubElement(p2, "TERMIN_PLAT").text = r["termin"]
            ET.SubElement(p2, "FORMA_PLATNOSCI_PLAT").text = "przelew"
            ET.SubElement(p2, "WALUTA_PLAT").text = ""
            ET.SubElement(p2, "KURS_WALUTY_PLAT").text = "--"
            ET.SubElement(p2, "NOTOWANIE_WALUTY_ILE_PLAT").text = "1"
            ET.SubElement(p2, "NOTOWANIE_WALUTY_ZA_ILE_PLAT").text = "1"
            ET.SubElement(p2, "KWOTA_PLN_PLAT").text = r["vat_sys"]
            ET.SubElement(p2, "KWOTA_PLAT").text = r["vat_sys"]
            ET.SubElement(p2, "KIERUNEK").text = kierunek_platnosci
            ET.SubElement(p2, "PODLEGA_ROZLICZENIU").text = "Tak"
            ET.SubElement(p2, "DATA_KURSU_PLAT").text = r["data_kursu"]
            ET.SubElement(p2, "WALUTA_DOK").text = ""
        else:
            p = ET.SubElement(platnosci, "PLATNOSC")
            ET.SubElement(p, "TERMIN_PLAT").text = r["termin"]
            ET.SubElement(p, "FORMA_PLATNOSCI_PLAT").text = "przelew"
            ET.SubElement(p, "WALUTA_PLAT").text = r["waluta"] if r["waluta"] != "PLN" else ""
            ET.SubElement(p, "KWOTA_PLN_PLAT").text = r["kwota_brutto_pln"]
            ET.SubElement(p, "KWOTA_PLAT").text = r["kwota_brutto"]
            ET.SubElement(p, "KIERUNEK").text = kierunek_platnosci
            ET.SubElement(p, "PODLEGA_ROZLICZENIU").text = "Tak"

    drzewo = ET.ElementTree(root)
    ET.indent(drzewo, space="  ")
    drzewo.write(plik_wyjsciowy, encoding="windows-1250", xml_declaration=True)


def eksportuj_katalog_do_optimy(
    katalog_xml: str,
    plik_wynikowy: str,
    data_od: str | None = None,
    data_do: str | None = None,
    wg_czego: str = "sprzedaz",
    typ_rejestru: str = "sprzedaz",
) -> int:
    """Parsuje pliki z wybranego folderu i generuje plik XML Optimy z filtrowaniem."""
    if not os.path.exists(katalog_xml):
        return 0

    zebrane_dane = []
    for plik in os.listdir(katalog_xml):
        if not plik.lower().endswith(".xml"):
            continue

        pelna_sciezka = os.path.join(katalog_xml, plik)
        try:
            dane = parsuj_fakture_ksef(pelna_sciezka, typ_rejestru=typ_rejestru)
        except (ET.ParseError, OSError, ValueError, KeyError) as err:
            print(f"Pominięto plik {plik} z powodu błędu struktury: {err}")
            continue

        r = dane["rejestr"]
        data_porownania = r["data_sprzedazy"] if wg_czego == "sprzedaz" else r["data_wystawienia"]

        if data_od and data_porownania < data_od:
            continue
        if data_do and data_porownania > data_do:
            continue

        zebrane_dane.append(dane)

    if zebrane_dane:
        klucz_sortowania = (
            (lambda x: x["rejestr"]["data_sprzedazy"])
            if wg_czego == "sprzedaz"
            else (lambda x: x["rejestr"]["data_wystawienia"])
        )
        zebrane_dane.sort(key=klucz_sortowania)
        generuj_xml_optima(zebrane_dane, plik_wynikowy, typ_rejestru=typ_rejestru)

    return len(zebrane_dane)