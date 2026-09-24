import sys
import threading
import customtkinter as ctk

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

        self.title("Pobieranie faktur KSeF")
        self.geometry("820x650")
        self.minsize(700, 500)

        # 1. Nagłówek okna
        self.etykieta_tytul = ctk.CTkLabel(
            self,
            text="Automatyczne pobieranie faktur KSeF",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        self.etykieta_tytul.pack(pady=(15, 10))

        # 2. Karty podsumowujące (Dashboard)
        self.ramka_kart = ctk.CTkFrame(self, fg_color="transparent")
        self.ramka_kart.pack(fill="x", padx=20, pady=5)
        self.ramka_kart.grid_columnconfigure((0, 1, 2), weight=1)

        # Karta 1: Aktywna firma
        self.karta_firma = ctk.CTkFrame(self.ramka_kart)
        self.karta_firma.grid(row=0, column=0, padx=5, sticky="ew")
        ctk.CTkLabel(self.karta_firma, text="🏢 AKTYWNA FIRMA", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray70").pack(pady=(8, 2))
        self.lbl_firma = ctk.CTkLabel(self.karta_firma, text="Gotowy", font=ctk.CTkFont(size=13, weight="bold"))
        self.lbl_firma.pack(pady=(0, 8), padx=5)

        # Karta 2: Nowe pobrane faktury
        self.karta_nowe = ctk.CTkFrame(self.ramka_kart)
        self.karta_nowe.grid(row=0, column=1, padx=5, sticky="ew")
        ctk.CTkLabel(self.karta_nowe, text="📥 POBRANO NOWYCH", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray70").pack(pady=(8, 2))
        self.lbl_nowe = ctk.CTkLabel(self.karta_nowe, text="0", font=ctk.CTkFont(size=16, weight="bold"), text_color="#2ecc71")
        self.lbl_nowe.pack(pady=(0, 8))

        # Karta 3: Pominięte faktury
        self.karta_pominiete = ctk.CTkFrame(self.ramka_kart)
        self.karta_pominiete.grid(row=0, column=2, padx=5, sticky="ew")
        ctk.CTkLabel(self.karta_pominiete, text="⏭️ POMINIĘTE", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray70").pack(pady=(8, 2))
        self.lbl_pominiete = ctk.CTkLabel(self.karta_pominiete, text="0", font=ctk.CTkFont(size=16, weight="bold"), text_color="#3498db")
        self.lbl_pominiete.pack(pady=(0, 8))

        # 3. Sekcja paska postępu
        self.lbl_status = ctk.CTkLabel(self, text="Kliknij przycisk, aby rozpocząć pracę.", font=ctk.CTkFont(size=12))
        self.lbl_status.pack(pady=(12, 4))

        self.pasek_postepu = ctk.CTkProgressBar(self, height=12)
        self.pasek_postepu.pack(fill="x", padx=25, pady=(0, 10))
        self.pasek_postepu.set(0.0)

        # 4. Przycisk uruchamiania
        self.przycisk_start = ctk.CTkButton(
            self,
            text="🚀 Rozpocznij pobieranie",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=38,
            command=self.uruchom_w_tle,
        )
        self.przycisk_start.pack(pady=5)

        # 5. Okno tekstowe na logi
        self.pole_logow = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=13),
            wrap="word",
            state="disabled",
        )
        self.pole_logow.pack(fill="both", expand=True, padx=20, pady=(10, 15))

        sys.stdout = PrzekierowanieLogow(self.pole_logow)

    def aktualizuj_postep(self, nazwa_firmy, aktualna, razem, nowe, pominiete, status_tekst):
        """Aktualizacja elementów interfejsu wywoływana bezpiecznie w pętli zdarzeń."""
        self.lbl_firma.configure(text=nazwa_firmy[:24] + ("..." if len(nazwa_firmy) > 24 else ""))
        self.lbl_nowe.configure(text=str(nowe))
        self.lbl_pominiete.configure(text=str(pominiete))
        self.lbl_status.configure(text=status_tekst)

        if razem > 0:
            wartosc = min(max(aktualna / razem, 0.0), 1.0)
            self.pasek_postepu.set(wartosc)

    def uruchom_w_tle(self):
        self.przycisk_start.configure(state="disabled", text="⏳ Trwa pobieranie...")
        self.pasek_postepu.set(0.0)

        def callback(nazwa_firmy, aktualna, razem, nowe, pominiete, status_tekst):
            # ctk/tkinter wymaga aktualizacji GUI w głównym wątku przez after()
            self.after(0, self.aktualizuj_postep, nazwa_firmy, aktualna, razem, nowe, pominiete, status_tekst)

        def zadanie():
            try:
                main.main(progress_callback=callback)
            except Exception as e:
                print(f"\nWystąpił błąd: {e}")
            finally:
                self.after(0, lambda: self.przycisk_start.configure(state="normal", text="🚀 Rozpocznij pobieranie"))

        watek = threading.Thread(target=zadanie, daemon=True)
        watek.start()


if __name__ == "__main__":
    app = AplikacjaKSeF()
    app.mainloop()