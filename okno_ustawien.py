from tkinter import filedialog, messagebox

import customtkinter as ctk

import zarzadca_ustawien as zu


class OknoUstawien(ctk.CTkToplevel):
    def __init__(self, parent, on_close_callback=None):
        super().__init__(parent)
        self.parent = parent
        self.on_close_callback = on_close_callback

        self.title("⚙️ Ustawienia i Zarządzanie Firmami")
        self.geometry("860x560")
        self.minsize(800, 500)

        self.transient(parent)
        self.grab_set()

        self.konfiguracja = zu.wczytaj_konfiguracje()
        self.aktywny_nip = None
        self.token_widoczny = False

        self._zbuduj_interfejs()
        self._odswiez_liste_firm()

    def _zbuduj_interfejs(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # LEWA KOLUMNA
        self.ramka_lewa = ctk.CTkFrame(self)
        self.ramka_lewa.grid(row=0, column=0, padx=(15, 8), pady=15, sticky="nsew")
        self.ramka_lewa.grid_rowconfigure(1, weight=1)
        self.ramka_lewa.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.ramka_lewa,
            text="🏢 Lista zdefiniowanych firm",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, padx=12, pady=(12, 6), sticky="w")

        self.scroll_firmy = ctk.CTkScrollableFrame(self.ramka_lewa)
        self.scroll_firmy.grid(row=1, column=0, padx=10, pady=4, sticky="nsew")

        ramka_akcji_firm = ctk.CTkFrame(self.ramka_lewa, fg_color="transparent")
        ramka_akcji_firm.grid(row=2, column=0, padx=10, pady=(8, 12), sticky="ew")
        ramka_akcji_firm.grid_columnconfigure((0, 1), weight=1)

        self.btn_nowa_firma = ctk.CTkButton(
            ramka_akcji_firm,
            text="➕ Nowa firma",
            font=ctk.CTkFont(weight="bold"),
            command=self._wyczysc_formularz,
        )
        self.btn_nowa_firma.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        self.btn_usun_firme = ctk.CTkButton(
            ramka_akcji_firm,
            text="🗑️ Usuń",
            fg_color="#c0392b",
            hover_color="#962d22",
            font=ctk.CTkFont(weight="bold"),
            command=self._usun_firme,
        )
        self.btn_usun_firme.grid(row=0, column=1, padx=(4, 0), sticky="ew")

        # PRAWA KOLUMNA
        self.ramka_prawa = ctk.CTkFrame(self)
        self.ramka_prawa.grid(row=0, column=1, padx=(8, 15), pady=15, sticky="nsew")
        self.ramka_prawa.grid_columnconfigure(1, weight=1)

        self.lbl_naglowek_form = ctk.CTkLabel(
            self.ramka_prawa,
            text="📝 Dodawanie nowej firmy",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.lbl_naglowek_form.grid(row=0, column=0, columnspan=2, padx=12, pady=(12, 10), sticky="w")

        ctk.CTkLabel(self.ramka_prawa, text="Nazwa:").grid(row=1, column=0, padx=(12, 6), pady=6, sticky="w")
        self.entry_nazwa = ctk.CTkEntry(self.ramka_prawa, placeholder_text="np. Moja Firma Sp. z o.o.")
        self.entry_nazwa.grid(row=1, column=1, padx=(0, 12), pady=6, sticky="ew")

        ctk.CTkLabel(self.ramka_prawa, text="NIP:").grid(row=2, column=0, padx=(12, 6), pady=6, sticky="w")
        self.entry_nip = ctk.CTkEntry(self.ramka_prawa, placeholder_text="np. 1234567890")
        self.entry_nip.grid(row=2, column=1, padx=(0, 12), pady=6, sticky="ew")

        ctk.CTkLabel(self.ramka_prawa, text="Token:").grid(row=3, column=0, padx=(12, 6), pady=6, sticky="w")
        ramka_token = ctk.CTkFrame(self.ramka_prawa, fg_color="transparent")
        ramka_token.grid(row=3, column=1, padx=(0, 12), pady=6, sticky="ew")
        ramka_token.grid_columnconfigure(0, weight=1)

        self.entry_token = ctk.CTkEntry(ramka_token, show="*", placeholder_text="Wklej token KSeF")
        self.entry_token.grid(row=0, column=0, sticky="ew")

        self.btn_pokaz_token = ctk.CTkButton(
            ramka_token,
            text="👁️",
            width=36,
            command=self._przelacz_widok_tokenu,
        )
        self.btn_pokaz_token.grid(row=0, column=1, padx=(6, 0))

        ramka_przyciski_form = ctk.CTkFrame(self.ramka_prawa, fg_color="transparent")
        ramka_przyciski_form.grid(row=4, column=0, columnspan=2, padx=12, pady=(10, 15), sticky="ew")
        ramka_przyciski_form.grid_columnconfigure((0, 1), weight=1)

        self.btn_zapisz = ctk.CTkButton(
            ramka_przyciski_form,
            text="💾 Zapisz firmę",
            fg_color="#27ae60",
            hover_color="#1e8449",
            font=ctk.CTkFont(weight="bold"),
            command=self._zapisz_firme,
        )
        self.btn_zapisz.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        self.btn_testuj = ctk.CTkButton(
            ramka_przyciski_form,
            text="📡 Testuj KSeF",
            fg_color="#005FB8",
            hover_color="#106EBE",
            font=ctk.CTkFont(weight="bold"),
            command=self._testuj_ksef,
        )
        self.btn_testuj.grid(row=0, column=1, padx=(4, 0), sticky="ew")

        ctk.CTkFrame(self.ramka_prawa, height=2, fg_color=["#E5E5E5", "#383838"]).grid(
            row=5, column=0, columnspan=2, padx=12, pady=10, sticky="ew"
        )

        ctk.CTkLabel(
            self.ramka_prawa,
            text="📁 Folder bazowy KSeF",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=6, column=0, columnspan=2, padx=12, pady=(4, 4), sticky="w")

        ramka_sciezki = ctk.CTkFrame(self.ramka_prawa, fg_color="transparent")
        ramka_sciezki.grid(row=7, column=0, columnspan=2, padx=12, pady=4, sticky="ew")
        ramka_sciezki.grid_columnconfigure(0, weight=1)

        self.entry_folder = ctk.CTkEntry(ramka_sciezki)
        self.entry_folder.insert(0, self.konfiguracja.get("folder_glowny", ""))
        self.entry_folder.configure(state="disabled")
        self.entry_folder.grid(row=0, column=0, sticky="ew")

        self.btn_zmien_folder = ctk.CTkButton(
            ramka_sciezki,
            text="Zmień",
            width=65,
            command=self._zmien_folder_glowny,
        )
        self.btn_zmien_folder.grid(row=0, column=1, padx=(6, 0))

        self.btn_integralnosc = ctk.CTkButton(
            self.ramka_prawa,
            text="🔍 Sprawdź integralność katalogów",
            fg_color=["#5A5A5A", "#3A3A3A"],
            hover_color=["#4A4A4A", "#4A4A4A"],
            command=self._sprawdz_integralnosc,
        )
        self.btn_integralnosc.grid(row=8, column=0, columnspan=2, padx=12, pady=(12, 12), sticky="ew")

        self.protocol("WM_DELETE_WINDOW", self._zamknij_okno)

    def _przelacz_widok_tokenu(self):
        self.token_widoczny = not self.token_widoczny
        self.entry_token.configure(show="" if self.token_widoczny else "*")
        self.btn_pokaz_token.configure(text="🔒" if self.token_widoczny else "👁️")

    def _odswiez_liste_firm(self):
        for widget in self.scroll_firmy.winfo_children():
            widget.destroy()

        firmy = self.konfiguracja.get("firmy", [])
        if not firmy:
            lbl = ctk.CTkLabel(
                self.scroll_firmy,
                text="Brak skonfigurowanych firm.\nKliknij 'Nowa firma', aby dodać.",
                text_color="gray",
            )
            lbl.pack(pady=20)
            return

        for firma in firmy:
            nazwa = firma.get("nazwa", "")
            nip = str(firma.get("nip", "")).strip()
            jest_aktywna = (nip == self.aktywny_nip)

            kolor_ramki = ["#005FB8", "#0078D4"] if jest_aktywna else ["#E5E5E5", "#2B2B2B"]
            kolor_tekstu_nazwa = "#FFFFFF" if jest_aktywna else ["#1F1F1F", "#F3F3F3"]
            kolor_tekstu_nip = "#E0E0E0" if jest_aktywna else ["#555555", "#A0A0A0"]

            karta = ctk.CTkFrame(
                self.scroll_firmy,
                fg_color=kolor_ramki,
                corner_radius=6,
                cursor="hand2",
            )
            karta.pack(fill="x", padx=4, pady=3)

            lbl_nazwa = ctk.CTkLabel(
                karta,
                text=nazwa,
                anchor="w",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=kolor_tekstu_nazwa,
            )
            lbl_nazwa.pack(fill="x", padx=10, pady=(6, 0))

            lbl_nip = ctk.CTkLabel(
                karta,
                text=f"NIP: {nip}",
                anchor="w",
                font=ctk.CTkFont(size=11),
                text_color=kolor_tekstu_nip,
            )
            lbl_nip.pack(fill="x", padx=10, pady=(0, 6))

            for w in (karta, lbl_nazwa, lbl_nip):
                w.bind("<Button-1>", lambda e, f=firma: self._zaladuj_firme_do_edycji(f))

    def _wyczysc_formularz(self):
        self.aktywny_nip = None
        self.lbl_naglowek_form.configure(text="📝 Dodawanie nowej firmy")
        self.entry_nazwa.delete(0, "end")
        self.entry_nip.delete(0, "end")
        self.entry_token.delete(0, "end")
        self._odswiez_liste_firm()

    def _zaladuj_firme_do_edycji(self, firma):
        self.aktywny_nip = str(firma.get("nip", "")).strip()
        self.lbl_naglowek_form.configure(text=f"✏️ Edycja: {firma.get('nazwa', '')}")

        self.entry_nazwa.delete(0, "end")
        self.entry_nazwa.insert(0, firma.get("nazwa", ""))

        self.entry_nip.delete(0, "end")
        self.entry_nip.insert(0, self.aktywny_nip)

        self.entry_token.delete(0, "end")
        self.entry_token.insert(0, firma.get("token", ""))

        self._odswiez_liste_firm()

    def _zapisz_firme(self):
        nazwa = self.entry_nazwa.get().strip()
        nip = self.entry_nip.get().strip()
        token = self.entry_token.get().strip()

        if not nazwa or not nip or not token:
            messagebox.showwarning("Brakujące dane", "Wszystkie pola muszą być wypełnione!")
            return

        if self.aktywny_nip is None:
            sukces, komunikat = zu.dodaj_firme(self.konfiguracja, nazwa, nip, token)
        else:
            sukces, komunikat = zu.edytuj_firme(self.konfiguracja, self.aktywny_nip, nazwa, nip, token)

        if sukces:
            messagebox.showinfo("Sukces", komunikat)
            self.aktywny_nip = nip
            self._odswiez_liste_firm()
        else:
            messagebox.showerror("Błąd", komunikat)

    def _usun_firme(self):
        if not self.aktywny_nip:
            messagebox.showwarning("Wybierz firmę", "Wybierz firmę z listy po lewej stronie, którą chcesz usunąć.")
            return

        potwierdzenie = messagebox.askyesno(
            "Potwierdzenie usunięcia",
            f"Czy na pewno chcesz usunąć firmę o NIP {self.aktywny_nip} z konfiguracji?\n\n"
            "Uwaga: Pliki i pobrane faktury na dysku pozostaną nienaruszone.",
        )
        if potwierdzenie:
            sukces, komunikat = zu.usun_firme(self.konfiguracja, self.aktywny_nip)
            if sukces:
                messagebox.showinfo("Usunięto", komunikat)
                self._wyczysc_formularz()
            else:
                messagebox.showerror("Błąd", komunikat)

    def _testuj_ksef(self):
        nip = self.entry_nip.get().strip()
        token = self.entry_token.get().strip()

        if not nip or not token:
            messagebox.showwarning("Brakujące dane", "Wpisz NIP oraz Token KSeF, aby przetestować połączenie.")
            return

        self.btn_testuj.configure(state="disabled", text="⏳ Testowanie...")
        self.update_idletasks()

        sukces, komunikat = zu.testuj_polaczenie(nip, token)

        self.btn_testuj.configure(state="normal", text="📡 Testuj KSeF")
        if sukces:
            messagebox.showinfo("Sukces połączenia", komunikat)
        else:
            messagebox.showerror("Błąd KSeF", komunikat)

    def _zmien_folder_glowny(self):
        wybrany = filedialog.askdirectory(title="Wybierz nowy folder bazowy KSeF")
        if wybrany:
            self.konfiguracja["folder_glowny"] = wybrany
            zu.zapisz_konfiguracje(self.konfiguracja)
            zu.utworz_strukture_katalogow(wybrany, self.konfiguracja.get("firmy", []))

            self.entry_folder.configure(state="normal")
            self.entry_folder.delete(0, "end")
            self.entry_folder.insert(0, wybrany)
            self.entry_folder.configure(state="disabled")

            messagebox.showinfo("Zapisano", f"Zmieniono folder bazowy na:\n{wybrany}")

    def _sprawdz_integralnosc(self):
        folder_glowny = self.konfiguracja.get("folder_glowny", zu.pobierz_domyslny_katalog())
        firmy = self.konfiguracja.get("firmy", [])

        wynik = zu.sprawdz_integralnosc(folder_glowny, firmy)
        if wynik["poprawny"]:
            messagebox.showinfo("Integralność", "✅ Wszystkie katalogi i podkatalogi istnieją na dysku!")
        else:
            odtworz = messagebox.askyesno(
                "Wykryto braki",
                f"Wykryto brak {wynik['liczba_brakow']} folderów.\n"
                "Czy chcesz je teraz automatycznie odtworzyć?",
            )
            if odtworz:
                zu.utworz_strukture_katalogow(folder_glowny, firmy)
                messagebox.showinfo("Naprawiono", "Katalogi zostały pomyślnie utworzone!")

    def _zamknij_okno(self):
        if self.on_close_callback:
            self.on_close_callback()
        self.destroy()