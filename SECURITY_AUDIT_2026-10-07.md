# Sicherheitsaudit 2026-10-07 (`master`)

Issues sind in diesem Fork deaktiviert, daher liegen die Befunde hier als Datei. Die Datenschutz-Funde
(personenbezogene Daten in `CLAUDE.md` und in der Historie) wurden am 2026-10-07 per History-Rewrite
bereinigt und sind hier nicht mehr aufgeführt.

## Hoch

### H1 – Alle Anhänge werden als öffentliche Dateien hochgeladen
**Status:** Code bestätigt, Frappe-Default plausibel
**Stelle:** `erpnext/en_api.py:266-276` (`upload_file`, `data={"doctype": …, "docname": …}` ohne `is_private`).

Frappes `upload_file` setzt bei fehlendem `is_private` den Wert 0 → Datei liegt unter `/files/<Name>` und ist
ohne Login abrufbar. Betroffen: `upload_weclapp_documents()` (`base_migration.py:309-338`) für Rechnungen,
Angebote, Aufträge, Lieferscheine, Kunden-, Lieferanten- und Artikeldokumente sowie `_upload_article_images()`
(`article_migration.py:131`). WeClapp-PDF-Namen wie `Rechnung_<nr>.pdf` sind erratbar.

- [ ] `data={..., "is_private": 1}` im Upload (Artikelbilder bewusst öffentlich lassen, falls gewünscht)
- [ ] Bestand bereinigen: alle `File`-Dokumente mit `attached_to_doctype` in den Belegarten und `is_private=0` auf 1 setzen; `Item.image`-URLs danach aktualisieren

## Mittel

### M1 – `wc_customer_api.py` umgeht die Read-only-Garantie des WeClapp-Clients
**Status:** bestätigt
**Stelle:** `weclapp/wc_customer_api.py:21-33` (rohe `requests.post/put/delete`), exportiert in `weclapp/__init__.py:1`.
Aktuell nirgends aufgerufen, widerspricht aber README und CLAUDE.md („strukturell read-only").
- [ ] Datei löschen und Export aus `__init__.py` entfernen

### M2 – Dokumentnamen ohne URL-Encoding im REST-Pfad
**Status:** Code bestätigt, Ausnutzung plausibel
**Stellen:** `erpnext/en_api.py:143, 170, 200, 211` (`f"{resource_url}/{id}"`).
Artikelnummer `1234/AB` → `GET /api/resource/Item/1234/AB` → 404 → gilt als „nicht vorhanden" → Duplikat
oder Update auf falsche Ressource; `#`/`?` schneiden ab.
- [ ] Zentral `urllib.parse.quote(str(id), safe="")` in `get`/`update`/`delete`/`create_link`

### M3 – Path Traversal über WeClapp-Dateinamen beim Cache-Download
**Status:** Code bestätigt, Ausnutzung plausibel
**Stellen:** `weclapp/wc_cache_wrapper.py:101-107` (`base_path.joinpath(document["name"])`), `weclapp/wc_api.py:235`.
Absoluter Name ersetzt die Basis, `../` traversiert → beliebiges Schreiben mit Rechten des ausführenden
Nutzers. Voraussetzung: Angreifer kann Dokumente in WeClapp benennen.
- [ ] `Path(document["name"]).name`, bei `""`/`.`/`..` auf `f"{document['id']}.bin"` ausweichen
- [ ] `target.resolve().relative_to(base_path.resolve())` prüfen oder nach `document["id"]` benennen
- [ ] Gleiches Muster in `cache_article_images.py:47` (praktisch nicht traversierbar, gleicher Fix)

## Niedrig

- [ ] N1 Kundendaten in weltlesbaren `/tmp`-Logs: `supervise_main.sh:10-17`, `migration_wrapper.py:84` (`response.text` mit Feldwerten). Logs ins gitignorierte Projektverzeichnis mit `umask 077`, `response.text` kürzen.
- [ ] N2 Cache-Dateien (`weclapp/cache/`, PDFs, Bilder) mit Default-Rechten 0644. `os.umask(0o077)` in `cache_weclapp.py`/`main.py`.
- [ ] N3 Rohes WeClapp-HTML in Text-Editor-Felder (`article_migration.py:152`, `invoice_migration.py:185, 239-244`, `purchase_invoice_migration.py:202`, `crm_event_migration.py:97`, `wc_interne_notiz`). Nur Frappes Sanitizer schützt; zusätzlich `html.unescape` bis Fixpunkt + `bleach.clean`.
- [ ] N4 `setup.py:82, 140`: WeClapp-`selectableValues` mit Zeilenumbruch erzeugen zusätzliche Select-Optionen.
- [ ] N5 `requirements.txt`: ungenutzte `paramiko`/`bcrypt`/`PyNaCl` entfernen, Versionen pinnen. `supervise_main.sh:22` `stat -f %m` ist macOS-Syntax, kein `set -euo pipefail`.
- [ ] N6 `config_example.py:11` `http://`-Beispiel-URL: Kommentar „immer https://" ergänzen (Basic-Auth im Klartext).

## Geprüft und sauber
Keine Tokens/Keys je committet; `config.py`, Cache, `*.xlsx`, `legacy_invoices` nie im Git; `_request()`-GET-Sperre
und `create/update/delete`-Verweigerung in `wc_api.py` intakt; Credentials nur in Headern; kein `verify=False`;
Timeouts überall; Filter/Fields per `json.dumps`; kein `eval/exec/pickle/yaml/subprocess`.
