import os
import subprocess
import sys
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from tkinter import filedialog, messagebox

import customtkinter as ctk
from tkcalendar import DateEntry

import main
import wyszukiwarka_faktur as wf
import zarzadca_ustawien as zu
from excel_exporter import eksportuj_liste_do_csv
from okno_ustawien import OknoUstawien
from optima_exporter import eksportuj_katalog_do_optimy

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("motyw_windows.json")


def stworz_kalendarz(rodzic, default_date):
    """Tworzy DateEntry wizualnie dostosowany do ciemnych kontrolek Windows 11."""
    kal = DateEntry(
        rodzic,
        width=11,
        background="#0078D4",
        foreground="#FFFFFF",
        headersbackground="#1E1E1E",
        headersforeground="#FFFFFF",
        selectbackground="#0078D4",
        selectforeground="#FFFFFF",
        normalbackground="#202020",
        normalforeground="#EDEDED",
        weekendbackground="#262626",
        weekendforeground="#CCCCCC",
        othermonthforeground="#555555",
        othermonthbackground="#1A1A1A",
        date_pattern="yyyy-mm-dd",
        year=default_date.year,
        month=default_date.month,
        day=default_date.day,
    )
    return kal


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

        self.withdraw()

        self.title("Panel Operatora KSeF")
        self.geometry("1120x940")
        self.minsize(980, 780)

        self.stop_event = threading.Event()
        self.konfiguracja = {}
        self.firmy = []
        self.indeks_faktur = {}

        # Paginacja wyszukiwarki
        self.limit_wyswietlania = 40
        self.aktualny_offset_wynikow = 40
        self.ostatnie_wyniki = []
        self.btn_wiecej = None

        # ==========================================
        # 1. Pasek nagłówka (Windows 11 Fluent Header)
        # ==========================================
        self.ramka_naglowka = ctk.CTkFrame(self, fg_color="transparent")
        self.ramka_naglowka.pack(fill="x", padx=22, pady=(16, 6))
        self.ramka_naglowka.grid_columnconfigure(0, weight=1)

        self.ramka_tytulu = ctk.CTkFrame(self.ramka_naglowka, fg_color="transparent")
        self.ramka_tytulu.grid(row=0, column=0, sticky="w")

        self.etykieta_tytul = ctk.CTkLabel(
            self.ramka_tytulu,
            text="Panel Operatora KSeF",
            font=ctk.CTkFont(family="Segoe UI Variable Display", size=22, weight="bold"),
            text_color="#FFFFFF",
        )
        self.etykieta_tytul.pack(side="left")

        self.lbl_podtytul = ctk.CTkLabel(
            self.ramka_tytulu,
            text=" • Centrum pobierania i analizy faktur",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color="#8A8A8A",
        )
        self.lbl_podtytul.pack(side="left", padx=(6, 0), pady=(4, 0))

        self.btn_ustawienia = ctk.CTkButton(
            self.ramka_naglowka,
            text="⚙️ Ustawienia",
            width=130,
            height=34,
            corner_radius=6,
            fg_color="#2B2B2B",
            hover_color="#383838",
            border_width=1,
            border_color="#3D3D3D",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            command=self.otworz_okno_ustawien,
        )
        self.btn_ustawienia.grid(row=0, column=1, sticky="e")

        # ==========================================
        # 2. Główny widok zakładek
        # ==========================================
        self.tabview = ctk.CTkTabview(
            self,
            segmented_button_font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        )
        self.tabview.pack(fill="both", expand=True, padx=20, pady=(2, 16))

        self.tabview.grid_columnconfigure(0, weight=1)
        self.tabview._segmented_button.configure(height=38, corner_radius=8)
        self.tabview._segmented_button.grid(sticky="ew", padx=14, pady=(6, 8))

        self.tab_pobieranie = self.tabview.add("📥  Pobieranie KSeF")
        self.tab_optima = self.tabview.add("📤  Eksport Optima")
        self.tab_szukaj = self.tabview.add("🔍  Wyszukiwarka faktur")

        teraz = datetime.now(timezone.utc)
        data_od_domyslna = teraz - timedelta(days=90)

        # ==========================================
        # ZAKŁADKA 1: POBIERANIE KSeF (Windows 11 Card Style)
        # ==========================================
        self.kontener_pobierania = ctk.CTkFrame(self.tab_pobieranie, fg_color="transparent")
        self.kontener_pobierania.pack(fill="both", expand=True, padx=8, pady=4)

        # Karta 1: Formularz parametrów
        self.karta_pobieranie = ctk.CTkFrame(
            self.kontener_pobierania,
            corner_radius=8,
            border_width=1,
            border_color="#363636",
            fg_color="#252525",
        )
        self.karta_pobieranie.pack(fill="x", padx=4, pady=(2, 8))

        # Wiersz 0: Wybór firmy
        ctk.CTkLabel(
            self.karta_pobieranie,
            text="Podmiot:",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        ).grid(row=0, column=0, padx=(18, 8), pady=(14, 8), sticky="w")

        self.combo_firma = ctk.CTkComboBox(self.karta_pobieranie, values=["WSZYSTKIE"], width=460, height=32)
        self.combo_firma.grid(row=0, column=1, columnspan=3, padx=(0, 18), pady=(14, 8), sticky="w")

        # Wiersz 1: Zakres dat
        ctk.CTkLabel(
            self.karta_pobieranie,
            text="Zakres dat:",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        ).grid(row=1, column=0, padx=(18, 8), pady=8, sticky="w")

        self.ramka_dat_pob = ctk.CTkFrame(self.karta_pobieranie, fg_color="transparent")
        self.ramka_dat_pob.grid(row=1, column=1, columnspan=3, padx=0, pady=8, sticky="w")

        ctk.CTkLabel(self.ramka_dat_pob, text="Od: ", text_color="#A0A0A0").pack(side="left")
        self.kalendarz_od = stworz_kalendarz(self.ramka_dat_pob, data_od_domyslna)
        self.kalendarz_od.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(self.ramka_dat_pob, text="Do: ", text_color="#A0A0A0").pack(side="left")
        self.kalendarz_do = stworz_kalendarz(self.ramka_dat_pob, teraz)
        self.kalendarz_do.pack(side="left")

        # Wiersz 2: Rejestry i Formaty z użyciem pól wyboru (Checkbox)
        ctk.CTkLabel(
            self.karta_pobieranie,
            text="Opcje zapisu:",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        ).grid(row=2, column=0, padx=(18, 8), pady=(8, 14), sticky="w")

        self.ramka_opcji_checks = ctk.CTkFrame(self.karta_pobieranie, fg_color="transparent")
        self.ramka_opcji_checks.grid(row=2, column=1, columnspan=3, padx=0, pady=(8, 14), sticky="w")

        self.chk_zakupowe = ctk.CTkCheckBox(self.ramka_opcji_checks, text="Koszty (Zakup)")
        self.chk_zakupowe.pack(side="left", padx=(0, 16))
        self.chk_zakupowe.select()

        self.chk_sprzedazowe = ctk.CTkCheckBox(self.ramka_opcji_checks, text="Przychody (Sprzedaż)")
        self.chk_sprzedazowe.pack(side="left", padx=(0, 24))

        self.chk_pdf = ctk.CTkCheckBox(self.ramka_opcji_checks, text="Format PDF")
        self.chk_pdf.pack(side="left", padx=(0, 16))
        self.chk_pdf.select()

        self.chk_xml = ctk.CTkCheckBox(self.ramka_opcji_checks, text="Format XML")
        self.chk_xml.pack(side="left")
        self.chk_xml.select()

        # Przyciski akcji
        self.ramka_akcji_pob = ctk.CTkFrame(self.kontener_pobierania, fg_color="transparent")
        self.ramka_akcji_pob.pack(fill="x", padx=4, pady=4)

        self.przycisk_start = ctk.CTkButton(
            self.ramka_akcji_pob,
            text="🚀  Rozpocznij pobieranie",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            height=38,
            width=220,
            command=self.uruchom_w_tle,
        )
        self.przycisk_start.pack(side="left", padx=(0, 8))

        self.przycisk_stop = ctk.CTkButton(
            self.ramka_akcji_pob,
            text="🛑  Przerwij",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            height=38,
            width=130,
            fg_color="#C42B1C",
            hover_color="#A82315",
            state="disabled",
            command=self.przerwij_pobieranie,
        )
        self.przycisk_stop.pack(side="left")

        # Karta 2: Konsola logów w stylu natywnego panelu zdarzeń
        self.karta_logow = ctk.CTkFrame(
            self.kontener_pobierania,
            corner_radius=8,
            border_width=1,
            border_color="#363636",
            fg_color="#202020",
        )
        self.karta_logow.pack(fill="both", expand=True, padx=4, pady=(8, 4))

        self.pasek_tytulu_logow = ctk.CTkFrame(self.karta_logow, fg_color="#282828", height=32, corner_radius=6)
        self.pasek_tytulu_logow.pack(fill="x", padx=4, pady=4)

        self.lbl_status = ctk.CTkLabel(
            self.pasek_tytulu_logow,
            text="● Gotowy do pracy",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#60CDFF",
        )
        self.lbl_status.pack(side="left", padx=10)

        self.pasek_postepu = ctk.CTkProgressBar(self.karta_logow, height=3)
        self.pasek_postepu.pack(fill="x", padx=6, pady=(0, 4))
        self.pasek_postepu.set(0.0)

        self.pole_logow = ctk.CTkTextbox(
            self.karta_logow,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
            state="disabled",
            fg_color="#181818",
            border_width=0,
        )
        self.pole_logow.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        sys.stdout = PrzekierowanieLogow(self.pole_logow)

        # ==========================================
        # ZAKŁADKA 2: EKSPORT OPTIMA (Nowoczesny układ kartowy)
        # ==========================================
        self.ramka_optima = ctk.CTkFrame(
            self.tab_optima,
            corner_radius=8,
            border_width=1,
            border_color="#383838",
            fg_color="#252525",
        )
        self.ramka_optima.pack(fill="x", padx=12, pady=12)

        ctk.CTkLabel(
            self.ramka_optima,
            text="📦 EKSPORT DO COMARCH OPTIMA (OFFLINE XML)",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#0078D4",
        ).grid(row=0, column=0, columnspan=4, padx=18, pady=(16, 12), sticky="w")

        ctk.CTkLabel(self.ramka_optima, text="Firma:", font=ctk.CTkFont(weight="bold")).grid(
            row=1, column=0, padx=18, pady=8, sticky="w"
        )
        self.combo_optima_firma = ctk.CTkComboBox(self.ramka_optima, values=["Wybierz firmę"], width=460, height=32)
        self.combo_optima_firma.grid(row=1, column=1, columnspan=2, padx=12, pady=8, sticky="w")

        ctk.CTkLabel(self.ramka_optima, text="Rejestr:", font=ctk.CTkFont(weight="bold")).grid(
            row=2, column=0, padx=18, pady=8, sticky="w"
        )
        self.var_typ_optima = ctk.StringVar(value="sprzedaz")
        self.rb_sprzedaz = ctk.CTkRadioButton(
            self.ramka_optima, text="Sprzedaż", variable=self.var_typ_optima, value="sprzedaz"
        )
        self.rb_sprzedaz.grid(row=2, column=1, padx=12, pady=8, sticky="w")
        self.rb_zakup = ctk.CTkRadioButton(
            self.ramka_optima, text="Zakup (Koszty)", variable=self.var_typ_optima, value="zakup"
        )
        self.rb_zakup.grid(row=2, column=2, padx=12, pady=8, sticky="w")

        ctk.CTkLabel(self.ramka_optima, text="Okres faktur:", font=ctk.CTkFont(weight="bold")).grid(
            row=3, column=0, padx=18, pady=8, sticky="w"
        )
        self.optima_kal_od = stworz_kalendarz(
            self.ramka_optima, datetime(teraz.year, teraz.month, 1, tzinfo=timezone.utc)
        )
        self.optima_kal_od.grid(row=3, column=1, padx=12, pady=8, sticky="w")

        self.optima_kal_do = stworz_kalendarz(self.ramka_optima, teraz)
        self.optima_kal_do.grid(row=3, column=2, padx=12, pady=8, sticky="w")

        self.var_kryterium_daty = ctk.StringVar(value="sprzedaz")
        self.rb_data_sprzedazy = ctk.CTkRadioButton(
            self.ramka_optima, text="Wg daty wykonania/sprzedaży", variable=self.var_kryterium_daty, value="sprzedaz"
        )
        self.rb_data_sprzedazy.grid(row=4, column=1, padx=12, pady=8, sticky="w")
        self.rb_data_wystawienia = ctk.CTkRadioButton(
            self.ramka_optima, text="Wg daty wystawienia", variable=self.var_kryterium_daty, value="wystawienie"
        )
        self.rb_data_wystawienia.grid(row=4, column=2, padx=12, pady=8, sticky="w")

        self.btn_eksport_optima = ctk.CTkButton(
            self.ramka_optima,
            text="📑  Eksportuj do Optimy",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            height=38,
            fg_color="#107C41",
            hover_color="#0E6B38",
            command=self.wykonaj_eksport_optima,
        )
        self.btn_eksport_optima.grid(row=5, column=1, columnspan=2, padx=12, pady=(18, 16), sticky="ew")

        # ==========================================
        # ZAKŁADKA 3: WYSZUKIWARKA FAKTUR
        # ==========================================
        self.ramka_filtry_szukaj = ctk.CTkFrame(
            self.tab_szukaj, corner_radius=8, border_width=1, border_color="#383838", fg_color="#252525"
        )
        self.ramka_filtry_szukaj.pack(fill="x", padx=12, pady=(8, 6))

        # Rząd 0: Filtry
        ctk.CTkLabel(self.ramka_filtry_szukaj, text="Firma:", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=(14, 4), pady=(10, 4), sticky="w"
        )
        self.combo_szukaj_firma = ctk.CTkComboBox(self.ramka_filtry_szukaj, values=["WSZYSTKIE"], width=230)
        self.combo_szukaj_firma.grid(row=0, column=1, padx=(0, 12), pady=(10, 4), sticky="w")

        ctk.CTkLabel(self.ramka_filtry_szukaj, text="Rejestr:", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=2, padx=(0, 4), pady=(10, 4), sticky="w"
        )
        self.combo_szukaj_rejestr = ctk.CTkComboBox(
            self.ramka_filtry_szukaj, values=["WSZYSTKIE", "zakup", "sprzedaz"], width=130
        )
        self.combo_szukaj_rejestr.grid(row=0, column=3, padx=(0, 12), pady=(10, 4), sticky="w")
        self.combo_szukaj_rejestr.set("WSZYSTKIE")

        ctk.CTkLabel(self.ramka_filtry_szukaj, text="Od:").grid(row=0, column=4, padx=(0, 4), pady=(10, 4), sticky="w")
        self.szukaj_kal_od = stworz_kalendarz(
            self.ramka_filtry_szukaj, datetime(teraz.year, teraz.month, 1, tzinfo=timezone.utc)
        )
        self.szukaj_kal_od.grid(row=0, column=5, padx=(0, 10), pady=(10, 4), sticky="w")

        ctk.CTkLabel(self.ramka_filtry_szukaj, text="Do:").grid(row=0, column=6, padx=(0, 4), pady=(10, 4), sticky="w")
        self.szukaj_kal_do = stworz_kalendarz(self.ramka_filtry_szukaj, teraz)
        self.szukaj_kal_do.grid(row=0, column=7, padx=(0, 10), pady=(10, 4), sticky="w")

        self.chk_wszystkie_daty = ctk.CTkCheckBox(
            self.ramka_filtry_szukaj,
            text="Wszystkie daty",
            command=self._przelacz_filtr_dat,
        )
        self.chk_wszystkie_daty.grid(row=0, column=8, padx=(4, 14), pady=(10, 4), sticky="w")
        self.chk_wszystkie_daty.select()
        self._przelacz_filtr_dat()

        # Rząd 1: Szukanie i akcje
        self.ramka_filtry_szukaj.grid_columnconfigure(0, weight=1)

        self.entry_szukaj_fraza = ctk.CTkEntry(
            self.ramka_filtry_szukaj,
            placeholder_text="Szukaj: nr faktury, NIP, kontrahent...",
            height=34,
        )
        self.entry_szukaj_fraza.grid(row=1, column=0, columnspan=5, padx=(14, 8), pady=(4, 10), sticky="ew")
        self.entry_szukaj_fraza.bind("<Return>", lambda e: self.filtruj_i_wyswietl_faktury())

        self.btn_szukaj_akcja = ctk.CTkButton(
            self.ramka_filtry_szukaj,
            text="🔍  Filtruj",
            width=90,
            height=34,
            command=self.filtruj_i_wyswietl_faktury,
        )
        self.btn_szukaj_akcja.grid(row=1, column=5, padx=4, pady=(4, 10))

        self.btn_odswiez_indeks = ctk.CTkButton(
            self.ramka_filtry_szukaj,
            text="🔄  Indeksuj dysk",
            width=120,
            height=34,
            fg_color="#2B2B2B",
            hover_color="#383838",
            border_width=1,
            border_color="#3D3D3D",
            command=self.przeindeksuj_baze,
        )
        self.btn_odswiez_indeks.grid(row=1, column=6, columnspan=2, padx=4, pady=(4, 10))

        self.btn_eksport_csv = ctk.CTkButton(
            self.ramka_filtry_szukaj,
            text="📊  Eksport do Excel",
            width=150,
            height=34,
            fg_color="#107C41",
            hover_color="#0E6B38",
            command=self.wykonaj_eksport_excel,
        )
        self.btn_eksport_csv.grid(row=1, column=8, padx=(4, 14), pady=(4, 10), sticky="e")

        # Pasek podsumowania (Stat Cards w stylu Fluent Design)
        self.ramka_statystyk = ctk.CTkFrame(self.tab_szukaj, fg_color="transparent")
        self.ramka_statystyk.pack(fill="x", padx=12, pady=(4, 6))

        self.karta_stat_liczba = ctk.CTkFrame(
            self.ramka_statystyk, fg_color="#262626", corner_radius=6, border_width=1, border_color="#353535"
        )
        self.karta_stat_liczba.pack(side="left", padx=(0, 8), pady=2)
        self.lbl_stat_liczba = ctk.CTkLabel(
            self.karta_stat_liczba,
            text="Dokumenty: 0",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            padx=12,
            pady=4,
        )
        self.lbl_stat_liczba.pack()

        self.karta_stat_suma = ctk.CTkFrame(
            self.ramka_statystyk, fg_color="#262626", corner_radius=6, border_width=1, border_color="#353535"
        )
        self.karta_stat_suma.pack(side="left", pady=2)
        self.lbl_stat_suma = ctk.CTkLabel(
            self.karta_stat_suma,
            text="Łącznie brutto: 0,00 PLN",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#57A6FF",
            padx=12,
            pady=4,
        )
        self.lbl_stat_suma.pack()

        self.scroll_wyniki_szukaj = ctk.CTkScrollableFrame(self.tab_szukaj)
        self.scroll_wyniki_szukaj.pack(fill="both", expand=True, padx=12, pady=(2, 8))

        self.after(50, self.przygotuj_srodowisko)

    def _przelacz_filtr_dat(self):
        """Włącza lub blokuje kontrolki wyboru dat w zależności od stanu checkboxa."""
        stan = "disabled" if self.chk_wszystkie_daty.get() else "normal"
        self.szukaj_kal_od.configure(state=stan)
        self.szukaj_kal_do.configure(state=stan)

    def otworz_okno_ustawien(self):
        """Otwiera okno zarządzania firmami i konfiguracją."""
        OknoUstawien(self, on_close_callback=self.odswiez_liste_firm)

    def odswiez_liste_firm(self):
        """Wczytuje listę firm i odświeża kontrolki ComboBox we wszystkich zakładkach."""
        self.konfiguracja = zu.wczytaj_konfiguracje()
        self.firmy = self.konfiguracja.get("firmy", [])

        opcje_pelne = ["WSZYSTKIE"] + [f"{f['nazwa']} (NIP: {f['nip']})" for f in self.firmy]
        opcje_pojedyncze = [f"{f['nazwa']} (NIP: {f['nip']})" for f in self.firmy]

        self.combo_firma.configure(values=opcje_pelne)
        self.combo_firma.set("WSZYSTKIE")

        if opcje_pojedyncze:
            self.combo_optima_firma.configure(values=opcje_pojedyncze)
            self.combo_optima_firma.set(opcje_pojedyncze[0])

        self.combo_szukaj_firma.configure(values=opcje_pelne)
        self.combo_szukaj_firma.set("WSZYSTKIE")

    def przeindeksuj_baze(self):
        """Wymusza odświeżenie indeksu z dysku i aktualizuje widok wyszukiwarki."""
        self.btn_odswiez_indeks.configure(state="disabled", text="⏳ Indeksuję...")
        self.update_idletasks()

        self.indeks_faktur, dodane, usuniete = wf.aktualizuj_indeks(self.konfiguracja)
        self.filtruj_i_wyswietl_faktury()

        self.btn_odswiez_indeks.configure(state="normal", text="🔄  Indeksuj dysk")
        if dodane > 0 or usuniete > 0:
            messagebox.showinfo("Indeks zaktualizowany", f"Nowe dokumenty: {dodane}\nUsunięte z dysku: {usuniete}")

    def filtruj_i_wyswietl_faktury(self):
        """Filtruje zindeksowane faktury i renderuje pierwszą partię wyników."""
        for w in self.scroll_wyniki_szukaj.winfo_children():
            w.destroy()

        wybrana_f = self.combo_szukaj_firma.get()
        nip = "WSZYSTKIE" if wybrana_f == "WSZYSTKIE" else wybrana_f.split("NIP: ")[-1].replace(")", "").strip()
        typ_rej = self.combo_szukaj_rejestr.get()
        fraza = self.entry_szukaj_fraza.get()

        if self.chk_wszystkie_daty.get():
            d_od = ""
            d_do = ""
        else:
            d_od = self.szukaj_kal_od.get_date().strftime("%Y-%m-%d")
            d_do = self.szukaj_kal_do.get_date().strftime("%Y-%m-%d")

        self.ostatnie_wyniki = wf.szukaj_faktur(
            self.indeks_faktur,
            fraza=fraza,
            nip_firmy=nip,
            typ_rejestru=typ_rej,
            data_od=d_od,
            data_do=d_do,
        )

        suma_brutto = sum(item.get("brutto", 0.0) for item in self.ostatnie_wyniki)
        self.lbl_stat_liczba.configure(text=f"Dokumenty: {len(self.ostatnie_wyniki):,}".replace(",", " "))
        self.lbl_stat_suma.configure(text=f"Łącznie brutto: {suma_brutto:,.2f} PLN".replace(",", " "))

        if not self.ostatnie_wyniki:
            ctk.CTkLabel(
                self.scroll_wyniki_szukaj,
                text="Brak faktur spełniających wybrane kryteria wyszukiwania.",
                text_color="gray",
                font=ctk.CTkFont(size=13),
            ).pack(pady=40)
            return

        self.aktualny_offset_wynikow = self.limit_wyswietlania
        self._renderuj_partie_wynikow()

    def _renderuj_partie_wynikow(self):
        """Rysuje partię faktur i dodaje przycisk doładowania kolejnych."""
        if self.btn_wiecej is not None and self.btn_wiecej.winfo_exists():
            self.btn_wiecej.destroy()
            self.btn_wiecej = None

        partia = self.ostatnie_wyniki[: self.aktualny_offset_wynikow]
        obecne_karty = len(self.scroll_wyniki_szukaj.winfo_children())
        for f in partia[obecne_karty:]:
            self._utworz_karte_faktury(f)

        if len(self.ostatnie_wyniki) > self.aktualny_offset_wynikow:
            pozostalo = len(self.ostatnie_wyniki) - self.aktualny_offset_wynikow
            tekst_btn = f"➕  Pokaż kolejne dokumenty (pozostało: {pozostalo})"
            self.btn_wiecej = ctk.CTkButton(
                self.scroll_wyniki_szukaj,
                text=tekst_btn,
                height=36,
                fg_color="#2B2B2B",
                hover_color="#383838",
                border_width=1,
                border_color="#3D3D3D",
                font=ctk.CTkFont(weight="bold"),
                command=self._zaladuj_kolejna_partie,
            )
            self.btn_wiecej.pack(fill="x", padx=8, pady=10)

    def _zaladuj_kolejna_partie(self):
        """Pobiera i wyświetla kolejną partię faktur."""
        self.aktualny_offset_wynikow += self.limit_wyswietlania
        self._renderuj_partie_wynikow()

    def _utworz_karte_faktury(self, f):
        """Tworzy nowoczesną kartę faktury Fluent Item w wynikach wyszukiwania."""
        jest_zakup = f.get("typ_rejestru") == "zakup"
        etykieta_rej = "ZAKUP" if jest_zakup else "SPRZEDAŻ"
        kolor_tekstu_tag = "#60CDFF" if jest_zakup else "#6CCB5F"
        kolor_tla_tag = "#0F2D4A" if jest_zakup else "#0E3A24"
        kolor_ramki_tag = "#1A4971" if jest_zakup else "#1A5C38"

        karta = ctk.CTkFrame(
            self.scroll_wyniki_szukaj,
            corner_radius=8,
            border_width=1,
            border_color="#363636",
            fg_color="#282828",
        )
        karta.pack(fill="x", padx=4, pady=3)
        karta.grid_columnconfigure(1, weight=1)

        def on_enter(e):
            if karta.winfo_exists():
                karta.configure(fg_color="#303030")

        def on_leave(e):
            if karta.winfo_exists():
                karta.configure(fg_color="#282828")

        karta.bind("<Enter>", on_enter)
        karta.bind("<Leave>", on_leave)

        # 1. Pigułka-badge rejestru
        ramka_badge = ctk.CTkFrame(
            karta,
            corner_radius=12,
            border_width=1,
            border_color=kolor_ramki_tag,
            fg_color=kolor_tla_tag,
            width=76,
            height=26,
        )
        ramka_badge.grid(row=0, column=0, rowspan=2, padx=(12, 8), pady=8)
        ramka_badge.pack_propagate(False)

        lbl_badge = ctk.CTkLabel(
            ramka_badge,
            text=etykieta_rej,
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=kolor_tekstu_tag,
        )
        lbl_badge.pack(expand=True)

        # 2. Informacje główne i kontrahent
        tytul = f"{f.get('nr_faktury')}   •   {f.get('kontrahent_nazwa')}"
        ctk.CTkLabel(
            karta,
            text=tytul,
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#F3F3F3",
        ).grid(row=0, column=1, padx=4, pady=(6, 0), sticky="w")

        info_tekst = (
            f"NIP: {f.get('kontrahent_nip', 'Brak')}   |   "
            f"Sprzedaż: {f.get('data_sprzedazy')}   |   "
            f"Wystawienie: {f.get('data_wystawienia')}   |   "
            f"Dla: {f.get('moja_firma_nazwa')}"
        )
        ctk.CTkLabel(
            karta,
            text=info_tekst,
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#999999",
        ).grid(row=1, column=1, padx=4, pady=(0, 6), sticky="w")

        # 3. Kwota brutto
        kwota_str = f"{f.get('brutto', 0.0):,.2f} PLN".replace(",", " ")
        ctk.CTkLabel(
            karta,
            text=kwota_str,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#FFFFFF",
            width=130,
        ).grid(row=0, column=2, rowspan=2, padx=8, pady=8)

        # 4. Przyciski akcji PDF / XML
        ramka_akcji = ctk.CTkFrame(karta, fg_color="transparent")
        ramka_akcji.grid(row=0, column=3, rowspan=2, padx=(4, 12), pady=8)

        sciezka_pdf = f.get("sciezka_pdf")
        btn_pdf = ctk.CTkButton(
            ramka_akcji,
            text="PDF",
            width=48,
            height=28,
            corner_radius=4,
            fg_color="#0078D4",
            hover_color="#1084D9",
            state="normal" if (sciezka_pdf and os.path.exists(sciezka_pdf)) else "disabled",
            command=lambda p=sciezka_pdf: self._otworz_plik(p),
        )
        btn_pdf.pack(side="left", padx=3)

        sciezka_xml = f.get("sciezka_xml")
        btn_xml = ctk.CTkButton(
            ramka_akcji,
            text="XML",
            width=48,
            height=28,
            corner_radius=4,
            fg_color="#383838",
            hover_color="#454545",
            border_width=1,
            border_color="#4D4D4D",
            state="normal" if (sciezka_xml and os.path.exists(sciezka_xml)) else "disabled",
            command=lambda p=sciezka_xml: self._otworz_plik(p),
        )
        btn_xml.pack(side="left", padx=3)

    def _otworz_plik(self, sciezka):
        """Otwiera skojarzony plik PDF lub XML w domyślnym programie systemowym."""
        if not sciezka or not os.path.exists(sciezka):
            messagebox.showerror("Brak pliku", "Wskazany plik nie istnieje na dysku.")
            return

        try:
            if sys.platform == "win32":
                os.startfile(sciezka)
            else:
                subprocess.run(["xdg-open", sciezka], check=False)
        except OSError as e:
            messagebox.showerror("Błąd otwarcia", f"Nie udało się otworzyć pliku:\n{e}")

    def przygotuj_srodowisko(self):
        """Weryfikuje strukturę folderów, wczytuje indeks i odświeża GUI."""
        if not os.path.exists(zu.PLIK_USTAWIEN):
            decyzja = messagebox.askyesno(
                "Pierwsza konfiguracja",
                "Gdzie chcesz przechowywać pliki pobrane z KSeF?\n\n"
                "• Kliknij [Tak], aby utworzyć domyślny folder KSeF na Pulpicie.\n"
                "• Kliknij [Nie], aby wskazać własną lokalizację na dysku.",
            )
            if decyzja:
                folder_glowny = zu.pobierz_domyslny_katalog()
            else:
                wybrany = filedialog.askdirectory(title="Wskaż folder bazowy dla plików KSeF")
                folder_glowny = wybrany if wybrany else zu.pobierz_domyslny_katalog()

            firmy = zu.migruj_ze_starego_configu()
            self.konfiguracja = {"folder_glowny": folder_glowny, "firmy": firmy}
            zu.zapisz_konfiguracje(self.konfiguracja)
            zu.utworz_strukture_katalogow(folder_glowny, firmy)
        else:
            self.konfiguracja = zu.wczytaj_konfiguracje()

        folder_glowny = self.konfiguracja.get("folder_glowny", zu.pobierz_domyslny_katalog())
        self.firmy = self.konfiguracja.get("firmy", [])

        wynik = zu.sprawdz_integralnosc(folder_glowny, self.firmy)
        if not wynik["poprawny"]:
            odtworz = messagebox.askyesno(
                "Wykryto brak folderów",
                f"Brakuje {wynik['liczba_brakow']} folderów dla skonfigurowanych firm.\n\n"
                "Czy chcesz je teraz automatycznie utworzyć na dysku?",
            )
            if odtworz:
                zu.utworz_strukture_katalogow(folder_glowny, self.firmy)

        self.odswiez_liste_firm()

        # Załadowanie i synchronizacja bazy indeksu
        self.indeks_faktur, _, _ = wf.aktualizuj_indeks(self.konfiguracja)
        self.filtruj_i_wyswietl_faktury()

        self.deiconify()

    def wykonaj_eksport_optima(self):
        wybrana = self.combo_optima_firma.get()
        if not wybrana or wybrana == "Wybierz firmę":
            messagebox.showwarning(
                "Wybierz firmę",
                "Wybierz konkretną firmę z listy rozwijanej!",
            )
            return

        nip = wybrana.split("NIP: ")[-1].replace(")", "").strip()
        znaleziona_firma = next((f for f in self.firmy if str(f["nip"]).strip() == nip), None)
        if not znaleziona_firma:
            messagebox.showerror("Błąd", "Nie znaleziono wybranej firmy w konfiguracji.")
            return

        typ_rejestru = self.var_typ_optima.get()
        folder_glowny = self.konfiguracja.get("folder_glowny", zu.pobierz_domyslny_katalog())
        folder_zrodlowy = zu.pobierz_sciezke_firmy(folder_glowny, nip, f"{typ_rejestru}_xml")

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
                messagebox.showinfo("Sukces", f"Pomyślnie wyeksportowano {liczba} faktur do pliku:\n{sciezka_zapisu}")
            else:
                messagebox.showwarning("Brak faktur", "W wybranym folderze i zakresie dat nie odnaleziono faktur.")
        except (OSError, ET.ParseError, ValueError) as e:
            messagebox.showerror("Błąd eksportu", f"Wystąpił błąd:\n{e}")

    def wykonaj_eksport_excel(self):
        """Wywołuje dedykowany moduł eksportujący aktualnie odfiltrowane faktury do CSV."""
        eksportuj_liste_do_csv(self.ostatnie_wyniki)

    def aktualizuj_postep(self, nazwa_firmy, aktualna, razem, nowe, pominiete, status_tekst):
        self.lbl_status.configure(text=f"● {nazwa_firmy}: {status_tekst}")
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
                main.main(
                    progress_callback=callback,
                    stop_event=self.stop_event,
                    konfiguracja=self.konfiguracja,
                    **parametry,
                )
            except Exception as e:  # noqa: BLE001
                print(f"\nWystąpił błąd: {e}")
            finally:
                def zakoncz():
                    self.przycisk_start.configure(state="normal", text="🚀  Rozpocznij pobieranie")
                    self.przycisk_stop.configure(state="disabled", text="🛑  Przerwij")
                    self.indeks_faktur, _, _ = wf.aktualizuj_indeks(self.konfiguracja)
                    self.filtruj_i_wyswietl_faktury()

                self.after(0, zakoncz)

        threading.Thread(target=zadanie, daemon=True).start()


if __name__ == "__main__":
    app = AplikacjaKSeF()
    app.mainloop()