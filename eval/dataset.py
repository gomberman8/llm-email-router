from dataclasses import dataclass

from app.agent.departments import Department


@dataclass
class Case:
    message: str
    expected: Department


CASES: list[Case] = [
    # --- kadry ---
    Case(
        message="Chciałbym złożyć wniosek o urlop wypoczynkowy od 14 do 25 sierpnia. Jak to zrobić przez system?",
        expected=Department.KADRY,
    ),
    Case(
        message="Dzisiaj rano dostałem L4 na tydzień. Co muszę dostarczyć i do kiedy?",
        expected=Department.KADRY,
    ),
    Case(
        message="Na pasku za czerwiec mam o 200 zł za mało. Proszę o wyjaśnienie skąd ta różnica.",
        expected=Department.KADRY,
    ),
    Case(
        message="Potrzebuje zaswiadczenie o zatrudnieniu do banku, biore kredyt hipoteczny. Ile to trwa i co muszę podać?",
        expected=Department.KADRY,
    ),
    Case(
        message="Kiedy dostane PIT-11 za poprzedni rok? Potrzebuje do rozliczenia z urzedem skarbowym, termin mija za 2 tygodnie.",
        expected=Department.KADRY,
    ),
    Case(
        message="Muszę podpisać aneks do umowy o pracę — podobno były zmiany w warunkach wynagrodzenia. Do kogo się zgłosić i gdzie to zrobić?",
        expected=Department.KADRY,
    ),
    # --- human-resources ---
    Case(
        message="Jestem nową osobą w firmie (zaczęłam w tym tygodniu) i nie wiem do kogo się zgłosić. Nikt mnie nie przywitał ani nie powiedział gdzie mam siedzieć. Trochę zagubiona.",
        expected=Department.HUMAN_RESOURCES,
    ),
    Case(
        message="Interesuje mnie kurs z Excela zaawansowanego lub Power BI. Czy firma oferuje dofinansowanie szkoleń i jak złożyć taki wniosek?",
        expected=Department.HUMAN_RESOURCES,
    ),
    Case(
        message="Mam coraz poważniejszy problem z relacjami w zespole. Jeden z kolegów regularnie mnie ignoruje i podważa moje decyzje na spotkaniach. Nie wiem jak to rozwiązać.",
        expected=Department.HUMAN_RESOURCES,
    ),
    Case(
        message="Pracuję tu już 4 lata i zastanawiam się nad awansem. Czy są jakieś ścieżki kariery lub programy rozwojowe? Do kogo powinienem się zgłosić?",
        expected=Department.HUMAN_RESOURCES,
    ),
    # --- help-desk ---
    Case(
        message="Drukarka przy moim stanowisku (HP LaserJet, sala 204) od rana wyświetla błąd 'paper jam', ale papieru nie ma. Wyłączałem i włączałem, nie pomogło.",
        expected=Department.HELP_DESK,
    ),
    Case(
        message="Excel zawiesza mi sie za kazdym razem jak otwieram plik ~50MB. Mam deadline dzis po poludniu, bardzo pilne!",
        expected=Department.HELP_DESK,
    ),
    Case(
        message="Nie pamiętam hasła do konta w domenie. Jak mogę je zresetować?",
        expected=Department.HELP_DESK,
    ),
    Case(
        message="Myszka bezprzewodowa przestała działać w środku dnia. Baterie są nowe, sprawdziłem. Mogę dostać zastępczą albo żeby ktoś spojrzał?",
        expected=Department.HELP_DESK,
    ),
    Case(
        message="Outlook wyrzuca mi błąd 'authentication failed' i nie mogę się zalogować. Inne osoby w biurze logują się normalnie więc to chyba mój komputer.",
        expected=Department.HELP_DESK,
    ),
    # --- it ---
    Case(
        message="Od ok. 10:00 cały nasz dział (ok. 20 osób) nie ma dostępu do internetu. Dotyczy całego skrzydła B, 2. piętro. Proszę o pilną interwencję.",
        expected=Department.IT,
    ),
    Case(
        message="Zatrudniliśmy nowego pracownika, Marek Kowalski, developer, zaczyna w poniedziałek. Proszę o założenie konta w AD, dostęp do Jiry i GitLaba.",
        expected=Department.IT,
    ),
    Case(
        message=(
            "PILNE! Dostałem dziś mejla rzekomo od 'działu IT' z prośbą o kliknięcie "
            "linku i 'weryfikację hasła'. Domena nadawcy wygląda podejrzanie "
            "(it-support-firma.xyz albo coś takiego). Nie kliknąłem, ale obawiam się "
            "że inni w firmie też to dostali. Co robić?"
        ),
        expected=Department.IT,
    ),
    Case(
        message="Nasz dział marketingu (5 osób) potrzebuje licencji Adobe Acrobat Pro. Jak złożyć zamówienie na nowe licencje?",
        expected=Department.IT,
    ),
    Case(
        message=r"Serwer plików (\\firma-fs01\shared) nie odpowiada od wczorajszego wieczoru. Kilka teamów nie może pracować na dokumentach. Bardzo pilne.",
        expected=Department.IT,
    ),
    Case(
        message="VPN przestało mi działać po tym jak dostałem nowego służbowego laptopa. Klient zainstalowany ale przy próbie połączenia wyrzuca 'authentication error'. Pracuję zdalnie więc bez VPN nie mam dostępu do niczego.",
        expected=Department.IT,
    ),
    # --- other ---
    Case(
        message="Otrzymałam fakturę od zewnętrznego dostawcy usług porządkowych za maj. Do kogo ją przekazać w celu weryfikacji i wystawienia przelewu?",
        expected=Department.OTHER,
    ),
    Case(
        message="Dzień dobry, reprezentuję firmę AutoSoft i chciałbym przedstawić ofertę na oprogramowanie do zarządzania flotą. Proszę o wskazanie osoby decyzyjnej.",
        expected=Department.OTHER,
    ),
    Case(
        message="Jestem klientem i nie mogę dodzwonić się do obsługi. Zamówienie nr 78234 miało przyjść tydzień temu i nadal nic. Proszę o kontakt.",
        expected=Department.OTHER,
    ),
    Case(
        message="Ekspres do kawy w kuchni na 3. piętrze jest zepsuty od dwóch tygodni. Czy można go naprawić lub wymienić?",
        expected=Department.OTHER,
    ),
    # --- przypadki graniczne bez podpowiedzi ---
    Case(
        message="Chciałbym zmienić wymiar etatu na pół etatu ze względów osobistych. Jak to wygląda proceduralnie i kto mi w tym pomoże?",
        expected=Department.KADRY,
    ),
    Case(
        message="Wracam z urlopu rodzicielskiego za trzy tygodnie. Chciałbym omówić plan powrotu, elastyczny grafik i to, jak się odnaleźć po długiej przerwie.",
        expected=Department.HUMAN_RESOURCES,
    ),
    Case(
        message="Program do raportowania od godziny 9 nie daje się otworzyć, wyskakuje błąd i się zamyka.",
        expected=Department.HELP_DESK,
    ),
    Case(
        message="Nie mam dostępu do firmowego dysku sieciowego. Próbuję jak zwykle, ale dostęp jest odmówiony.",
        expected=Department.IT,
    ),
]
