# CLAUDE.md

Projektinterne Referenz für Claude Code – Architektur, Konventionen und aktueller Stand. Ergänzt
README.md/README.en.md (die sind für Außenstehende/GitHub) um Dinge, die für die Arbeit *an* diesem
Projekt relevant sind, aber nicht in eine öffentliche Doku gehören.

**Diese Datei wird laufend aktualisiert** – nach jeder Session mit relevanten neuen Erkenntnissen,
abgeschlossenen Punkten oder neu aufgetauchten offenen Fragen ergänzen/korrigieren, nicht nur einmalig
schreiben. Der "Aktueller Stand"-Abschnitt ist der wichtigste Teil und muss akkurat bleiben.

## Was das Projekt macht

Migration von WeClapp (ERP) nach ERPNext (Open-Source-ERP) für eine konkrete Instanz, über die
REST-APIs beider Produkte. Drei getrennte Phasen: **Cachen** (`cache_weclapp.py`, komplettes
WeClapp-Abbild als JSON via PysonDB) → **Setup** (`setup.py`, idempotentes Anlegen der
ERPNext-Stammdaten/Strukturen) → **Migration** (`main.py`, überträgt die eigentlichen Datensätze aus
dem Cache). Details/Feature-Liste: siehe README.md.

## Architektur-Grundprinzipien (nicht brechen ohne guten Grund)

- **WeClapp-Client ist strukturell read-only.** `weclapp/wc_api.py`: `create()`/`update()`/`delete()`
  verweigern jeden Aufruf, `_request()` lehnt jede Nicht-GET-Methode ab. Das ist eine explizite
  Sicherheitsgarantie gegenüber dem Nutzer, nicht nur eine Konvention – niemals aufweichen.
- **Deterministische Namen statt persistiertem Mapping.** ERPNext-Dokumente bekommen Namen, die
  direkt aus WeClapp-Nummern abgeleitet sind (`RE-2024RE1004`, `SO-10234`, `CRM-819030`, ...).
  Mehrere Codestellen (z. B. `setup.setup_warehouses()` und `stock_entry_migration.py`) berechnen
  denselben Namen unabhängig voneinander aus denselben Quelldaten – kein Cross-Script-State nötig.
  Siehe `ERPNextHelper.get_wc_warehouse_name()`/`get_wc_account_name()` als Muster.
- **Idempotenz überall.** Jede `setup_*`-Funktion: try/except, "already exists"/"DuplicateEntryError"
  wird als Skip behandelt, alles andere wird geloggt und gezählt (created/skipped/failed). Jede
  Migration prüft vor dem Anlegen, ob der Zielname schon existiert (`_skip_if_exists`).
- **Ein Fehler bei einem Datensatz bricht nie den ganzen Lauf ab.** `MigrationWrapper.migrate_all()`
  fängt pro Datensatz, loggt `FAILED ...` und macht weiter.
- **Erst gegen echte Cache-Daten verifizieren, dann Code schreiben/vertrauen.** Bewährtes Muster aus
  mehreren Sessions: eine Zuordnungs-Heuristik (z. B. Zahlung → Bankkonto, Personenkonto → Kunde)
  nie auf Verdacht implementieren, sondern erst mit einem kleinen Python-Snippet gegen
  `weclapp/cache/*.json` die tatsächliche Trefferquote messen. Mehrfach hat sich die erste Annahme
  als falsch/unzureichend erwiesen (Payment-Matching über Betrag+Datum: nur 18–45 % Treffer, verworfen
  zugunsten Rechnungsnummer+Betrag: 71–81 %; Personenkonto-Zuordnung über Namensabgleich: nur 6–94 %
  je nach Formatierung, verworfen zugunsten der direkten ID-Referenz in `party.json`: ~100 %).

## Wo was liegt

- `base/` – gemeinsame Abstraktionen (`ApiBase`, `ApiException`, `DocType`), von beiden API-Clients
  genutzt. Kein Ballast, wird gebraucht.
- `weclapp/` – WeClapp-Zugriff: `wc_api.py` (live, read-only), `wc_cache_api.py` (liest aus dem
  JSON-Cache, hier liegen alle `get_*()`-Lookup-Methoden mit Lazy-Caching), `wc_cache_wrapper.py`
  (befüllt den Cache initial), `wc_doctypes.py` (Enum aller WeClapp-Objekttypen).
- `erpnext/` – ERPNext-Zugriff: `en_api.py` (REST-Client), `en_helper.py` (Namens-/Mapping-Helfer,
  hier leben die deterministischen Namensfunktionen), `en_doctypes.py` (Enum der genutzten
  ERPNext-Doctypes), `en_tax_info.py` (Steuer-Mapping-Datenklassen).
- `migration/` – ein Modul pro Objekttyp, alle erben von `BaseMigration`. `migration_wrapper.py`
  ist der zentrale Dispatcher (lädt einmalig alle gebrauchten Lookup-Tabellen, reicht sie an die
  konkrete Migration weiter). Neue Migration hinzufügen: Klasse hier, dann in `__init__.py`,
  `migration_wrapper.py`s `_get_migration()`-Dispatch und `main.py` verdrahten.
- `setup.py` – alle `setup_*()`-Funktionen, orchestriert von `run_setup()`.
- `.github/FUNDING.yml`, `.devcontainer/` – Nebensächlichkeiten, siehe README falls Frage aufkommt.
- `test.py` wurde entfernt (totes Altmaterial aus der ursprünglichen Vorlage).

## Sensible Daten

`config.py`, `weclapp/cache/` (komplett) und `*.xlsx` (Kontenplan-Exporte) sind in `.gitignore`.
Vor jedem `git add`/Push kurz `git status` prüfen, dass keine dieser Dateien auftauchen.
`config_example.py` ist die Vorlage für `config.py` und muss generisch bleiben (Platzhalter
`"Your Company"`/`"YC"`, keine echten Firmennamen/Kontodaten) – siehe Historie, das war zwischenzeitlich
mit echten FranceTec-Daten befüllt und wurde bewusst zurückgebaut.

## Aktueller Stand (zuletzt aktualisiert: 2026-08-08)

**Fertig und offline gegen den vollen Cache verifiziert, aber noch NICHT live gegen die echte
ERPNext-Instanz gelaufen:**
- Bankkonten-Setup (`setup_bank_accounts()`) inkl. Kunden-/Lieferanten-Bankkonten-Migration
  (`EN_MIGRATE_BANK_ACCOUNTS` steht jetzt auf `True`)
- Zahlungs-/Abschreibungsmigration (`payment_entry_migration.py`) – 81 % Verkauf / 71 % Einkauf
  lösen sich auf ein echtes Bankkonto auf, Rest wird als Journal-Entry-Abschreibung gebucht
- Personenkonten-Setup (`setup_personal_accounts()`) – 5680/5681 Kunden, 389/389 Lieferanten
- Rechnungs-E-Mail-Kontakt-Logik in `customer_migration.py`/`supplier_migration.py`
- CRM-Ereignis-Migration (`crm_event_migration.py`) – 97 % Trefferquote (3784/3895 Anrufe)
- `setup_negative_rate_settings()` (Selling/Buying Settings)

**Offene Punkte:**
- `config.EN_DEBTOR_ACCOUNT_GROUP`/`EN_CREDITOR_ACCOUNT_GROUP` sind **nicht live verifiziert**
  (ERPNext-API-Token war beim Bauen inaktiv) – nur eine SKR03-Konvention-Schätzung. Vor dem ersten
  Lauf von `setup_personal_accounts()` gegen den echten Kontenplan prüfen.
- Ob "2400 - Forderungsverluste" auch für Einkaufsseiten-Abschreibungen das fachlich richtige Konto
  ist, wurde nur für die Verkaufsseite an zwei echten Beispielen bestätigt (siehe Docstring in
  `payment_entry_migration.py`).
- Erster echter Live-Lauf von `setup_bank_accounts()`/`setup_personal_accounts()`/Zahlungsmigration
  gegen die produktive ERPNext-Instanz steht noch aus (bisher nur Offline-Verifikation gegen den
  Cache + vereinzelte Live-Checks anderer Config-Werte).
- Nummernkreise für den laufenden Betrieb nach Go-Live (aktuell `autoname=Prompt`, WeClapp-Nummern
  werden 1:1 übernommen) sind für die Zeit nach der Migration noch nicht gelöst.
- Verträge, SEPA-Mandate, Tickets sind noch nicht migriert (WeClapp-Doctypes existieren, keine
  Migration dafür).

**Design-Entscheidungen, die bewusst so getroffen wurden (nicht versehentlich unvollständig):**
- WeClapps volles Buchungsjournal (`accountingTransaction`) wird NICHT als allgemeine Journal Entries
  importiert (würde ERPNexts eigene GL-Buchungen beim Rechnungs-Submit doppeln). Nur gezielt für
  Zahlungsauflösung/Abschreibungen genutzt.
- Bestehende generische Konten "1200 - Bankkonto"/"1000 - Kasse" wurden nicht umbenannt (Frappes
  Autoname-Mechanik für Account lässt das über die dünne REST-Wrapper-Schicht nicht zu) – ist
  funktional irrelevant, da Buchung über die Kontonummer läuft, nicht das Label.

## Sonstiges

- Es existiert eine externe Datei `~/shared-agent-test.md` (außerhalb dieses Repos), über die in
  einer früheren Session testweise mit einer Claude-Code-Sitzung im Projekt `ecommerce_integrations`
  kommuniziert wurde (Shopware-6-Sync-Kompatibilitätsprüfung). Falls der Nutzer wieder auf
  Cross-Projekt-Absprache mit diesem Projekt zu sprechen kommt, ist das der Mechanismus.
