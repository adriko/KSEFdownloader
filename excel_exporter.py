import csv
from datetime import datetime, timezone
from tkinter import filedialog, messagebox


def eksportuj_liste_do_csv(lista_faktur: list[dict]) -> None:
    """
    Eksportuje przefiltrowaną listę faktur z wyszukiwarki do pliku CSV
    w formacie dostosowanym do polskiej wersji programu Microsoft Excel.
    """
    if not lista_faktur:
        messagebox.showwarning(
            "Brak danych",
            "Brak faktur do wyeksportowania na bieżącej liście wyników.",
        )
        return

    teraz_str = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
    domyslna_nazwa = f"Zestawienie_Faktur_KSeF_{teraz_str}.csv"

    sciezka_zapisu = filedialog.asksaveasfilename(
        title="Zapisz zestawienie do Excela (CSV)",
        defaultextension=".csv",
        initialfile=domyslna_nazwa,
        filetypes=[("Pliki CSV (Excel)", "*.csv"), ("Wszystkie pliki", "*.*")],
    )

    if not sciezka_zapisu:
        return

    naglowki = [
        "Moja Firma",
        "NIP Mojej Firmy",
        "Typ Rejestru",
        "Numer Faktury",
        "Numer KSeF",
        "Kontrahent",
        "NIP Kontrahenta",
        "Data Sprzedaży",
        "Data Wystawienia",
        "Netto (PLN)",
        "VAT (PLN)",
        "Brutto (PLN)",
        "Plik PDF",
        "Plik XML",
    ]

    try:
        # Kodowanie utf-8-sig dodaje znacznik BOM, dzięki czemu Excel od razu poprawnie wyświetla polskie znaki
        with open(sciezka_zapisu, mode="w", newline="", encoding="utf-8-sig") as plik:
            # Średnik jako separator kolumn jest standardem w polskiej lokalizacji Windows/Excel
            writer = csv.writer(plik, delimiter=";")
            writer.writerow(naglowki)

            for f in lista_faktur:
                # Zamiana kropki na przecinek, by Excel traktował wartości jako liczby do sumowania
                netto_str = f"{f.get('netto', 0.0):.2f}".replace(".", ",")
                vat_str = f"{f.get('vat', 0.0):.2f}".replace(".", ",")
                brutto_str = f"{f.get('brutto', 0.0):.2f}".replace(".", ",")

                writer.writerow([
                    f.get("moja_firma_nazwa", ""),
                    f.get("moja_firma_nip", ""),
                    "ZAKUP" if f.get("typ_rejestru") == "zakup" else "SPRZEDAŻ",
                    f.get("nr_faktury", ""),
                    f.get("nr_ksef", ""),
                    f.get("kontrahent_nazwa", "").replace("\n", " ").strip(),
                    f.get("kontrahent_nip", ""),
                    f.get("data_sprzedazy", ""),
                    f.get("data_wystawienia", ""),
                    netto_str,
                    vat_str,
                    brutto_str,
                    f.get("sciezka_pdf", "") or "",
                    f.get("sciezka_xml", "") or "",
                ])

        messagebox.showinfo(
            "Sukces",
            f"Pomyślnie wyeksportowano {len(lista_faktur)} faktur do pliku:\n{sciezka_zapisu}",
        )
    except OSError as e:
        messagebox.showerror("Błąd zapisu", f"Nie udało się zapisać pliku CSV:\n{e}")