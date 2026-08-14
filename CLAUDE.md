# CLAUDE.md

Projektinterne Referenz für Claude Code – Architektur, Konventionen und aktueller Stand. Ergänzt
README.md/README.en.md (die sind für Außenstehende/GitHub) um Dinge, die für die Arbeit *an* diesem
Projekt relevant sind, aber nicht in eine öffentliche Doku gehören.

**Diese Datei wird laufend aktualisiert** – nach jeder Session mit relevanten neuen Erkenntnissen,
abgeschlossenen Punkten oder neu aufgetauchten offenen Fragen ergänzen/korrigieren, nicht nur einmalig
schreiben. Der "Aktueller Stand"-Abschnitt ist der wichtigste Teil und muss akkurat bleiben.

**Sprache: Immer auf Deutsch antworten.** Unabhängig von der Sprache der Nutzeranfrage – alle
Antworten in diesem Projekt auf Deutsch verfassen. Code, Bezeichner und Kommentare bleiben davon
unberührt (Englisch, wie im restlichen Codebase-Standard).

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

## Aktueller Stand (zuletzt aktualisiert: 2026-08-10)

Der Nutzer hat ERPNext einmal komplett zurückgesetzt (Migrations-Daten/Masterdata entfernt, die
Basis-Struktur – Kontenplan, Kostenstellen, Steuervorlagen, Konten-Übergruppen – blieb erhalten)
und einen frischen ERPNext-API-Key/-Secret hinterlegt. Direkt danach wurden **alle** in `config.py`
referenzierten Konten-/Gruppen-/Vorlagen-Namen live gegengeprüft – alle 12 existieren:
`EN_INVOICE_PAID_FROM_ACCOUNT`, `EN_INVOICE_PAID_TO_ACCOUNT`, `EN_PURCHASE_PAID_TO_ACCOUNT`,
`EN_BANK_ACCOUNT_GROUP`, `EN_LOAN_ACCOUNT_GROUP`, `EN_RECEIVABLE_WRITEOFF_ACCOUNT_GROUP`,
`EN_DEBTOR_ACCOUNT_GROUP`, `EN_CREDITOR_ACCOUNT_GROUP` (die beiden waren zuvor nur eine
SKR03-Konvention-Schätzung – jetzt bestätigt korrekt), `EN_DEFAULT_COST_CENTER`,
`EN_DEFAULT_WAREHOUSE`, `EN_DEFAULT_TAXES_AND_CHARGES`, `EN_DEFAULT_PURCHASE_TAXES_AND_CHARGES`.
Der erste echte Live-Lauf gegen die frisch zurückgesetzte Instanz fand statt. `setup.py` lief
fehlerfrei durch (0 failed über alle Schritte). `main.py` scheiterte im ersten Anlauf fast
vollständig bei allen Belegarten (Rechnungen 0/5165, Lagerbewegungen 2922/15415, ...) durch zwei
externe Root Causes, beide auf ERPNext-Seite, nicht im Migrationscode:

1. **Fehlendes Geschäftsjahr.** Nach dem Reset existierte nur noch Fiscal Year "2026" - jeder
   historische Beleg (WeClapp-Daten reichen bis 2020 zurück) schlug mit `FiscalYearError` fehl.
   Fix: Fiscal-Year-Records 2020-2025 nachträglich per API angelegt (`Fiscal Year`-Doctype,
   `year_start_date`/`year_end_date` = volles Kalenderjahr, wie beim bestehenden 2026er).
   **Für künftige Resets: das gehört eigentlich in eine Art `setup_fiscal_years()`, ist aber
   aktuell nicht in `setup.py` automatisiert** - vor jedem Lauf gegen eine frisch aufgesetzte
   ERPNext-Instanz prüfen, ob Fiscal-Year-Records den vollen Datumsbereich der WeClapp-Daten
   abdecken (`min`/`max` über `invoiceDate`/`orderDate`/`postingDate` etc. im Cache).
2. **Fremde App auf derselben Instanz.** Die ERPNext-Instanz wird auch vom Shopware-6-Sync-Projekt
   `ecommerce_integrations` genutzt (siehe "Sonstiges" unten). Eine dortige Notification
   ("Ecommerce Sales Invoice") griff per direktem Attributzugriff auf `doc.ecommerce_source` zu -
   ein Feld, das auf einer frisch installierten Site nie entstand (die App hatte nie einen
   funktionierenden `after_install`-Hook, Custom Fields liefen bisher nur zufällig über
   `bench migrate` auf einer bestehenden Site mit). Jede Rechnungsanlage crashte dadurch komplett.
   Von der anderen Sitzung über `~/shared-agent-test.md` gemeldet und dort behoben (Hook aktiviert,
   Notification auf `doc.get('ecommerce_source')` umgestellt), Fix per `bench migrate` deployed.
   **Für künftige Resets: diese Instanz ist geteilt - nach jedem Reset kurz prüfen, ob Notifications/
   Custom Fields der anderen App sauber (re-)installiert wurden, bevor Rechnungen migriert werden.**
   **Update:** Derselbe Root Cause hat im dritten Live-Lauf noch eine zweite Stelle erwischt -
   `ecommerce_integrations/channel_propagation.py`s `propagate_to_payment_entry` (before_insert-Hook
   auf Payment Entry) selektiert `ecommerce_source` roh per SQL aus Sales Invoice, ohne
   Feld-Existenz-Check - warf `MySQLdb.OperationalError: Unknown column 'ecommerce_source'` bei 1058
   von 1337 Payment-Entry-Anlagen. An Sitzung B über `~/shared-agent-test.md` gemeldet (2026-08-09),
   noch nicht bestätigt/deployed. Kein Blocker für den restlichen main.py-Lauf (Payment Entries sind
   idempotent nachmigrierbar), aber vor dem nächsten vollständigen Cutover-Lauf gegenprüfen.

Ein dritter Live-Lauf (nach Fix von 1./2.) deckte drei weitere reale Bugs auf, alle inzwischen
behoben:

3. **`setup_fiscal_years()` jetzt automatisiert** (vorher als offener Punkt hier notiert). Beim
   dritten Lauf zusätzlich aufgefallen: der Altrechnungs-Import (siehe unten) braucht Belegjahre
   bis 2017 zurück, nicht nur 2020. `setup.py` scannt jetzt selbst `orderDate`/`invoiceDate`/
   `quotationDate`/`shippingDate`/`postingDate` über alle relevanten Cache-Dateien (plus
   `legacy_invoices/invoices.json`, falls vorhanden) und legt für jedes referenzierte Jahr ein
   volles Kalenderjahr als Fiscal Year an - offensichtlich korrupte Timestamps (ein `salesInvoice`
   mit absurdem negativem Epoch-Wert, löst sich auf ca. Jahr 0023 auf) werden über eine
   Plausibilitätsspanne (2000-2100) rausgefiltert. Läuft jetzt als Teil von `run_setup()`, kein
   manueller Schritt mehr nötig.
4. **Personenkonto-Zuordnung schlug bei Kunden/Lieferanten ohne Vor-/Nachname fehl.**
   `_map_customer_name()`/`_map_supplier_name()` bauten den Namen via
   `f"{wc_data.get('firstName', str())} {wc_data.get('lastName', str())}"` - `.get(key, default)`
   greift nur, wenn der Key fehlt, nicht wenn er mit explizitem `null` im JSON steht (kommt bei
   WeClapp-Testkunden/Sammelkonten wie "Barverkauf"/"Testkunde" vor). Ergebnis: der berechnete
   Kontoname enthielt buchstäblich "None" (z. B. "13779 - None Testkunde - FT"), was nicht mit
   dem von `setup_personal_accounts()` tatsächlich angelegten Konto übereinstimmte (dessen
   Label-Berechnung mit `or ''` korrekt gegen `None` abgesichert war) → `LinkValidationError`
   bei der Kundenanlage. Betraf 56 von 59 Customer- und mehrere Supplier-Fehlern im dritten Lauf.
   Fix: beide Stellen auf `.get('firstName') or ''` umgestellt (in
   `migration/customer_migration.py`/`migration/supplier_migration.py`).
5. **Massive Sales-Order/Quotation/Sales-Invoice-Fehlerquote durch Item-Steuer-Template-Konflikt**
   (524/3405 Sales Orders, 43/114 Quotations, dann live auch Sales Invoices betroffen -
   "Artikelbezogene Steuerdetails stimmen nicht mit den Steuern und Abgaben überein"). Root Cause:
   `article_migration.py._map_item_taxes()` setzte pro Item ein statisches ERPNext Item Tax
   Template basierend auf `article.taxRateType` - obwohl derselbe Artikel in der WeClapp-Historie
   unter verschiedenen Steuersätzen verkauft worden sein kann (Inland Standard, ermäßigt,
   steuerfreier Export). Jede Migration bucht den exakten historischen Steuerbetrag ohnehin schon
   pro Zeile als "Actual"-Steuerzeile auf dem Beleg selbst (`BaseMigration._add_tax`/`_map_taxes`)
   - das Item-Default kollidierte damit auf jedem Beleg, dessen tatsächlicher Satz vom aktuellen
   Artikel-Default abwich. Der Docstring behauptete fälschlich, die Migration setze pro Beleg ein
   `item_tax_rate`-Override - das war nie implementiert. Fix: `_map_item_taxes()` gibt jetzt immer
   `[]` zurück (kein Item-Default mehr), `config.EN_ITEM_TAX_TEMPLATE_MAP` entfernt (war nur dafür
   da). Da die ~6199 Items im dritten Lauf schon mit dem alten (falschen) Template angelegt waren,
   wurden sie zusätzlich per einmaligem Live-Bulk-Update bereinigt (`taxes`-Kindtabelle geleert;
   Skript nicht im Repo, war ein Wegwerf-Script im Scratchpad).
6. **Delivery Note buchte trotz `update_stock: 0` im Payload doppelt auf den Lagerbestand.**
   `delivery_note_migration.py` ging (Docstring sagte das explizit) davon aus, `update_stock: 0`
   verhindere wie bei Sales Invoice die Lagerbuchung. Live bestätigt: `update_stock` ist auf
   Delivery Note gar kein echtes Feld (`GET .../Delivery Note?fields=["update_stock"]` liefert
   `Field not permitted in query`) - ein submitteter Delivery Note bucht in ERPNext IMMER auf den
   Lagerbestand, dafür gibt es keinen Opt-out. Da `warehouseStockMovement`/Stock Entries exakt
   dieselben Warenausgänge schon abbilden, hat jeder erfolgreich submittete Delivery Note den
   Bestand doppelt abgezogen (einmal Stock Entry, einmal Delivery Note) - manifestierte sich im
   dritten Lauf als `NegativeStockError` bei 1621 von 3190 Lieferungen (die anderen scheiterten
   erst gar nicht an fehlendem Bestand, buchten also den Doppelabzug klaglos durch). **321 bereits
   submittete Delivery Notes** existieren dadurch aktuell mit potenziell falschem
   Lagerbestandseffekt - Korrektur (stornieren+neu als Draft, oder Stock Reconciliation) steht noch
   aus, siehe "Offene Punkte". Code-Fix: Delivery Note wird jetzt immer als Draft (`docstatus=0`)
   angelegt, unabhängig von `EN_DEFAULT_INVOICE_STATE` - das ist die einzige Möglichkeit, die
   Lagerbuchung wirklich zu unterdrücken.
   **Korrektur durchgeführt (2026-08-09):** Alle 321 betroffenen Delivery Notes wurden storniert
   (Stock-Ledger-/GL-Auswirkung damit korrekt rückgängig gemacht - das ist der entscheidende
   Schritt) und anschließend versucht zu löschen: 181 erfolgreich gelöscht, 140 bleiben als
   stornierter (docstatus=2) Beleg stehen, weil Frappe das Löschen bei verknüpften GL-/Lagerbuch-
   Einträgen verweigert (`LinkExistsError`) - normales, korrektes Frappe-Verhalten für einen
   Prüfpfad, kein offener Fehler. **Bekannte Einschränkung:** `_skip_if_exists()` behandelt einen
   stornierten Beleg als "existiert bereits" - die 140 zugehörigen Sendungen bekommen dadurch beim
   Neulauf von `migrate_wc_en_shipments()` keinen neuen (aktiven) Delivery Note mehr, nur den
   stornierten als Altlast. Kein fachliches Problem (Lagerbestand ist korrekt, nur die
   informelle Tracking-Notiz fehlt für diese ~140 von 3190 Sendungen) - akzeptiert statt mit
   Rename-Hacks aufwendig repariert.
7. **`setup_negative_rate_settings()` hat nie wirklich etwas bewirkt - Tippfehler im Feldnamen.**
   Der Code setzte `allow_negative_rate_for_items` (Singular "rate"), das echte Feld heißt
   `allow_negative_rates_for_items` (Plural "rates") - live über die DocType-Feldliste von
   Selling/Buying Settings bestätigt. Frappe verwirft unbekannte Felder bei einem Update
   stillschweigend (kein Fehler, kein Log-Hinweis) - die Funktion loggte bei jedem Lauf
   "enabled", ohne dass die Einstellung je wirklich aktiv war. Dadurch schlugen alle Zeilen mit
   negativem Rabatt-/Gutschrift-Preis in Sales Order/Quotation/Sales Invoice/Purchase-Pendants
   mit "Für den Artikel ... muss der Einzelpreis eine positive Zahl sein" fehl - im vierten Lauf
   allein 172 von 194 verbleibenden Sales-Invoice-Fehlern. Fix: Feldname korrigiert, live neu
   gesetzt und per GET verifiziert (`allow_negative_rates_for_items = 1`). **Für künftige Resets:**
   dieser Bug war über alle bisherigen Läufe hinweg aktiv - nach jedem Setup-Lauf empfiehlt es
   sich, sicherheitshalber per GET zu verifizieren, dass eine Single-Doctype-Einstellung wirklich
   den erwarteten Wert angenommen hat, statt sich auf die Erfolgsmeldung zu verlassen (Frappes
   Silent-Drop-Verhalten bei unbekannten Feldern gilt für Custom Fields UND normale Feld-Updates).

**Neu: Altrechnungs-Import (`legacy_invoices/`).** Rechnungen, die nur noch als PDF existieren
(teils vor 2020, teils später - kein Datumsschnitt, sondern "existiert nicht strukturiert in
WeClapp"), werden separat vom regulären WeClapp-Pipeline importiert. Ablauf: eine externe
Sitzung/ein externer Prozess extrahiert die PDFs zu `legacy_invoices/invoices.json` (Schema in
`legacy_invoices/FORMAT.md`), `legacy_invoices/import_legacy_invoices.py` liest das ein und legt
Sales Invoices als **Draft** an (bewusst nicht submitted - erst nach Stichprobenprüfung gegen die
PDFs manuell einreichen), inkl. PDF-Anhang. Namenskonvention `RE-ALT-...`, komplett getrennt vom
regulären `RE-...`-Namensraum. Ganzer Ordner `legacy_invoices/` ist in `.gitignore` (echte
Kunden-/Finanzdaten, nur lokal relevant). Dafür wurden vier neue, vorher nicht existierende
SKR03-Konten angelegt (Corona-Zeitraum 07-12/2020, befristete 16%/5%-Sätze): `8309`/`1769`
(5 %), `8339`/`1775` (16 %) - Kontonummern selbst gewählt (an den bestehenden 19%/7%-Konten
orientiert, keine verifizierte offizielle DATEV-Nummer), bei Bedarf mit Steuerberater abgleichen.
Erster Live-Lauf (3604 Rechnungen): 2658 erstellt, 946 fehlgeschlagen - fast alle durch die zu
diesem Zeitpunkt fehlenden Fiscal Years 2017-2019 (Altrechnungen reichen weiter zurück als die
reguläre WeClapp-Historie, siehe Punkt 3 oben), 8 durch negative Beträge (Gutschriften), die
ERPNext als normale Sales Invoice ablehnt - gefixt via `is_return=1` in `_transform()`, sobald
`net_amount < 0`. Nach beiden Fixes zweiter Lauf gestartet (idempotent, überspringt die 2658
bereits erstellten).

**Fertig und (mindestens) offline gegen den vollen Cache verifiziert:**
- Bankkonten-Setup (`setup_bank_accounts()`) inkl. Kunden-/Lieferanten-Bankkonten-Migration
  (`EN_MIGRATE_BANK_ACCOUNTS` steht jetzt auf `True`)
- Zahlungs-/Abschreibungsmigration (`payment_entry_migration.py`) – 81 % Verkauf / 71 % Einkauf
  lösen sich auf ein echtes Bankkonto auf, Rest wird als Journal-Entry-Abschreibung gebucht
- Personenkonten-Setup (`setup_personal_accounts()`) – 5680/5681 Kunden, 389/389 Lieferanten
- Rechnungs-E-Mail-Kontakt-Logik in `customer_migration.py`/`supplier_migration.py`
- CRM-Ereignis-Migration (`crm_event_migration.py`) – 97 % Trefferquote (3784/3895 Anrufe)
- `setup_negative_rate_settings()` (Selling/Buying Settings)

8. **UOM "Nos" verlangte Ganzzahlen, WeClapp liefert echte gebrochene Stückzahlen.** ERPNexts
   SKR03-Vorlage aktiviert "Muss eine ganze Zahl sein" auf "Nos" standardmäßig - live bestätigt,
   dass reale WeClapp-Positionen (z. B. `purchaseInvoiceItems`) Mengen wie 2,4 "Stk." führen, die
   korrekt auf "Nos" gemappt werden, aber an dieser Einschränkung mit `UOMMustBeIntegerError`
   scheiterten (113 von 116 Purchase-Invoice-Fehlern im fünften Lauf). Fix:
   `setup_uom_settings()` deaktiviert `must_be_whole_number` auf "Nos", jetzt Teil von
   `run_setup()`.
9. **Delivery Note ohne explizites `rate` bekam von ERPNext automatisch den Item-Standardpreis
   eingesetzt** - bei ein paar generischen Rabatt-/Gutschrift-Pseudoartikeln (u. a. "920011",
   "Abrechnung Gebrauchtteilverkauf") ist dieser negativ, was den `base_grand_total` unter 0
   drückte und mit "Grand Total must be >= 0.0" abgelehnt wurde (11 von 3190 Lieferungen).
   **Zwei Fixversuche nötig:** ein explizites `"rate": 0` allein reichte NICHT - live per
   Isolationstest bestätigt, dass ERPNext `rate` beim `validate()` aus `price_list_rate`
   (aus der Preisliste des Artikels nachgeladen) neu ableitet, auch wenn `rate` schon gesetzt
   war. Erst zusätzliches `"price_list_rate": 0` hat das unterbunden. `_map_items()` setzt jetzt
   beide Felder (Lieferschein war ohnehin nie als Preisträger gedacht, siehe Docstring).
   **Verbleibend, akzeptiert:** 2 von 3190 Lieferungen scheitern an "Angabe des Lagers ist für
   den Lagerartikel ... erforderlich" - `_map_item_warehouse()` findet für diese Positionen
   keinen `picks`-Eintrag in WeClapp, es gibt also schlicht keine bekannte Lagerortangabe zum
   Migrieren. Kein Datenverlust (Stock Entries decken den eigentlichen Lagerbestand ab), nur die
   Tracking-Notiz fehlt für diese 2 Positionen.

**Live-Migration abgeschlossen (2026-08-09).** Neun main.py-Läufe insgesamt (siehe Bugfixes 1-9
oben). Lauf 9 (mit Währungs- und Gutschriften-Vorzeichen-Fix aktiv) bestätigt den Endzustand:
Customer 5739/5739, Supplier 392/392, Item/Stock Entry/Quotation/Sales Invoice/Purchase
Order/Purchase Invoice-Kern bei 0 Fehlern, Sales Order 1/3405, Delivery Note 2/3190,
Purchase Invoice 3/2800, Payment Entry/Journal Entry zusammen 262 von 7916 (vorher 382 - der
Rückgang um exakt 120 bestätigt den Gutschriften-Vorzeichen-Fix zahlenmäßig; die verbleibenden
262 sind ausschließlich "Betrag übersteigt offenen Betrag"-Fälle, also die schon identifizierte
akzeptierte Restkategorie, kein neuer Bug). Die verbleibenden Restfehler sind einzeln geprüft
und verstanden (siehe "Offene Punkte"). Weitere Re-Runs gegen dieselbe Instanz bringen nichts
mehr - das ist der Endzustand.

**Vom Nutzer entschiedener Scope (2026-08-09) - das hier ist NICHT vergessen, sondern bewusst so
belassen:**
- **Verträge, Tickets:** nicht migriert, weil der Nutzer die entsprechenden WeClapp-Module gar
  nicht abonniert hat - es gibt schlicht keine Daten dafür.
- **SEPA-Lastschriftmandate:** technisch machbar geprüft (WeClapp hat nur 12 Mandate gecacht,
  `weclapp/cache/sepaDirectDebitMandate.json`; ERPNext hat kein natives SEPA-Doctype, live
  bestätigt - Custom Fields auf `Bank Account` wären der pragmatische Weg gewesen), vom Nutzer
  aber explizit als "nice to have, kein Muss" abgelehnt, nicht umgesetzt.
- **Nummernkreise für den laufenden Betrieb nach Go-Live:** vom Nutzer explizit als "kann komplett
  weggelassen werden" eingestuft - bleibt dauerhaft bei `autoname=Prompt` (WeClapp-Nummern 1:1).
- **Legacy-PDF-Rechnungen als Draft:** vom Nutzer bestätigt, dass der aktuelle Zustand (Entwurf,
  nicht eingereicht, siehe `legacy_invoices/FORMAT.md`) passt - keine weitere Aktion nötig.

**Offene Punkte:**
- Ob "2400 - Forderungsverluste" auch für Einkaufsseiten-Abschreibungen das fachlich richtige Konto
  ist, wurde nur für die Verkaufsseite an zwei echten Beispielen bestätigt (siehe Docstring in
  `payment_entry_migration.py`) – weiterhin ungeklärt.
- ~~2 Lieferanten mit Fremdwährung scheitern an der Personenkonto-Zuordnung~~ **behoben
  (2026-08-09):** `setup_personal_accounts()` setzt jetzt `account_currency` auf
  `party.currencyName`, wenn die von `config.EN_DEFAULT_CURRENCY` abweicht (statt immer EUR).
  Die beiden bereits live existierenden Konten (70022 "Openai, Llc", 70392 "Frappe Technologies
  Pvt. Ltd") wurden zusätzlich per Update auf USD nachgezogen.
- ~~382 Payment Entries lösen sich nicht auf ein echtes Bankkonto auf~~ **120 behoben, Rest
  bestätigt akzeptiertes Limit (2026-08-09, verifiziert über Lauf 9):** Root Cause war KEIN
  generelles Matching-Problem, sondern ein Vorzeichenfehler bei Zahlungen auf Gutschriften
  (`is_return=1`) - deren `outstanding_amount` ist bereits negativ, ein positiv gebuchter Betrag
  wird von ERPNext zu Recht als "größer als der ausstehende Betrag" abgelehnt (live bestätigt:
  120 von 196 betroffenen Rechnungen waren Gutschriften). Fix in `_transform_payment()` (negiert
  `amount`, wenn `en_invoice.is_return`) und in `_transform_writeoff()` (kehrt Soll/Haben um,
  gleicher Grund). Lauf 9 bestätigt den Fix zahlenmäßig exakt: 382 → 262 Fehler, Differenz genau
  120. Die verbleibenden 262 (Payment+Journal Entry zusammen) sind ausnahmslos "Betrag übersteigt
  offenen Betrag" bei regulären (nicht-Gutschrift) Rechnungen - echte WeClapp-Dateninkonsistenzen,
  akzeptiertes Limit der Rechnungsnummer+Betrag-Matching-Heuristik, kein weiterer Code-Fix
  vorgesehen.
- `disable_legacy_warehouses()` als manueller Cutover-Schritt steht noch aus (siehe main.py) -
  sinnvoll erst, wenn der Nutzer die Migration final für abgeschlossen erklärt.

**`bench reinstall`-Bereitschaft (2026-08-09):** Ausgangspunkt laut Nutzer ist eine Instanz mit
nur Company "FranceTec" + SKR03-Kontenplan, sonst nichts. `setup_accounts()` legte bisher nur
das OSS-Konto (1767) an - die 4 COVID-Übergangskonten (8339/1775 16 %, 8309/1769 5 %), die
`legacy_invoices/import_legacy_invoices.py`s `TAX_MAPPING` voraussetzt, existierten nur durch
ein untracked Wegwerf-Script aus einer früheren Session, nicht in `setup.py` selbst - bei einem
echten Reinstall wären sie also gefehlt. Gefixt: `setup_accounts()` legt jetzt alle 5 Konten
über eine Liste an, live einzeln standalone gegen die echte Instanz verifiziert (alle 5 melden
korrekt "exists"). **Wichtig:** Lauf 9 selbst zeigt in seinem Log noch das alte Verhalten (nur
1 Konto-Zeile), weil der Lauf schon gestartet war, bevor dieser Fix geschrieben wurde (Python
lädt `.py`-Änderungen nicht in einen bereits laufenden Prozess nach) - der Fix liegt aber auf
der Platte und greift beim nächsten frischen `setup.py`-Aufruf, also ab dem ersten Lauf nach dem
geplanten Reinstall. Mit diesem Fix ist `run_setup()` vollständig: alle Konten/Gruppen/Einstellungen,
die `main.py` voraussetzt, werden von `setup.py` selbst und idempotent erzeugt - kein bekannter
manueller Handgriff mehr offen vor einem `main.py`-Lauf gegen eine frisch zurückgesetzte Instanz.
Einzige verbleibende Unbekannte: ob die fremde App `ecommerce_integrations` (siehe "Sonstiges")
ihre eigenen Custom Fields/Notifications auf einer wirklich frischen Site sauber (re-)installiert
- außerhalb der Kontrolle dieses Projekts, nach dem Reinstall kurz gegenprüfen.

10. **WeClapps verknüpfte Kommentare ("Kommentare"-Feature) wurden nie migriert - kompletter,
    lange unentdeckter Gap.** Vom Nutzer gemeldet (2026-08-10): interne Hinweise an Kunden (Beispiel
    "Markus Decker") fehlen in ERPNext. Root Cause: `wc_doctypes.py` hatte von der ursprünglichen
    Vorlage einen auskommentierten `#COMMENT = "comment"  # TODO: get linked comments` - nie
    umgesetzt. Das ist ein eigenständiges WeClapp-Feature, komplett getrennt vom bereits migrierten
    `description`-Feld (`_map_wc_notes()`) - live gegen die echte API bestätigt: Kunde 91364
    ("KFZ-Reparaturwerkstatt Decker", dessen Adresse den Namen "Markus Decker" trägt) hat einen
    echten WeClapp-Kommentar ("Reifen je 3€ Netto"), der nur über einen separaten Endpunkt
    (`GET /comment?entityName=...&entityId=...`) abrufbar ist - **kein Bulk-/List-all-Modus**,
    `entityName`+`entityId` sind Pflichtparameter pro Aufruf. Live außerdem bestätigt: Customer- und
    Supplier-Kommentare hängen beide am selben zugrundeliegenden WeClapp-`party`-Datensatz
    (`entityName=customer`/`entityName=supplier`/`entityName=party` liefern für dieselbe ID
    identische Ergebnisse) - ~43 Parteien in dieser Instanz sind gleichzeitig Kunde und Lieferant,
    ein naiver Precache pro Doctype hätte deren Kommentare doppelt abgerufen/gespeichert.
    **Scope-Entscheidung des Nutzers:** nur Kunden + Lieferanten (nicht Belege wie Aufträge/
    Rechnungen) - der Endpunkt-Zwang zu Einzelabfragen hätte bei voller Breite (~25.000+ Belege)
    den Cache-Lauf spürbar verlängert.
    **Implementiert:** `WeClappAPI.get_comments(entity_name, id)` (neue Methode, GET-only wie der
    Rest des Clients); `WcCacheWrapper.comment_doctypes`/`_cache_comments()` sammelt die
    deduplizierte Vereinigung der Customer-/Supplier-IDs während des Haupt-Cache-Loops und fragt
    danach einmal pro eindeutiger Partei-ID mit `entityName="party"` ab, statt pro Doctype (vermeidet
    die Doppel-Abfrage der 43 Überschneidungen); Ergebnis landet in `comment.json`, gruppiert nach
    `entityId` über `WcCacheApi.get_comments()`. `BaseMigration._map_wc_comments()` formatiert die
    Kommentare (sortiert nach Datum) als Klartext-Zeilen mit Datum+Autor.
    **Korrektur (2026-08-10, noch am selben Tag):** erste Implementierung schrieb in ein neues
    Custom Field `wc_interne_notiz` (analog zu den Belegarten) - der Nutzer meldete daraufhin,
    die Notiz sei in ERPNexts eigenem Kundenformular ("Internal notes about this customer. Not
    visible on transactions or the portal.") nicht sichtbar. Live geprüft: Customer/Supplier
    haben dafür längst eigene native Felder (`customer_details`/`supplier_details`, beide
    `fieldtype: "Text"`, exakt diese Beschriftung) - kein anderes migriertes Doctype hat ein
    Äquivalent. Umgestellt: `CustomerMigration`/`SupplierMigration._map_notes_and_comments()`
    schreiben jetzt direkt in `customer_details`/`supplier_details`; `setup_internal_note_fields()`
    erzeugt das `wc_interne_notiz`-Custom-Field nur noch für die 6 Belegarten ohne natives
    Pendant (Customer/Supplier aus der Liste entfernt); die zuvor angelegten
    `Customer-wc_interne_notiz`/`Supplier-wc_interne_notiz`-Custom-Fields (samt Section Break)
    wurden live wieder gelöscht. Da `customer_details`/`supplier_details` reines `Text` sind
    (kein `Text Editor`/Rich-Text), musste HTML aus WeClapps `description` zusätzlich in Klartext
    gewandelt werden: neue `ERPNextHelper.strip_html()` - dabei live entdeckt, dass WeClapps
    `description`-Feld **doppelt HTML-encodiert** vorliegt (roher Cache-Wert enthält buchstäblich
    `&amp;Uuml;` und `&lt;br /&gt;`, also einmal escapte Escapes) - `strip_html()` unescaped
    deshalb wiederholt bis zum Fixpunkt (begrenzt auf 5 Durchläufe), erst danach werden
    `<br>`/`</p>` in Zeilenumbrüche gewandelt und verbleibende Tags entfernt. Live an allen 12
    Kunden-/8 Lieferanten-Beschreibungen mit echtem Inhalt verifiziert (u. a. Umlaute, mehrzeilige
    Inhalte). Zwei Lieferanten-Beschreibungen enthalten literale "?"-Zeichen an Stellen, wo
    vermutlich ein "€" gemeint war - bestätigt bereits so in WeClapps Rohdaten vorhanden (keine
    Beschädigung durch die Migration, bewusst nicht "korrigiert", da nur geraten werden könnte).
    **Live-Backfill (2026-08-10):** da `cache_weclapp.py` den kompletten Cache verwirft und neu
    aufbaut (Stunden-Aufwand), wurde stattdessen ein einmaliges Wegwerf-Script gegen die
    *bestehende* `customer.json`/`supplier.json` gefahren, das nur `comment.json` befüllt (~6100
    Einzelabfragen, ~0.09s/Call, ~9-10 Min. Laufzeit) - ein regulärer künftiger `cache_weclapp.py`-
    Lauf deckt das jetzt aber automatisch mit ab (`comment_doctypes` ist Teil von `cache_all()`).
    Ergebnis: 15 von 6088 Parteien haben tatsächlich einen Kommentar (Kunde 91364 = "Markus
    Decker"-Fall aus der Nutzermeldung war dabei). Customer-/Supplier-Migration danach zweimal
    erneut gelaufen (idempotent, upsertet über `existing = en_api.get(...)` - jeweils 5739/5739
    bzw. 392/392, 0 failed; zweiter Lauf nach dem strip_html()-Fix oben) und live gegen Kunde
    15655 (customerNumber) verifiziert: `customer_details` enthält jetzt korrekt
    "2024-05-13 (info@francetec.de): Reifen je 3€ Netto". Abgeschlossen, kein offener Punkt mehr.

11. **Kritischer, vorher unentdeckter Bug: E-Mail/Telefon erreichten ~73 % der Kunden nie in
    ERPNext.** Beim Nachforschen zu weiteren, vom Nutzer gewünschten Feldern (siehe unten)
    entdeckt: `Customer.email_id`/`mobile_no` sind in ERPNext **Read-Only-Felder mit
    `fetch_from: customer_primary_contact.email_id`/`.mobile_no`** - sie spiegeln IMMER den
    primären Kontakt, sind nicht direkt beschreibbar. `customer_migration.py`/
    `supplier_migration.py` haben aber nie einen Kontakt angelegt, wenn WeClapps `contacts[]`
    leer war und keine abweichende Rechnungs-E-Mail existierte - live gemessen: **5643 von 5739
    Kunden haben ein leeres `contacts[]`, davon 4202 mit einer echten WeClapp-E-Mail**, die dadurch
    nie nach ERPNext gelangte (`customer_primary_contact` blieb `None`, `email_id`/`mobile_no`
    blieben leer). Nebenbefund: `customer_migration.py`s `_transform()` versuchte zusätzlich
    `"phone"`/`"email"` direkt auf Customer zu setzen - live bestätigt, dass **keines von beiden
    ein echtes Customer-Feld ist** (Frappe verwirft beide seit jeher stillschweigend), diese
    beiden toten Zeilen wurden entfernt (Supplier nutzt korrekterweise `mobile_no`/`email_id`,
    die echten - wenn auch fetch_from-gesteuerten - Feldnamen, dort nicht angefasst).
    **Fix:** neue `_map_self_contact()` in beiden Migrationsklassen - baut einen Contact aus der
    Partei's eigenen Feldern (firstName/lastName, bei fehlendem Namen auf COMPANY-Typ
    `"Hauptkontakt"` + Firmenname zurückfallend, analog zum bestehenden "Rechnungsversand"-Muster),
    wird als `customer_primary_contact`/`supplier_primary_contact` gesetzt, aber NUR falls weder
    ein echter WeClapp-Kontakt noch die Rechnungs-E-Mail-Override-Logik bereits einen geliefert
    hat. **Wichtig:** das musste zusätzlich in den Upsert-Zweig von `migrate()` eingebaut werden
    (nicht nur den "neu anlegen"-Zweig) - da bei diesem Projektstand bereits alle 5739/392
    Kunden/Lieferanten existieren, hätte ein reiner Re-Run über den Create-Zweig nie gegriffen;
    der Upsert-Zweig prüft jetzt `if not existing.get("customer_primary_contact")` und legt den
    Kontakt nachträglich an. Live-Backfill-Lauf: 5739/5739 bzw. 392/392, 0 failed (2 einmalige
    transiente Frappe-Cloud-Fehler beim ersten Versuch - "Kontakt X nicht gefunden" direkt nach
    Kontakt-Anlage+Verknüpfung, beim manuellen Sofort-Retry ohne Codeänderung sofort erfolgreich;
    beim zweiten vollen Lauf 0 Fehler). Live verifiziert an Kunde 15040 (Christian Seipold,
    Beispiel aus der Nutzermeldung): `email_id` zeigt jetzt korrekt `m.bagnole@yahoo.de`.

12. **Sechs vom Nutzer explizit angeforderte zusätzliche Felder** (nach einer Bestandsaufnahme
    aller ~158 `party.json`-Felder gegen das, was migriert wird - siehe Punkt 11 oben, das war der
    wichtigste Fund dabei): `termOfPaymentName`, `paymentMethodName`, `salutation`/`title`,
    `blockNotice`, `optIn*`, `emailHome`/`fax`/`mobilePhone1`. Alle live implementiert und
    verifiziert:
    - **`termOfPaymentName`** (Zahlungsbedingungen, z.B. "net 14", "3/14 net 90") → ERPNexts
      natives `payment_terms`-Link-Feld auf Customer/Supplier. Neue `setup.setup_payment_terms()`
      legt pro distinktem WeClapp-Wert (9 insgesamt über customer.json+supplier.json) ein Payment
      Terms Template an - `_parse_wc_payment_term()` parst WeClapps Kurzform ("net N" →
      `credit_days=N`; "X/Y net Z" → zusätzlich `discount`/`discount_validity` auf derselben
      Zeile), gegen alle real vorkommenden Werte vor dem Schreiben verifiziert. Autoname ist
      `field:template_name`, d.h. der WeClapp-String selbst ist der ERPNext-Dokumentname - keine
      separate Mapping-Tabelle nötig.
    - **`paymentMethodName`** (z.B. "Auf Rechnung", "PayPal", "Lastschrift") → neues Custom Field
      `wc_zahlungsart` auf Customer/Supplier (kein natives ERPNext-Äquivalent gefunden).
    - **`salutation`/`title`** → `Contact.salutation` (Link auf ERPNexts Standard-Salutation-Werte
      - nur `MR`→`Mr`/`MRS`→`Mrs` sauber gemappt, `NO_SALUTATION`/`COMPANY`/`FAMILY`/fehlend
      bewusst ungemappt statt geraten, siehe `ContactMigration._SALUTATION_MAP`) und
      `Contact.designation` (Data, für WeClapps `title`, z.B. "Dr.-Ing.").
    - **`blockNotice`** (Sperrgrund-Freitext, nur auf Customer, kein Supplier-Äquivalent im Schema)
      → als "Sperrgrund: ..." in `customer_details` (siehe Punkt 9/`_map_notes_and_comments()`).
    - **`emailHome`/`fax`/`mobilePhone1`** → `emailHome` als sekundäre (nicht-primäre)
      `Contact.email_ids`-Zeile; `mobilePhone1` wie bisher schon für echte WeClapp-Kontakte
      (`ContactMigration._map_phone_nos()`); `fax` als neues Custom Field `Contact.wc_fax` (kein
      natives Fax-Feld auf Contact).
    - **`optIn`/`optInLetter`/`optInPhone`/`optInSms`** (Marketing-Einwilligungen) → vier neue
      Custom Fields `wc_opt_in_email`/`_letter`/`_phone`/`_sms` auf Customer (**nicht** Supplier -
      supplier.json hat diese Felder gar nicht, live bestätigt). Bewusst NICHT in ERPNexts native
      `Contact.unsubscribed` geschrieben (nur E-Mail, ein einzelnes generisches Flag) - die vier
      Felder liegen direkt auf Customer, u.a. damit das Shopware-Sync-Plugin
      (`ecommerce_integrations`) sie ohne Link-Traversierung lesen kann; an
      `~/shared-agent-test.md` für die andere Sitzung dokumentiert. **Wichtiger Befund beim
      Live-Verifizieren:** `optIn` ist bei **allen** 5739 gecachten Kunden `false` - in dieser
      WeClapp-Instanz hat aktuell niemand aktiv einer E-Mail-Marketing-Einwilligung zugestimmt
      (oder das Feld wird auf WeClapp-Seite schlicht nicht genutzt). Technisch korrekt migriert,
      aber ohne einen einzigen "true"-Fall in den Live-Daten nicht end-to-end mit einem positiven
      Beispiel verifizierbar gewesen - nur der (durchgängige) negative Fall.
    Neuer, ebenfalls neuer Helper `ERPNextHelper.strip_html()` musste zusätzlich mehrfach
    unescapen (nicht nur einmal) - siehe Punkt 9, dieselbe Methode wird hier für `customer_details`
    weiterverwendet, keine neue Logik nötig.

**Design-Entscheidungen, die bewusst so getroffen wurden (nicht versehentlich unvollständig):**
- WeClapps volles Buchungsjournal (`accountingTransaction`) wird NICHT als allgemeine Journal Entries
  importiert (würde ERPNexts eigene GL-Buchungen beim Rechnungs-Submit doppeln). Nur gezielt für
  Zahlungsauflösung/Abschreibungen genutzt.
- Bestehende generische Konten "1200 - Bankkonto"/"1000 - Kasse" wurden nicht umbenannt (Frappes
  Autoname-Mechanik für Account lässt das über die dünne REST-Wrapper-Schicht nicht zu) – ist
  funktional irrelevant, da Buchung über die Kontonummer läuft, nicht das Label.

## Bekannte, behobene Stolperfallen beim Cachen/Migrieren

- **`erpnext/en_api.py` hatte (wie zuvor `wc_api.py`, siehe nächster Punkt) keinen Request-Timeout.**
  Live beobachtet (2026-08-14): ein `main.py`-Lauf gegen die frisch aufgesetzte Instanz blieb nach
  einem Laptop-Schlafzustand über Nacht **22+ Stunden** ohne jede neue Log-Zeile hängen - `ps`
  zeigte weiterhin eine offene TCP-Verbindung zum Frappe-Cloud-Host, CPU-Zeit stagnierte. Exakt
  derselbe Bug wie unten für `wc_api.py` dokumentiert, aber nie auf die ERPNext-Seite übertragen.
  Fix: `timeout=(10, 180)` auf beide `session.request()`-Aufrufe in `_request()` sowie auf den
  separaten `requests.post()` in `upload_file()` (nutzt keine Session, wurde beim ersten Fix
  übersehen). Diagnose-Muster wie beim Cache-Hänger: `ps aux | grep main.py`, `lsof -p <pid>`
  zeigt die hängende Verbindung, `ls -la <logfile>` zeigt den Zeitpunkt des letzten Fortschritts -
  zusätzlich empfiehlt sich ein Live-Abgleich der tatsächlichen ERPNext-Datensatzzahlen
  (`frappe.client.get_count` per API) gegen den Log-Stand, um sicherzugehen, dass wirklich nichts
  mehr vorankommt und nicht nur die Log-Ausgabe verzögert ist.
- **`weclapp/wc_api.py` hatte keinen Request-Timeout.** Ein hängender Server/Proxy konnte
  `cache_weclapp.py` unbemerkt für Stunden blockieren (live beobachtet: 2+ Stunden, eine einzelne
  offene TCP-Verbindung, keine Fehlerausgabe). Jetzt `timeout=(10, 180)` gesetzt, und die
  Exception-Behandlung greift nicht mehr fälschlich auf `response.status_code` zu, wenn `response`
  wegen eines Timeouts nie zugewiesen wurde (hätte sonst einen `UnboundLocalError` statt einer
  sauberen `ApiException` geworfen). Bei einem erneuten Hänger: `ps aux | grep cache_weclapp`,
  `lsof -p <pid>` zeigt offene Verbindungen, `ls -lat weclapp/cache/*.json` zeigt den letzten
  Fortschritt.
- **`_download_documents()` in `wc_cache_wrapper.py` lud Dokumente bei jedem Cache-Lauf neu
  herunter**, obwohl `cache_all()` nur die `*.json`-Dateien löscht, nicht den
  `weclapp/cache/documents/`-Baum. Jetzt wird übersprungen, was schon existiert (gleiches Muster
  wie `cache_article_images.py`, das das schon immer konnte) - macht Re-Cache-Läufe deutlich
  schneller.
- **`cache_all()` rief `_download_documents()` für JEDEN der ~100 WeClapp-Doctypes auf**, auch für
  reine Nachschlagetabellen, deren Dokumente nirgends verwendet werden (z. B. `articleSupplySource`
  mit ~87.000 Einträgen → ~87.000 sequenzielle `get_documents()`-HTTP-Calls, live beobachtet:
  dominierte den gesamten Lauf über Stunden, sah wie ein Hänger aus, war aber nur brutal
  ineffizient). Live gemessen mit `ps -o pid,etime,time` (CPU-Zeit wächst kaum über Zeit) plus
  `lsof -p <pid>` (dieselbe eine Verbindung bleibt lange bestehen) unterscheiden: echter Hänger vs.
  extrem langsame sequenzielle Schleife sehen fast identisch aus. Fix: `WcCacheWrapper.document_doctypes`
  - nur noch die 9 Doctypes, die `BaseMigration.upload_weclapp_documents()` tatsächlich aufrufen
  (ARTICLE, CUSTOMER, SUPPLIER, SALES_INVOICE, SALES_ORDER, PURCHASE_INVOICE, PURCHASE_ORDER,
  QUOTATION, SHIPMENT), bekommen noch `_download_documents()` aufgerufen.

## Sonstiges

- Es existiert eine externe Datei `~/shared-agent-test.md` (außerhalb dieses Repos), über die in
  einer früheren Session testweise mit einer Claude-Code-Sitzung im Projekt `ecommerce_integrations`
  kommuniziert wurde (Shopware-6-Sync-Kompatibilitätsprüfung). Falls der Nutzer wieder auf
  Cross-Projekt-Absprache mit diesem Projekt zu sprechen kommt, ist das der Mechanismus.
