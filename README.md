# WeClapp → ERPNext Migration

*[English version](README.en.md)*

Ein Python-Projekt zur Migration von Daten aus dem ERP-System [WeClapp](https://www.weclapp.com/) in das Open-Source-ERP-System [ERPNext](https://erpnext.com), über die REST-APIs beider Produkte.

Ursprünglich basierend auf einer Vorlage von [fglashauser](https://github.com/fglashauser/weclapp-erpnext-migration), seitdem stark erweitert und für eine konkrete WeClapp-zu-ERPNext-Migration angepasst.

### Wichtiger Hinweis

Die eigentliche Datenmigration ist abgeschlossen und lief erfolgreich gegen eine produktive ERPNext-Instanz durch – siehe "Nächste Schritte" unten für die (bewusst) nicht umgesetzten Teile und verbleibende manuelle Cutover-Schritte.

## Wie es funktioniert

Die Migration läuft in drei getrennten Phasen ab, die bewusst nicht ineinander verzahnt sind:

1. **Cachen** (`cache_weclapp.py`): Liest alle relevanten WeClapp-Objekte einmalig über die WeClapp-REST-API aus und speichert sie lokal als JSON (mit [PysonDB](https://github.com/pysonDB/pysonDB) als einfacher Dateidatenbank). Zusätzlich werden Original-Dokumente (PDFs) und Artikelbilder heruntergeladen.
2. **Setup** (`setup.py`): Legt in ERPNext die Stammdaten und Strukturen an, die die eigentliche Migration voraussetzt – Zusatzfelder, Lagerorte, Artikelgruppen, Hersteller, Bankkonten, Namensschemata usw. Idempotent, d. h. beliebig oft wiederholbar, ohne Duplikate zu erzeugen.
3. **Migration** (`main.py`): Überträgt die eigentlichen Datensätze aus dem lokalen Cache nach ERPNext, in einer festen Reihenfolge, die Abhängigkeiten zwischen Belegen respektiert (z. B. Kunden vor Rechnungen, Aufträge vor Lieferscheinen).

Die Trennung von Cache und Migration hat einen wichtigen Vorteil: Die eigentliche Migration braucht **keine aktive WeClapp-Verbindung** mehr und kann beliebig oft gegen denselben, konsistenten Datenstand wiederholt werden – etwa nach einem fehlgeschlagenen Teillauf oder um neue Migrationsschritte gegen dieselben Ausgangsdaten zu testen. Da ein WeClapp-Zugang während der Entwicklung dieses Projekts zeitweise nicht verfügbar war, wurde dieser Cache-Ansatz von Anfang an so gebaut.

**Schreibsicherheit gegenüber WeClapp:** Der WeClapp-API-Client (`weclapp/wc_api.py`) ist bewusst rein lesend implementiert – `create()`/`update()`/`delete()` verweigern jeden Aufruf, und auch auf HTTP-Ebene wird jede Nicht-GET-Anfrage abgelehnt. Die Migration liest die WeClapp-Daten nur einmalig beim Cachen; alle Schreiboperationen finden ausschließlich in ERPNext statt.

Jeder Migrationsschritt ist idempotent: ERPNext-Dokumente werden mit deterministischen, aus den WeClapp-Nummern abgeleiteten Namen angelegt (`RE-2024RE1004`, `SO-10234`, ...). Ein erneuter Lauf erkennt bereits migrierte Datensätze an ihrem Namen und überspringt sie, statt sie zu duplizieren. Ein Fehler bei einem einzelnen Datensatz wird geloggt und übersprungen, statt den ganzen Lauf abzubrechen.

## Features

### Setup (`setup.py`)

Idempotentes, einmaliges Anlegen der ERPNext-Stammdaten, die vor der eigentlichen Migration existieren müssen:

- Zusatzfelder (Custom Fields), generisch aus WeClapps `customAttributeDefinition` abgeleitet, inklusive eines von Hand modellierten Tab-/Sektions-/Spalten-Layouts für den "Freifelder"-Tab bei Artikeln
- Interne-Notiz-Felder (`wc_interne_notiz`, für Belegarten ohne eigenes natives ERPNext-Feld dafür – Kunden/Lieferanten haben mit `customer_details`/`supplier_details` bereits ein natives Pendant, siehe unten) und Versand-Tracking-Felder (`wc_tracking_nummer`, `wc_versanddienstleister`)
- Belegketten-Verknüpfungsfelder (Angebot → Auftrag → Rechnung, Bestellung → Eingangsrechnung, Lieferung → Auftrag)
- Artikelgruppen und Hersteller aus den WeClapp-Artikeldaten
- Der vollständige WeClapp-Lagerbaum (Lager/Lagerort/Lagerplatz) als ERPNext-Warehouses
- WeClapps echte Bank-/Darlehens-/Kreditkarten-/Kassenkonten (`bankAccount`/`cashAccount`) als einzelne ERPNext-Konten, plus ein Forderungsverlust-Konto für Zahlungen ohne echte Bankbewegung dahinter (siehe Zahlungseingänge/-ausgänge unten)
- Individuelle Personenkonten (ein eigenes Debitoren-/Kreditorenkonto pro Kunde/Lieferant, statt eines gemeinsamen Sammelkontos für alle) – aus WeClapps `party.customerDebtorAccountNumber`/`supplierCreditorAccountNumber` abgeleitet, direkt über die WeClapp-ID zugeordnet (keine Namenszuordnung nötig)
- "Negative Beträge zulassen" wird auf Verkaufs- und Einkaufsseite automatisch aktiviert (nötig für Gutschriften/Rabattzeilen, die WeClapp mit negativem Betrag abbildet)
- Geschäftsjahre werden automatisch für jedes in den WeClapp-Daten tatsächlich vorkommende Kalenderjahr angelegt (aus den Datumsfeldern über alle Belegarten ermittelt), damit historische Belege nicht an einem fehlenden Fiscal Year scheitern
- Die Mengeneinheit "Nos" wird von "muss eine Ganzzahl sein" auf gebrochene Mengen umgestellt (WeClapp führt teils echte Bruchstückzahlen)
- Namensschema (WeClapps eigene Belegnummern werden als ERPNext-Namen übernommen statt ERPNexts automatischer Nummernkreise)

### Migrationen nach ERPNext

Bisher implementiert sind die folgenden Objekte (siehe `main.py`):

**Stammdaten**
- Kunden (inkl. Bankkonten, individuellem Personenkonto, Adressen, Kontakte, Zusatzfelder,
  internen WeClapp-Kommentaren – siehe unten). Hat WeClapp eine abweichende
  Rechnungs-E-Mail-Adresse hinterlegt, wird dafür ein eigener ERPNext-Kontakt angelegt und als
  primärer Kontakt gesetzt – nur so übernimmt ihn ERPNext beim Anlegen künftiger Rechnungen
  automatisch als Empfänger (ein reines Datenfeld würde ERPNext dafür nicht heranziehen)
- Lieferanten (inkl. Bankkonten, individuellem Personenkonto, internen WeClapp-Kommentaren,
  abweichender Rechnungs-E-Mail wie oben)
  - WeClapps verknüpfte Kommentare ("Kommentare"-Feature auf Kunden/Lieferanten, getrennt von der
    "Beschreibung") werden zusammen mit der Beschreibung in ERPNexts eigenes natives Feld dafür
    geschrieben (`customer_details`/`supplier_details` – "Internal notes about this
    customer/supplier", kein Custom Field nötig). Der WeClapp-Endpunkt dafür hat keinen Bulk-Modus
    (ein Request pro Kunde/Lieferant nötig), daher bewusst nur auf Kunden/Lieferanten begrenzt,
    nicht auf Belege wie Aufträge/Rechnungen ausgeweitet
- Kontakte, Adressen
- Artikel (inkl. Zusatzfelder, Preise, Artikelgruppen, Hersteller)
- CRM-Ereignisse (ein-/ausgehende Anrufe) als ERPNext Communications, verknüpft mit dem jeweiligen
  Kunden oder Lieferanten

**Transaktionsdaten**
- Angebote
- Aufträge
- Rechnungen
- Bestellungen
- Eingangsrechnungen
- Lagerbewegungen als Stock Entries – vollständige historische Nachbildung, die einzige Quelle für den ERPNext-Lagerbestand
- Lieferungen als Delivery Notes – reine Liefer-/Tracking-Belege, bewusst als Entwurf (nicht eingereicht) angelegt, da ein eingereichter Delivery Note in ERPNext immer auf den Lagerbestand bucht (es gibt dafür keinen Opt-out) und die Lagerbewegungs-Nachbildung dieselben Warenausgänge bereits abdeckt – ein eingereichter Delivery Note würde den Bestand doppelt abziehen
- Zahlungen (offene Posten) als Payment Entries, aufgelöst über WeClapps echtes Buchungsjournal (`accountingTransaction`, zugeordnet über Rechnungsnummer + beglichenen Betrag) für das korrekte Bank-/Kassenkonto und das echte Zahlungsdatum – nicht die alte Notlösung "vollständig bezahlt am Rechnungsdatum, gegen ein pauschales Konto". Zahlungen ohne echte Bankbewegung dahinter (WeClapp-Abschreibungen/Zahlungsdifferenzen, die als "bezahlt" markiert wurden, ohne dass Geld geflossen ist) werden stattdessen als Journal-Entry-Abschreibung gebucht statt als fingierte Zahlung – siehe das Modul-Docstring in `migration/payment_entry_migration.py` für die vollständige Herleitung und empirische Trefferquoten (~81 % Verkauf / ~71 % Einkauf lösen sich auf ein echtes Konto auf, der Rest sind Abschreibungen)

**Übergreifend**
- Gesperrte/insolvente Kunden, bestellgesperrte Lieferanten und inaktive Artikel aus WeClapp werden in ERPNext erst deaktiviert, nachdem alle historischen Belege, die auf sie verweisen, importiert wurden
- Der historische Lagerbaum wird wieder deaktiviert, sobald die Lagerbewegungs-/Lieferschein-Nachbildung dagegen gebucht wurde (bleibt für die Historie erhalten, wird aber für neue Belege ausgeblendet)

### Altrechnungs-Import (`legacy_invoices/`)

Separat von der regulären WeClapp-Pipeline: Rechnungen, die nur noch als PDF existieren und nie
strukturiert in WeClapp erfasst wurden, werden über `legacy_invoices/import_legacy_invoices.py`
importiert. Eine externe Vorverarbeitung extrahiert die PDFs nach `legacy_invoices/invoices.json`
(Schema siehe `legacy_invoices/FORMAT.md`); das Skript legt daraus Sales Invoices als **Entwurf**
an (bewusst nicht eingereicht – erst nach Stichprobenprüfung gegen die Original-PDFs manuell
freigeben), inklusive PDF-Anhang, unter einem eigenen Namensraum (`RE-ALT-...`), getrennt von den
regulären `RE-...`-Belegen.

### Bewusst nicht umgesetzt

Vom Nutzer nach Abschluss der Migration explizit entschieden, nicht offene Baustellen:

- **Nummernkreise für den laufenden Betrieb nach Go-Live** – bleibt dauerhaft bei WeClapps eigenen
  Belegnummern als manuell eingegebenem ERPNext-Namen; für diese konkrete Instanz bewusst als
  verzichtbar eingestuft
- **Verträge, Tickets** – nicht migriert, da die entsprechenden WeClapp-Module für diese Instanz
  nie abonniert waren (keine Daten vorhanden)
- **SEPA-Lastschriftmandate** – technisch machbar geprüft (WeClapp hat nur eine Handvoll Mandate
  gecacht, ERPNext hat kein natives SEPA-Doctype, Custom Fields auf Bank Account wären der
  pragmatische Weg gewesen), aber als "nice to have, kein Muss" nicht umgesetzt
- WeClapps vollständiges Buchungsjournal (`accountingTransaction`) wird bewusst **nicht** als
  allgemeine Journal Entries importiert – ERPNext erzeugt beim Buchen von Verkaufs-/
  Einkaufsrechnungen bereits eigene GL-Einträge, ein vollständiger Journal-Import würde alles
  doppelt buchen. Nur die oben beschriebenen gezielten Abschreibungsbuchungen (Zahlungen/offene
  Posten) nutzen das Journal, und auch dort nur zur Auflösung/Verifikation einzelner Zahlungen

### Verbleibender manueller Schritt

- `disable_legacy_warehouses()` (in `main.py`) deaktiviert den historischen Lagerbaum – sinnvoll
  erst auszuführen, wenn die Migration final für abgeschlossen erklärt wird, daher bewusst kein
  automatischer Teil von `main.py`s Standardlauf

## Für die eigene WeClapp-/ERPNext-Instanz anpassen

Dieses Projekt wurde gegen eine konkrete WeClapp- und ERPNext-Instanz entwickelt und eingestellt. Über die üblichen API-Zugangsdaten hinaus sind mehrere Dinge fest auf diese Instanz zugeschnitten und müssten für eine andere Umgebung neu geprüft bzw. neu aufgebaut werden:

- **`config.py` – jede `EN_*_ACCOUNT`-/`EN_*_ACCOUNT_TYPE`-/`EN_DEFAULT_COST_CENTER`-/`EN_DEFAULT_TAXES_AND_CHARGES`-/`EN_DEFAULT_WAREHOUSE`-/`EN_COMPANY`-/`EN_COMPANY_ABBR`-Konstante.** Das sind wörtliche Konto-/Kostenstellen-/Vorlagen-Namen, live gegen den echten ERPNext-Kontenplan dieser Instanz geprüft (SKR03-Vorlage mit deren exakter Bezeichnung). Werden sie unverändert in eine andere ERPNext-Instanz übernommen, referenzieren sie dort still Konten, die nicht existieren. Jede einzeln live prüfen (z. B. über die ERPNext-REST-API, `GET /api/resource/Account/<name>`), bevor irgendetwas ernsthaft läuft.
- **`config.EN_CUSTOM_ATTRIBUTE_EXCLUDE` / `EN_MULTISELECT_TABLE_FIELDS`.** Fest codierte WeClapp-`attributeKey`-IDs, spezifisch für die eigenen Zusatzfelder dieser Instanz (Shop-Integrations-Synchronisationsfelder, Multi-Select-Dropdowns) – eine andere WeClapp-Instanz hat andere Zusatzfelder mit anderen Keys, das muss anhand der eigenen `customAttributeDefinition.json` neu aufgebaut werden.
- **`setup.ITEM_FREIFELDER_LAYOUT`.** Das Tab-/Sektions-/Spalten-Layout des Artikel-"Freifelder"-Tabs wurde von Hand für ~44 konkrete Artikel-Zusatzfelder dieser Instanz modelliert (siehe Code-Kommentar dort) – es greift bei einer anderen WeClapp-Instanz für deren Zusatzfelder überhaupt nicht (die würden einfach mit `FAILED ... no WeClapp definition found` übersprungen). Entweder das Layout für die neuen Felder neu bauen, oder auf die generische, flache Sektion zurückfallen, die jeder andere Doctype ohnehin bekommt (siehe `setup_custom_fields()`).
- **Payment-Entry-Kontoauflösung (`payment_entry_migration.py`).** Der Abgleich über Rechnungsnummer + Betrag gegen WeClapps Buchungsjournal wurde empirisch gegen die Daten dieser Instanz validiert (~81 % Verkauf / ~71 % Einkauf Trefferquote) – diese Validierung vor dem produktiven Einsatz gegen die eigenen `salesOpenItem`/`purchaseOpenItem`/`accountingTransaction`-Daten wiederholen. Die Trefferquote hängt stark davon ab, wie konsistent die eigene WeClapp-Bankanbindung `externalRecordNumber` befüllt, was zwischen Instanzen deutlich variieren kann.
- **`setup.setup_bank_accounts()`** selbst ist datengetrieben (leitet alles aus `bankAccount.json`/`cashAccount.json`/`ledgerAccount.json` ab, keine fest codierte Kontenliste) und sollte für eine andere SKR03-basierte WeClapp-Instanz unverändert funktionieren – nur die beiden Konten-Übergruppen `EN_BANK_ACCOUNT_GROUP`/`EN_LOAN_ACCOUNT_GROUP` sowie `EN_RECEIVABLE_WRITEOFF_ACCOUNT_GROUP` in `config.py` müssen zur tatsächlichen Kontenplan-Struktur der Ziel-ERPNext-Instanz passen.
- **`config.EN_DEBTOR_ACCOUNT_GROUP` / `EN_CREDITOR_ACCOUNT_GROUP`** (Übergruppen für die individuellen Personenkonten, siehe `setup.setup_personal_accounts()`) wurden für die ursprüngliche Instanz live gegen den echten Kontenplan verifiziert (SKR03-Konvention "...mit Kontokorrent" als Pendant zu den Sammelkonten – bestätigt korrekt). Bei einer anderen Instanz trotzdem vor dem produktiven Lauf gegenprüfen, da das eine reine Namenskonvention und keine strukturelle Notwendigkeit ist.

## Installation

### Konfiguration

Repository klonen, dann die Beispiel-Konfiguration kopieren:

```bash
git clone <your-fork-url>
cd weclapp-erpnext-migration
cp config_example.py config.py
```

`config.py` öffnen und die benötigten REST-API-URLs und Zugangsdaten für WeClapp und ERPNext eintragen.
Einen API-Token in WeClapp erzeugt man unter `Meine Einstellungen > API`.

In ERPNext einen API-Token erzeugen:
```
1. Benutzerliste -> Benutzer öffnen
2. Einstellungen -> API Access
3. "Generate Keys" klicken
4. API Secret kopieren (wird nur einmal angezeigt!)
5. API Key kopieren
```

### Option 1: VS-Code Dev Container (empfohlen)

Docker und die VSCode Dev-Container-Erweiterung werden vorausgesetzt.
Ordner `weclapp-erpnext-migration` in VSCode öffnen oder per Shell:
```
code .
```
Danach über die Command Palette `Dev Containers: Reopen in container` ausführen.

### Option 2: Lokal (Debian-basierte Systeme)

Aktuelles **Python** und **pip** sowie die Pakete aus `requirements.txt` installieren:
```
sudo apt update
sudo apt install python3 python3-pip
pip3 install -r requirements.txt
```

## Verwendung

### 1. WeClapp-Datenbank cachen

Zuerst über die eingebaute Cache-Funktion ein lokales Abbild der WeClapp-Instanz erstellen:
```bash
python3 cache_weclapp.py
```
Danach liegen für jeden WeClapp-Objekttyp `.json`-Dateien in **`weclapp/cache`** (Artikel, Kunden, Lieferanten, Verkaufs-/Einkaufsaufträge und -rechnungen, Angebote, Lieferungen, Lagerorte, Lagerbewegungen, ...), PDF-Dokumente in **`weclapp/cache/documents`** und Artikelbilder in **`weclapp/cache/images`**.

### 2. ERPNext-Stammdaten einrichten

Vor der eigentlichen Belegmigration den einmaligen (aber idempotenten – beliebig wiederholbaren) Setup-Schritt ausführen, der die Zusatzfelder, Lagerorte, Artikelgruppen, Hersteller usw. anlegt, von denen die Migration selbst abhängt:
```bash
python3 setup.py
```

### 3. Nach ERPNext migrieren

```bash
python3 main.py
```
Das führt `setup.run_setup()` erneut aus und danach jeden Migrationsschritt in der in `main.py` dokumentierten Reihenfolge (Stammdaten vor Belegen, die darauf verweisen, z. B. Kunden/Artikel vor Verkaufsaufträgen, Verkaufsaufträge vor Lieferscheinen). Ein Fehler bei einem einzelnen Datensatz wird geloggt und übersprungen, statt den ganzen Lauf abzubrechen, und der komplette Lauf ist beliebig wiederholbar – bereits migrierte Belege werden anhand ihres deterministischen ERPNext-Namens übersprungen.

## Sicherheitshinweise

- **API-Schlüssel und Kundendaten gehören niemals in ein öffentliches Repository.** `config.py`, der komplette `weclapp/cache`-Ordner sowie Kontenplan-Exporte (`*.xlsx`) sind in `.gitignore` eingetragen – vor dem ersten Commit prüfen, dass `git status` keine dieser Dateien als "zu committen" anzeigt.
- Der WeClapp-Client ist strukturell auf reines Lesen beschränkt (siehe oben) – ein aktiver WeClapp-Token in `config.py` erlaubt trotzdem keine Schreibzugriffe auf WeClapp durch dieses Projekt.

## Unterstützen

Wenn dir dieses Projekt weiterhilft, freue ich mich über eine kleine Spende:

[![Spenden via PayPal](https://img.shields.io/badge/Spenden-PayPal-0070ba?logo=paypal&logoColor=white)](https://paypal.me/DrdotHouse)
