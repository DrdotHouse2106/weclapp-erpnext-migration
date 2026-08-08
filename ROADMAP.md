# Roadmap: WeClapp zu ERPNext Migration

Dieses Dokument beschreibt den aktuellen Stand des Migrationsprojekts von WeClapp nach ERPNext, was bereits fertig ist, was noch offen ist, und was bewusst nicht umgesetzt wird.

## Projektziel

Die vollständige und korrekte Übertragung aller relevanten Geschäftsdaten von der WeClapp-Instanz zur ERPNext-Instanz.

## Aktueller Stand

Alle drei Phasen (Cachen, Setup, Migration) sind implementiert und offline vollständig gegen den realen WeClapp-Datenbestand verifiziert. Ein erster produktiver Lauf gegen die echte ERPNext-Instanz steht für die neueren Bausteine (Bankkonten-Setup, Zahlungs-/Abschreibungsmigration) noch aus – siehe "Nächste Schritte".

---

## Abgeschlossen

### Grundstruktur
- [x] API-Wrapper für WeClapp (rein lesend, siehe Sicherheitshinweise im README) und ERPNext
- [x] Cache-Schicht (PysonDB, `cache_weclapp.py`) inkl. Original-Dokumenten- und Artikelbild-Download
- [x] Generisches Migrations-Grundgerüst (`BaseMigration`, `MigrationWrapper`) mit Idempotenz (deterministische Namen, Skip bei bereits vorhandenen Belegen) und Fehlertoleranz pro Datensatz

### Setup (`setup.py`)
- [x] Zusatzfelder (Custom Fields), generisch aus WeClapps `customAttributeDefinition`
- [x] Hand-modelliertes Tab-/Sektions-/Spalten-Layout für den Artikel-"Freifelder"-Tab
- [x] Multi-Select-Felder als echte Table-MultiSelect-Dropdowns
- [x] Interne-Notiz-Felder und Versand-Tracking-Felder
- [x] Belegketten-Verknüpfungsfelder (Angebot → Auftrag → Rechnung, Bestellung → Eingangsrechnung, Lieferung → Auftrag)
- [x] Artikelgruppen und Hersteller
- [x] Vollständiger WeClapp-Lagerbaum (Lager/Lagerort/Lagerplatz) als ERPNext-Warehouses
- [x] Echte Bank-/Darlehens-/Kreditkarten-/Kassenkonten aus WeClapp als ERPNext-Konten, datengetrieben über die SKR03-Kontonummern-Konvention (kein fest codierter Konten-Katalog)
- [x] Forderungsverlust-Konto (2400) für Zahlungen ohne echte Bankbewegung
- [x] Namensschema (`autoname = Prompt`) für alle Belege mit WeClapp-abgeleitetem Namen

### Stammdaten-Migration
- [x] Kunden (inkl. Bankkonten, Adressen, Kontakte, Zusatzfelder) – Upsert-fähig, Validierung berücksichtigt sowohl Firmen- als auch Privatkunden ohne Firmenname
- [x] Lieferanten (inkl. Bankkonten) – gleiche Upsert-/Validierungslogik
- [x] Adressen, Kontakte
- [x] Artikel (inkl. Zusatzfelder, Verkaufs- und Einkaufspreise, Artikelgruppen, Hersteller, Bilder, Barcodes)

### Transaktionsdaten-Migration
- [x] Angebote
- [x] Aufträge (Verkauf)
- [x] Rechnungen (inkl. Steuer-Mapping für alle real vorkommenden deutschen und EU-Steuersätze, OSS-Verfahren für EU-Ausland)
- [x] Bestellungen (Einkauf)
- [x] Eingangsrechnungen (inkl. Einfuhrumsatzsteuer, Vorsteuer-Mapping)
- [x] Lagerbewegungen als Stock Entries – vollständige historische Nachbildung des Lagerbestands
- [x] Lieferscheine als Delivery Notes (`update_stock=0`, keine doppelte Bestandsbuchung)
- [x] Zahlungseingänge/-ausgänge (offene Posten) als Payment Entries, aufgelöst über das echte WeClapp-Buchungsjournal (Rechnungsnummer + Betrag) für Konto und Datum
- [x] Abschreibungen/Zahlungsdifferenzen ohne echte Bankbewegung als Journal-Entry-Ausbuchung statt fingierter Zahlung

### Übergreifend
- [x] Rückwärts-Verknüpfung der Belegkette nach Abschluss aller Importe
- [x] Nachträgliches Anwenden von WeClapp-Sperren (gesperrte/insolvente Kunden, bestellgesperrte Lieferanten, inaktive Artikel)
- [x] Deaktivierung des historischen Lagerbaums nach abgeschlossener Bestands-Nachbildung

---

## In Arbeit / als Nächstes

*Ungefähr nach Priorität, nicht nach Aufwand sortiert.*

1. **Erster Live-Lauf der Bankkonten- und Zahlungsmigration**
   Bisher nur offline gegen den vollständigen gecachten Datenbestand verifiziert (7.711 offene Posten, 0 Fehler, korrekte Kontensummen). `setup_bank_accounts()` und die Zahlungs-/Abschreibungsmigration müssen noch einmal live gegen die echte ERPNext-Instanz laufen, zuerst mit einem kleinen Teillauf, dann stichprobenartig geprüft (richtiges Konto, richtiges Datum, korrekte Verknüpfung zur Rechnung).

2. **Verifikation: Forderungsverlust-Konto (2400) für die Einkaufsseite**
   Das Konto "2400 - Forderungsverluste" wurde nur anhand von zwei Verkaufsbeispielen bestätigt (Kunden-Forderungsausfälle). Für die Einkaufsseite (Zahlungsdifferenzen bei Lieferantenrechnungen) ist es fachlich nicht zweifelsfrei das richtige Konto – aktuell wird es testweise auch dort verwendet, mit entsprechendem Hinweis im Code. Muss vor dem produktiven Lauf der Einkaufszahlungen final geklärt werden.

3. **Nummernkreise für den laufenden Betrieb nach Go-Live**
   Belege benötigen aktuell einen manuell vergebenen Namen (`autoname = Prompt`), da WeClapps eigene Nummern während der Migration übernommen werden. Für den Tagesbetrieb nach dem Go-Live braucht es echte ERPNext-Nummernkreise, die nahtlos an die zuletzt migrierte WeClapp-Nummer anschließen.

4. **Weitere WeClapp-Objekte**
   - [ ] Verträge
   - [ ] SEPA-Mandate
   - [ ] Tickets

---

## Bewusst nicht umgesetzt

- **Vollständiger Import von WeClapps Buchungsjournal (`accountingTransaction`) als allgemeine Journal Entries.** ERPNext erzeugt beim Buchen von Verkaufs-/Einkaufsrechnungen bereits eigene GL-Einträge; ein vollständiger Journal-Import würde alles doppelt buchen. Das Journal wird ausschließlich gezielt genutzt, um einzelne Zahlungen einem echten Bankkonto zuzuordnen bzw. als Abschreibung zu erkennen (siehe `migration/payment_entry_migration.py`).
- **Schreibender Zugriff auf WeClapp.** Der WeClapp-API-Client ist strukturell auf reines Lesen beschränkt (siehe README, Abschnitt "Sicherheitshinweise") – die Migration verändert niemals Daten in WeClapp, auch nicht rückwirkend (z. B. um Belege nach erfolgreicher Migration dort als "übertragen" zu markieren).
