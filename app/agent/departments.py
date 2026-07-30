from enum import Enum

from app.config import settings


class Department(str, Enum):
    KADRY = "kadry"
    HUMAN_RESOURCES = "human-resources"
    HELP_DESK = "help-desk"
    IT = "it"
    OTHER = "other"

    @property
    def address(self) -> str:
        return f"{self.value}@{settings.department_domain}"


DEPARTMENT_SCOPES: dict[Department, str] = {
    Department.KADRY: (
        "Administracja kadrowo-płacowa. Dokumenty, formalne uprawnienia i pieniądze "
        "na pasku wynagrodzeń: wnioski urlopowe, zwolnienia lekarskie, umowy i aneksy, "
        "świadectwa pracy, zaświadczenia o zatrudnieniu, ewidencja czasu pracy, "
        "wynagrodzenia, PIT-y, rozliczenia delegacji."
    ),
    Department.HUMAN_RESOURCES: (
        "Miękka strona HR. Ludzie, rozwój i relacje: rekrutacja, onboarding nowych "
        "osób, szkolenia, oceny okresowe, ścieżki awansu, konflikty w zespole, "
        "atmosfera pracy, benefity pozapłacowe."
    ),
    Department.HELP_DESK: (
        "Pierwsza linia wsparcia. Jeden użytkownik, jeden konkretny problem z własnym "
        "sprzętem lub oprogramowaniem: nie działa drukarka, zawiesza się aplikacja, "
        "reset zapomnianego hasła, nie działa mysz, klawiatura lub monitor."
    ),
    Department.IT: (
        "Infrastruktura, systemy i bezpieczeństwo. Sprawy wykraczające poza jedno "
        "stanowisko: awarie sieci i usług dotyczące wielu osób, serwery i VPN, "
        "zakładanie kont i nadawanie uprawnień, incydenty bezpieczeństwa i podejrzane "
        "wiadomości, zamawianie nowego sprzętu i licencji."
    ),
    Department.OTHER: (
        "Wszystko, co nie należy do żadnego z powyższych działów: sprawy księgowe "
        "i faktury, oferty handlowe, zapytania od klientów, sprawy biurowe "
        "i administracyjne, wiadomości bez czytelnego zgłoszenia."
    ),
}
