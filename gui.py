from datetime import datetime, timedelta, timezone
import sys
import threading
import customtkinter as ctk
from tkcalendar import DateEntry

from config import FIRMY
import main

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class PrzekierowanieLogow:
    """Klasa przekierowująca strumień print() do pola tekstowego w GUI."""

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

        self.title("Panel Operatora KSeF - Pobieranie Faktur")
        self.geometry("860x780")
        self.minsize(750, 600)

        self.stop_event = threading.Event()

        # 1. Nagłówek
        self.etykieta_tytul = ctk.CTkLabel(
            self,
            text="Panel Operatora KSeF",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        self.etykieta_tytul.pack(pady=(12, 6))

        # 2. Panel filtrów i opcji
        self.ramka_opcji = ctk.CTkFrame(self)
        self.ramka_opcji.pack(fill="x", padx=20, pady=5)

        # Wiersz 1: Wybór firmy
        ctk.CTkLabel(self.ramka_opcji, text="Wybierz firmę:", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=10, pady=8, sticky="w"
        )
        self.opcje_firm = ["WSZYSTKIE"] + [f"{f['nazwa']} (NIP: {f['nip']})" for f in FIRMY]
        self.combo_firma = ctk.CTkComboBox(self.ramka_opcji, values=self.opcje_firm, width=420)
        self.combo_firma.grid(row=0, column=1, columnspan=3, padx=10, pady=8, sticky="w")
        self.combo_firma.set("WSZYSTKIE")

        # Wiersz 2: Zakres dat (Kalendarze DateEntry)
        teraz = datetime.now()
        data_od_domyslna = teraz - timedelta(days=90)

        ctk.CTkLabel(self.ramka_opcji, text="Data od:", font=ctk.CTkFont(weight="bold")).grid(
            row=1, column=0, padx=10, pady=8, sticky="w"
        )
        self.kalendarz_od = DateEntry(
            self.ramka_opcji,
            width=14,
            background="#1f538d",
            foreground="white",
            headersbackground="#14375e",
            headersforeground="white",
            date_pattern="yyyy-mm-dd",
            year=data_od_domyslna.year,
            month=data_od_domyslna.month,
            day=data_od_domyslna.day,
        )
        self.kalendarz_od.grid(row=1, column=1, padx=10, pady=8, sticky="w")

        ctk.CTkLabel(self.ramka_opcji, text="Data do:", font=ctk.CTkFont(weight="bold")).grid(
            row=1, column=2, padx=10, pady=8, sticky="w"
        )
        self.kalendarz_do = DateEntry(
            self.ramka_opcji,
            width=14,
            background="#1f538d",
            foreground="white",
            headersbackground="#14375e",
            headersforeground="white",
            date_pattern="yyyy-mm-dd",
            year=teraz.year,
            month=teraz.month,
            day=teraz.day,
        )
        self.kalendarz_do.grid(row=1, column=3, padx=10, pady=8, sticky="w")

        # Wiersz 3: Typ dokumentów
        ctk.CTkLabel(self.ramka_opcji, text="Zakres dokumentów:", font=ctk.CTkFont(weight="bold")).grid(
            row=2, column=0, padx=10, pady=8, sticky="w"
        )
        self.chk_zakupowe = ctk.CTkCheckBox(self.ramka_opcji, text="Zakupowe (Koszty)")
        self.chk_zakupowe.grid(row=2, column=1, padx=10, pady=8, sticky="w")
        self.chk_zakupowe.select()

        self.chk_sprzedazowe = ctk.CTkCheckBox(self.ramka_opcji, text="Sprzedażowe (Przychody)")
        self.chk_sprzedazowe.grid(row=2, column=2, columnspan=2, padx=10, pady=8, sticky="w")

        # Wiersz 4: Formaty zapisu
        ctk.CTkLabel(self.ramka_opcji, text="Format zapisu:", font=ctk.CTkFont(weight="bold")).grid(
            row=3, column=0, padx=10, pady=8, sticky="w"
        )
        self.chk_pdf = ctk.CTkCheckBox(self.ramka_opcji, text="Zapisz PDF")
        self.chk_pdf.grid(row=3, column=1, padx=10, pady=8, sticky="w")
        self.chk_pdf.select()

        self.chk_xml = ctk.CTkCheckBox(self.ramka_opcji, text="Zapisz XML")
        self.chk_xml.grid(row=3, column=2, columnspan=2, padx=10, pady=8, sticky="w")

        # 3. Karty podsumowujące (Dashboard)
        self.ramka_kart = ctk.CTkFrame(self, fg_color="transparent")
        self.ramka_kart.pack(fill="x", padx=20, pady=5)
        self.ramka_kart.grid_columnconfigure((0, 1, 2), weight=1)

        self.karta_firma = ctk.CTkFrame(self.ramka_kart)
        self.karta_firma.grid(row=0, column=0, padx=5, sticky="ew")
        ctk.CTkLabel(self.karta_firma, text="🏢 AKTYWNA FIRMA", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray70").pack(pady=(6, 2))
        self.lbl_firma = ctk.CTkLabel(self.karta_firma, text="Gotowy", font=ctk.CTkFont(size=13, weight="bold"))
        self.lbl_firma.pack(pady=(0, 6), padx=5)

        self.karta_nowe = ctk.CTkFrame(self.ramka_kart)
        self.karta_nowe.grid(row=0, column=1, padx=5, sticky="ew")
        ctk.CTkLabel(self.karta_nowe, text="📥 POBRANO NOWYCH", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray70").pack(pady=(6, 2))
        self.lbl_nowe = ctk.CTkLabel(self.karta_nowe, text="0", font=ctk.CTkFont(size=16, weight="bold"), text_color="#2ecc71")
        self.lbl_nowe.pack(pady=(0, 6))

        self.karta_pominiete = ctk.CTkFrame(self.ramka_kart)
        self.karta_pominiete.grid(row=0, column=2, padx=5, sticky="ew")
        ctk.CTkLabel(self.karta_pominiete, text="⏭️ POMINIĘTE", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray70").pack(pady=(6, 2))
        self.lbl_pominiete = ctk.CTkLabel(self.karta_pominiete, text="0", font=ctk.CTkFont(size=16, weight="bold"), text_color="#3498db")
        self.lbl_pominiete.pack(pady=(0, 6))

        # 4. Status i pasek postępu
        self.lbl_status = ctk.CTkLabel(self, text="Wybierz parametry i kliknij przycisk poniżej.", font=ctk.CTkFont(size=12))
        self.lbl_status.pack(pady=(8, 2))

        self.pasek_postepu = ctk.CTkProgressBar(self, height=10)
        self.pasek_postepu.pack(fill="x", padx=25, pady=(0, 8))
        self.pasek_postepu.set(0.0)

        # 5. Przyciski sterujące (Start i Przerwij)
        self.ramka_przyciskow = ctk.CTkFrame(self, fg_color="transparent")
        self.ramka_przyciskow.pack(pady=4)

        self.przycisk_start = ctk.CTkButton(
            self.ramka_przyciskow,
            text="🚀 Rozpocznij pobieranie",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=36,
            width=220,
            command=self.uruchom_w_tle,
        )
        self.przycisk_start.pack(side="left", padx=10)

        self.przycisk_stop = ctk.CTkButton(
            self.ramka_przyciskow,
            text="🛑 Przerwij",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=36,
            width=160,
            fg_color="#c0392b",
            hover_color="#962d22",
            state="disabled",
            command=self.przerwij_pobieranie,
        )
        self.przycisk_stop.pack(side="left", padx=10)

        # 6. Okno tekstowe na logi
        self.pole_logow = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
            state="disabled",
        )
        self.pole_logow.pack(fill="both", expand=True, padx=20, pady=(8, 12))

        sys.stdout = PrzekierowanieLogow(self.pole_logow)

    def aktualizuj_postep(self, nazwa_firmy, aktualna, razem, nowe, pominiete, status_tekst):
        self.lbl_firma.configure(text=nazwa_firmy[:24] + ("..." if len(nazwa_firmy) > 24 else ""))
        self.lbl_nowe.configure(text=str(nowe))
        self.lbl_pominiete.configure(text=str(pominiete))
        self.lbl_status.configure(text=status_tekst)

        if razem > 0:
            wartosc = min(max(aktualna / razem, 0.0), 1.0)
            self.pasek_postepu.set(wartosc)

    def odczytaj_parametry(self):
        wybrana = self.combo_firma.get()
        if wybrana == "WSZYSTKIE":
            nip = "WSZYSTKIE"
        else:
            nip = wybrana.split("NIP: ")[-1].replace(")", "").strip()

        data_od_date = self.kalendarz_od.get_date()
        data_do_date = self.kalendarz_do.get_date()

        d_od = datetime.combine(data_od_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        d_do = datetime.combine(data_do_date, datetime.max.time().replace(microsecond=0)).replace(tzinfo=timezone.utc)

        if d_od > d_do:
            print("❌ Błąd: Data początkowa nie może być późniejsza niż data końcowa!")
            return None

        roznica_dni = (data_do_date - data_od_date).days
        if roznica_dni > 90:
            print(f"❌ Błąd limitu KSeF: Wybrany zakres to {roznica_dni} dni! Maksymalny dozwolony zakres to 90 dni.")
            return None

        zakupowe = bool(self.chk_zakupowe.get())
        sprzedazowe = bool(self.chk_sprzedazowe.get())
        pdf = bool(self.chk_pdf.get())
        xml = bool(self.chk_xml.get())

        if not zakupowe and not sprzedazowe:
            print("❌ Wybierz przynajmniej jeden typ dokumentów (zakupowe lub sprzedażowe)!")
            return None

        if not pdf and not xml:
            print("❌ Wybierz przynajmniej jeden format zapisu (PDF lub XML)!")
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
        self.lbl_status.configure(text="Zatrzymywanie procesu...")

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
            except Exception as e:
                print(f"\nWystąpił błąd: {e}")
            finally:
                def zakoncz():
                    self.przycisk_start.configure(state="normal", text="🚀 Rozpocznij pobieranie")
                    self.przycisk_stop.configure(state="disabled", text="🛑 Przerwij")
                self.after(0, zakoncz)

        watek = threading.Thread(target=zadanie, daemon=True)
        watek.start()


if __name__ == "__main__":
    app = AplikacjaKSeF()
    app.mainloop()