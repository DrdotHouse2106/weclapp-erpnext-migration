# WeClapp → ERPNext Migration

*[Deutsche Version](README.md)*

A Python project for migrating data from the [WeClapp](https://www.weclapp.com/) ERP system to the open-source ERP system [ERPNext](https://erpnext.com), using the REST APIs of both products.

Originally based on a template by [fglashauser](https://github.com/fglashauser/weclapp-erpnext-migration), since heavily extended and customized for a concrete WeClapp-to-ERPNext migration.

### Important note

The project isn't complete yet and is still under active development - see "Next on the roadmap" below for what's still missing.

## How it works

The migration runs in three deliberately separate phases:

1. **Caching** (`cache_weclapp.py`): Reads every relevant WeClapp object once via the WeClapp REST API and stores it locally as JSON (using [PysonDB](https://github.com/pysonDB/pysonDB) as a simple file-based database). Original documents (PDFs) and article images are downloaded alongside it.
2. **Setup** (`setup.py`): Creates the ERPNext master data and structures the actual migration depends on - custom fields, warehouses, item groups, manufacturers, bank accounts, naming schemes, etc. Idempotent, so it can be re-run any number of times without creating duplicates.
3. **Migration** (`main.py`): Transfers the actual records from the local cache into ERPNext, in a fixed order that respects the dependencies between documents (e.g. customers before invoices, sales orders before delivery notes).

Separating caching from migration has one key benefit: the actual migration no longer needs a **live WeClapp connection** and can be re-run as often as needed against the same, consistent snapshot of data - e.g. after a failed partial run, or to test new migration steps against the exact same source data. Since WeClapp access was temporarily unavailable while this project was being developed, this cache-first approach was built in from the start.

**Write-safety towards WeClapp:** the WeClapp API client (`weclapp/wc_api.py`) is deliberately read-only - `create()`/`update()`/`delete()` refuse every call, and even at the HTTP level any non-GET request is rejected outright. The migration only ever reads WeClapp data once, during caching; every write operation targets ERPNext exclusively.

Every migration step is idempotent: ERPNext documents are created with deterministic names derived from their WeClapp numbers (`RE-2024RE1004`, `SO-10234`, ...). A re-run recognizes already-migrated records by their name and skips them instead of duplicating them. A failure on a single record is logged and skipped rather than aborting the whole run.

## Features

### Setup (`setup.py`)

Idempotent, one-time ERPNext master-data setup that must exist before the actual migration runs:

- Custom Fields, derived generically from WeClapp's `customAttributeDefinition`, including a hand-modeled Tab/Section/Column layout for the Item "Freifelder" (custom attributes) tab
- Internal-note fields (`wc_interne_notiz`) and shipment tracking fields (`wc_tracking_nummer`, `wc_versanddienstleister`)
- Document-chain link fields (Quotation → Sales Order → Sales Invoice, Purchase Order → Purchase Invoice, Delivery Note → Sales Order)
- Item Groups and Manufacturers derived from WeClapp's article data
- The full WeClapp Warehouse/Storage Location/Storage Place tree as ERPNext Warehouses
- WeClapp's real bank/loan/credit-card/cash accounts (`bankAccount`/`cashAccount`) as individual ERPNext Accounts, plus a receivable write-off account for payments with no real bank movement behind them (see Payment Entries below)
- Naming (WeClapp's own document numbers are kept as ERPNext names instead of ERPNext's own naming series)

### Migrations to ERPNext

Currently implemented (see `main.py`):

**Master data**
- Customers (incl. their bank accounts, addresses, contacts, custom fields)
- Suppliers (incl. bank accounts)
- Contacts, Addresses
- Articles / Items (incl. custom fields, item prices, item groups, manufacturers)

**Transactional data**
- Quotations
- Sales Orders
- Sales Invoices
- Purchase Orders
- Purchase Invoices
- Warehouse Stock Movements as Stock Entries - full historical replay, the sole source for the ERPNext stock ledger
- Shipments as Delivery Notes - pure delivery/tracking records (`update_stock=0`), since the Stock Entry replay already covers the same goods-out events
- Payments (open items) as Payment Entries, resolved against WeClapp's real accounting journal (`accountingTransaction`, matched via invoice number + settled amount) for the correct bank/cash account and the real settlement date - not the old "fully paid on the invoice date, against one generic account" shortcut. Payments that turn out to have no real bank/cash movement behind them (WeClapp write-offs/payment differences booked as "paid" without money ever moving) are booked as a Journal Entry write-off instead of a fabricated Payment Entry - see `migration/payment_entry_migration.py`'s module docstring for the full reasoning and empirical match rates (~81% sales / ~71% purchase resolve to a real account; the rest are write-offs)

**Cross-cutting**
- WeClapp's blocked/insolvent customers, order-blocked suppliers and inactive articles are disabled in ERPNext only after all historical documents referencing them have been imported
- The historical Warehouse tree is disabled again once the Stock Entry/Delivery Note replay has posted against it (kept for history, hidden from pickers for new transactions)

### Next on the roadmap

- Naming series for day-to-day operation after go-live (documents currently need their name entered manually, since WeClapp's own numbers are kept during the migration)
- Contracts, Sepa Mandates, Tickets
- WeClapp's full accounting journal (`accountingTransaction`) is deliberately **not** imported as general Journal Entries - ERPNext already generates its own GL entries when Sales/Purchase Invoices are submitted, so a full journal import would double-book everything. Only the targeted write-off entries described above (payments/open items) use the journal, and only to resolve/verify individual payments

## Using this for your own WeClapp/ERPNext instance

This was built and tuned against one specific WeClapp account and ERPNext instance. Beyond the usual API credentials, several things are hardcoded for that instance and need re-verifying/rebuilding for a different setup:

- **`config.py` - every `EN_*_ACCOUNT`/`EN_*_ACCOUNT_TYPE`/`EN_DEFAULT_COST_CENTER`/`EN_DEFAULT_TAXES_AND_CHARGES`/`EN_DEFAULT_WAREHOUSE`/`EN_ITEM_TAX_TEMPLATE_MAP`/`EN_COMPANY`/`EN_COMPANY_ABBR` constant.** These are literal account/cost-center/template names, checked live against this instance's real ERPNext chart of accounts (SKR03 template with its exact wording) - copy-pasting them into a different ERPNext instance will silently reference accounts that don't exist there. Verify each one live (e.g. via the ERPNext REST API, `GET /api/resource/Account/<name>`) before running anything for real.
- **`config.EN_CUSTOM_ATTRIBUTE_EXCLUDE` / `EN_MULTISELECT_TABLE_FIELDS`.** Hardcoded WeClapp `attributeKey` IDs specific to this instance's own custom fields (shop-integration sync fields, multi-select dropdowns) - a different WeClapp account has different custom fields with different keys, so these need to be rebuilt from scratch against `customAttributeDefinition.json`.
- **`setup.ITEM_FREIFELDER_LAYOUT`.** The Item "Freifelder" tab's tab/section/column layout was hand-modeled to match this instance's ~44 specific article custom fields (see the code comment on it) - it will not pick up a different WeClapp account's custom fields at all (they'd just be skipped with a `FAILED ... no WeClapp definition found` log). Either rebuild the layout for the new account's fields, or fall back to the generic per-doctype flat section every other doctype already gets (see `setup_custom_fields()`).
- **Payment Entry account resolution (`payment_entry_migration.py`).** The invoice-number+amount match against WeClapp's accounting journal was empirically validated against this instance's data (~81% sales / ~71% purchase match rate) - re-run that same validation against a new account's own `salesOpenItem`/`purchaseOpenItem`/`accountingTransaction` data before trusting it; match rates depend on how consistently that WeClapp account's bank-feed integration fills in `externalRecordNumber`, which can vary a lot between accounts.
- **`setup.setup_bank_accounts()`** itself is data-driven (derives everything from `bankAccount.json`/`cashAccount.json`/`ledgerAccount.json`, no hardcoded account list) and should work unmodified for another SKR03-based WeClapp account - only the `EN_BANK_ACCOUNT_GROUP`/`EN_LOAN_ACCOUNT_GROUP`/`EN_RECEIVABLE_WRITEOFF_ACCOUNT_GROUP` parent-group names in `config.py` need to match the target ERPNext's actual chart-of-accounts structure.

## Installation

### Configuration

Clone the repository, then copy the example configuration:

```bash
git clone <your-fork-url>
cd weclapp-erpnext-migration
cp config_example.py config.py
```

Open `config.py` and set the needed REST-API URLs and keys for both WeClapp and ERPNext.
To generate an API token in WeClapp, go to `My settings > API` and generate one.

In ERPNext, get an API token by generating an API key and API secret:
```
1. User list -> Open a user
2. Settings -> API Access section
3. Click on Generate Keys
4. Copy API secret (it won't show again!)
5. Copy API key
```

### Option 1: Open with VS Code Dev Container (recommended)

Make sure you have Docker installed and the VSCode Dev-Container extension.
Open the folder `weclapp-erpnext-migration` in VSCode, or run from the shell:
```
code .
```
Then open the command palette and run `Dev Containers: Reopen in container`.

### Option 2: Open locally (Debian-based systems)

Make sure you have current **Python** and **pip** packages, and install the packages in `requirements.txt`:
```
sudo apt update
sudo apt install python3 python3-pip
pip3 install -r requirements.txt
```

## Usage

### 1. Caching the WeClapp database

First create a local backup of your WeClapp instance using the built-in caching function:
```bash
python3 cache_weclapp.py
```
After that you will have `.json` files in **`weclapp/cache`** for every WeClapp object type (articles, customers, suppliers, sales/purchase orders and invoices, quotations, shipments, warehouses, stock movements, ...), PDF documents in **`weclapp/cache/documents`**, and article images in **`weclapp/cache/images`**.

### 2. Setting up ERPNext master data

Before migrating any actual documents, run the one-time (but idempotent - safe to re-run) setup step, which creates the custom fields, warehouses, item groups, manufacturers etc. that the migration itself depends on:
```bash
python3 setup.py
```

### 3. Migrating to ERPNext

```bash
python3 main.py
```
This runs `setup.run_setup()` again and then every migration step in the order documented in `main.py` (master data before documents that reference it, e.g. customers/articles before sales orders, sales orders before their delivery notes). A failure on a single record is logged and skipped rather than aborting the whole batch, and the whole run is safe to re-run - already migrated documents are skipped by their deterministic ERPNext name.

## Security notes

- **API keys and customer data must never end up in a public repository.** `config.py`, the entire `weclapp/cache` folder, and chart-of-accounts exports (`*.xlsx`) are all listed in `.gitignore` - before your first commit, check that `git status` doesn't show any of these as pending.
- The WeClapp client is structurally limited to reading only (see above) - an active WeClapp token in `config.py` still doesn't grant this project any write access to WeClapp.
