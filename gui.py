import os
import sys
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from tkinter import filedialog, messagebox

import customtkinter as ctk
from tkcalendar import DateEntry

import main
from config import FIRMY
from optima_exporter import eksportuj_katalog_do_optimy

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class PrzekierowanieLogow:
    def __init__(self, pole_tekstowe):
        self.pole_tekstowe = pole_tekstowe

    def write(self, tekst):
        self.pole_tekstowe.configure(state="normal")
        self.pole_tekstowe.insert("end", tekst)
        self.pole_tekstowe.see("end")
        self.pole_tekstowe.configure(state="disabled")

    def flush(self):
        pass


class AplikacjaKSeF(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Panel Operatora KSeF & Eksport Optima")
        self.geometry("900x860")
        self.minsize(800, 700)

        self.stop_event = threading.Event()

        # 1. Nagłówek
        self.etykieta_tytul = ctk.CTkLabel(
            self,
            text="Panel Operatora KSeF",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        self.etykieta_tytul.pack(pady=(8, 4))

        # 2. Panel pobierania z KSeF
        self.ramka_opcji = ctk.CTkFrame(self)
        self.ramka_opcji.pack(fill="x", padx=15, pady=4)

        ctk.CTkLabel(self.ramka_opcji, text="Wybierz firmę:", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=8, pady=4, sticky="w"
        )
        self.opcje_firm = ["WSZYSTKIE"] + [f"{f['nazwa']} (NIP: {f['nip']})" for f in FIRMY]
        self.combo_firma = ctk.CTkComboBox(self.ramka_opcji, values=self.opcje_firm, width=380)
        self.combo_firma.grid(row=0, column=1, columnspan=3, padx=8, pady=4, sticky="w")
        self.combo_firma.set("WSZYSTKIE")

        teraz = datetime.now(timezone.utc)
        data_od_domyslna = teraz - timedelta(days=90)

        ctk.CTkLabel(self.ramka_opcji, text="Data od:", font=ctk.CTkFont(weight="bold")).grid(
            row=1, column=0, padx=8, pady=4, sticky="w"
        )
        self.kalendarz_od = DateEntry(
            self.ramka_opcji,
            width=12,
            background="#1f538d",
            foreground="white",
            headersbackground="#14375e",
            headersforeground="white",
            date_pattern="yyyy-mm-dd",
            year=data_od_domyslna.year,
            month=data_od_domyslna.month,
            day=data_od_domyslna.day,
        )
        self.kalendarz_od.grid(row=1, column=1, padx=8, pady=4, sticky="w")

        ctk.CTkLabel(self.ramka_opcji, text="Data do:", font=ctk.CTkFont(weight="bold")).grid(
            row=1, column=2, padx=8, pady=4, sticky="w"
        )
        self.kalendarz_do = DateEntry(
            self.ramka_opcji,
            width=12,
            background="#1f538d",
            foreground="white",
            headersbackground="#14375e",
            headersforeground="white",
            date_pattern="yyyy-mm-dd",
            year=teraz.year,
            month=teraz.month,
            day=teraz.day,
        )
        self.kalendarz_do.grid(row=1, column=3, padx=8, pady=4, sticky="w")

        ctk.CTkLabel(self.ramka_opcji, text="Zakres:", font=ctk.CTkFont(weight="bold")).grid(
            row=2, column=0, padx=8, pady=4, sticky="w"
        )
        self.chk_zakupowe = ctk.CTkCheckBox(self.ramka_opcji, text="Zakupowe (Koszty)")
        self.chk_zakupowe.grid(row=2, column=1, padx=8, pady=4, sticky="w")
        self.chk_zakupowe.select()

        self.chk_sprzedazowe = ctk.CTkCheckBox(self.ramka_opcji, text="Sprzedażowe (Przychody)")
        self.chk_sprzedazowe.grid(row=2, column=2, columnspan=2, padx=8, pady=4, sticky="w")

        ctk.CTkLabel(self.ramka_opcji, text="Formaty:", font=ctk.CTkFont(weight="bold")).grid(
            row=3, column=0, padx=8, pady=4, sticky="w"
        )
        self.chk_pdf = ctk.CTkCheckBox(self.ramka_opcji, text="Zapisz PDF")
        self.chk_pdf.grid(row=3, column=1, padx=8, pady=4, sticky="w")
        self.chk_pdf.select()

        self.chk_xml = ctk.CTkCheckBox(self.ramka_opcji, text="Zapisz XML")
        self.chk_xml.grid(row=3, column=2, columnspan=2, padx=8, pady=4, sticky="w")
        self.chk_xml.select()

        # Przyciski pobierania
        self.ramka_przyciskow = ctk.CTkFrame(self, fg_color="transparent")
        self.ramka_przyciskow.pack(pady=4)

        self.przycisk_start = ctk.CTkButton(
            self.ramka_przyciskow,
            text="🚀 Rozpocznij pobieranie",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=32,
            width=200,
            command=self.uruchom_w_tle,
        )
        self.przycisk_start.pack(side="left", padx=8)

        self.przycisk_stop = ctk.CTkButton(
            self.ramka_przyciskow,
            text="🛑 Przerwij",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=32,
            width=130,
            fg_color="#c0392b",
            hover_color="#962d22",
            state="disabled",
            command=self.przerwij_pobieranie,
        )
        self.przycisk_stop.pack(side="left", padx=8)

        # 3. Panel Eksportu do Comarch Optima
        self.ramka_optima = ctk.CTkFrame(self, border_width=1, border_color="#34495e")
        self.ramka_optima.pack(fill="x", padx=15, pady=6)

        ctk.CTkLabel(
            self.ramka_optima,
            text="📦 EKSPORT DO COMARCH OPTIMA (OFFLINE XML)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#3498db",
        ).grid(row=0, column=0, columnspan=4, padx=10, pady=(6, 4), sticky="w")

        # Rejestr
        ctk.CTkLabel(self.ramka_optima, text="Rejestr:", font=ctk.CTkFont(weight="bold")).grid(
            row=1, column=0, padx=8, pady=3, sticky="w"
        )
        self.var_typ_optima = ctk.StringVar(value="sprzedaz")
        self.rb_sprzedaz = ctk.CTkRadioButton(
            self.ramka_optima, text="Sprzedaż", variable=self.var_typ_optima, value="sprzedaz"
        )
        self.rb_sprzedaz.grid(row=1, column=1, padx=8, pady=3, sticky="w")
        self.rb_zakup = ctk.CTkRadioButton(
            self.ramka_optima, text="Zakup (Koszty)", variable=self.var_typ_optima, value="zakup"
        )
        self.rb_zakup.grid(row=1, column=2, padx=8, pady=3, sticky="w")

        # Filtrowanie dat
        ctk.CTkLabel(self.ramka_optima, text="Okres faktur:", font=ctk.CTkFont(weight="bold")).grid(
            row=2, column=0, padx=8, pady=3, sticky="w"
        )
        self.optima_kal_od = DateEntry(
            self.ramka_optima,
            width=12,
            background="#2980b9",
            foreground="white",
            headersbackground="#1f618d",
            headersforeground="white",
            date_pattern="yyyy-mm-dd",
            year=teraz.year,
            month=teraz.month,
            day=1,
        )
        self.optima_kal_od.grid(row=2, column=1, padx=8, pady=3, sticky="w")

        self.optima_kal_do = DateEntry(
            self.ramka_optima,
            width=12,
            background="#2980b9",
            foreground="white",
            headersbackground="#1f618d",
            headersforeground="white",
            date_pattern="yyyy-mm-dd",
            year=teraz.year,
            month=teraz.month,
            day=teraz.day,
        )
        self.optima_kal_do.grid(row=2, column=2, padx=8, pady=3, sticky="w")

        # Kryterium daty
        self.var_kryterium_daty = ctk.StringVar(value="sprzedaz")
        self.rb_data_sprzedazy = ctk.CTkRadioButton(
            self.ramka_optima, text="Wg daty wykonania/sprzedaży", variable=self.var_kryterium_daty, value="sprzedaz"
        )
        self.rb_data_sprzedazy.grid(row=3, column=1, padx=8, pady=3, sticky="w")
        self.rb_data_wystawienia = ctk.CTkRadioButton(
            self.ramka_optima, text="Wg daty wystawienia", variable=self.var_kryterium_daty, value="wystawienie"
        )
        self.rb_data_wystawienia.grid(row=3, column=2, padx=8, pady=3, sticky="w")

        self.btn_eksport_optima = ctk.CTkButton(
            self.ramka_optima,
            text="📑 Eksportuj do Optimy",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=32,
            fg_color="#27ae60",
            hover_color="#1e8449",
            command=self.wykonaj_eksport_optima,
        )
        self.btn_eksport_optima.grid(row=3, column=3, padx=10, pady=4, sticky="e")

        # 4. Dashboard i status
        self.lbl_status = ctk.CTkLabel(self, text="Gotowy do pracy.", font=ctk.CTkFont(size=12))
        self.lbl_status.pack(pady=(4, 2))

        self.pasek_postepu = ctk.CTkProgressBar(self, height=8)
        self.pasek_postepu.pack(fill="x", padx=20, pady=(0, 4))
        self.pasek_postepu.set(0.0)

        # 5. Logi
        self.pole_logow = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
            state="disabled",
        )
        self.pole_logow.pack(fill="both", expand=True, padx=15, pady=(4, 8))

        sys.stdout = PrzekierowanieLogow(self.pole_logow)

    def wykonaj_eksport_optima(self):
        wybrana = self.combo_firma.get()
        if wybrana == "WSZYSTKIE":
            messagebox.showwarning(
                "Wybierz firmę",
                "Do eksportu do Optimy musisz wybrać konkretną firmę z listy na górze!",
            )
            return

        nip = wybrana.split("NIP: ")[-1].replace(")", "").strip()
        znaleziona_firma = next((f for f in FIRMY if str(f["nip"]).strip() == nip), None)
        if not znaleziona_firma:
            messagebox.showerror("Błąd", "Nie znaleziono wybranej firmy w pliku konfiguracyjnym.")
            return

        typ_rejestru = self.var_typ_optima.get()
        folder_zrodlowy = os.path.join(znaleziona_firma["folder"], f"{typ_rejestru}_xml")

        if not os.path.exists(folder_zrodlowy):
            messagebox.showerror("Brak katalogu", f"Katalog źródłowy nie istnieje:\n{folder_zrodlowy}")
            return

        d_od = self.optima_kal_od.get_date().strftime("%Y-%m-%d")
        d_do = self.optima_kal_do.get_date().strftime("%Y-%m-%d")
        kryterium = self.var_kryterium_daty.get()
        skrot_kryterium = "sprz" if kryterium == "sprzedaz" else "wyst"

        domyslna_nazwa = f"Optima_{typ_rejestru}_{skrot_kryterium}_{nip}_{d_od}_{d_do}.xml"
        sciezka_zapisu = filedialog.asksaveasfilename(
            title="Wskaż miejsce zapisu pliku dla Optimy",
            defaultextension=".xml",
            initialfile=domyslna_nazwa,
            filetypes=[("Pliki XML", "*.xml")],
        )

        if not sciezka_zapisu:
            return

        print(f"\n--- Eksport do Optimy: {znaleziona_firma['nazwa']} ---")
        print(f"Katalog źródłowy: {folder_zrodlowy}")
        print(f"Zakres dat ({kryterium}): {d_od} do {d_do}")

        try:
            liczba = eksportuj_katalog_do_optimy(
                katalog_xml=folder_zrodlowy,
                plik_wynikowy=sciezka_zapisu,
                data_od=d_od,
                data_do=d_do,
                wg_czego=kryterium,
                typ_rejestru=typ_rejestru,
            )
            if liczba > 0:
                print(f"✅ Zapisano pomyślnie {liczba} faktur w: {sciezka_zapisu}")
                messagebox.showinfo("Sukces", f"Pomyślnie wyeksportowano {liczba} faktur do pliku:\n{sciezka_zapisu}")
            else:
                print("⚠️ Nie znaleziono faktur spełniających podane kryteria.")
                messagebox.showwarning("Brak faktur", "W wybranym folderze i zakresie dat nie odnaleziono faktur.")
        except (OSError, ET.ParseError, ValueError) as e:
            print(f"❌ Błąd podczas generowania pliku: {e}")
            messagebox.showerror("Błąd eksportu", f"Wystąpił błąd:\n{e}")

    def aktualizuj_postep(self, nazwa_firmy, aktualna, razem, nowe, pominiete, status_tekst):
        self.lbl_status.configure(text=f"{nazwa_firmy}: {status_tekst}")
        if razem > 0:
            self.pasek_postepu.set(min(max(aktualna / razem, 0.0), 1.0))

    def odczytaj_parametry(self):
        wybrana = self.combo_firma.get()
        nip = "WSZYSTKIE" if wybrana == "WSZYSTKIE" else wybrana.split("NIP: ")[-1].replace(")", "").strip()

        data_od_date = self.kalendarz_od.get_date()
        data_do_date = self.kalendarz_do.get_date()

        d_od = datetime.combine(data_od_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        d_do = datetime.combine(data_do_date, datetime.max.time().replace(microsecond=0)).replace(tzinfo=timezone.utc)

        if d_od > d_do:
            print("❌ Data początkowa nie może być późniejsza niż data końcowa!")
            return None

        zakupowe = bool(self.chk_zakupowe.get())
        sprzedazowe = bool(self.chk_sprzedazowe.get())
        pdf = bool(self.chk_pdf.get())
        xml = bool(self.chk_xml.get())

        if not zakupowe and not sprzedazowe:
            print("❌ Wybierz przynajmniej jeden typ dokumentów!")
            return None

        return {
            "wybrana_firma_nip": nip,
            "data_od": d_od,
            "data_do": d_do,
            "pobieraj_zakupowe": zakupowe,
            "pobieraj_sprzedazowe": sprzedazowe,
            "zapisz_pdf": pdf,
            "zapisz_xml": xml,
        }

    def przerwij_pobieranie(self):
        self.stop_event.set()
        self.przycisk_stop.configure(state="disabled", text="⏳ Przerywanie...")

    def uruchom_w_tle(self):
        parametry = self.odczytaj_parametry()
        if not parametry:
            return

        self.stop_event.clear()
        self.przycisk_start.configure(state="disabled", text="⏳ Trwa pobieranie...")
        self.przycisk_stop.configure(state="normal", text="🛑 Przerwij")
        self.pasek_postepu.set(0.0)

        def callback(nazwa_firmy, aktualna, razem, nowe, pominiete, status_tekst):
            self.after(0, self.aktualizuj_postep, nazwa_firmy, aktualna, razem, nowe, pominiete, status_tekst)

        def zadanie():
            try:
                main.main(progress_callback=callback, stop_event=self.stop_event, **parametry)
            except Exception as e:  # noqa: BLE001
                print(f"\nWystąpił błąd: {e}")
            finally:
                def zakoncz():
                    self.przycisk_start.configure(state="normal", text="🚀 Rozpocznij pobieranie")
                    self.przycisk_stop.configure(state="disabled", text="🛑 Przerwij")
                self.after(0, zakoncz)

        threading.Thread(target=zadanie, daemon=True).start()


if __name__ == "__main__":
    app = AplikacjaKSeF()
    app.mainloop()