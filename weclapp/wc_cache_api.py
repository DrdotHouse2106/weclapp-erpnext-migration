import json
from pathlib import Path
from pysondb import PysonDB
from base import ApiBase, ApiException
from .wc_doctypes import WeClappDocType

class WcCacheApi(ApiBase):
    """Class for accessing WeClapp data from cache (psysondb)
    """

    def __init__(self, base_url: str):
        """Initializes the api wrapper for local WeClapp-db cache.

        Args:
            base_url (str): Base filepath to database-files (.json)
        """
        super().__init__(base_url)
        self._open_conns = {}   # Used for storing open connections to databases
        self._custom_attribute_definitions = None
        self._article_categories = None

    def get_article_supply_sources(self) -> dict:
        """Returns the article supply sources (Bezugsquellen: Lieferant + Einkaufspreise),
        keyed by WeClapp "id".

        Returns:
            dict: Article supply sources
        """
        if getattr(self, "_article_supply_sources", None) is None:
            db_path = Path(self.base_url).joinpath("articleSupplySource.json")
            with open(db_path, "r") as f:
                raw = json.load(f)["data"]
            self._article_supply_sources = {v["id"]: v for v in raw.values()}
        return self._article_supply_sources

    def get_article_categories(self) -> dict:
        """Returns the article categories (Artikelgruppen), keyed by WeClapp "id".

        Returns:
            dict: Article categories
        """
        if self._article_categories is None:
            db_path = Path(self.base_url).joinpath("articleCategory.json")
            with open(db_path, "r") as f:
                raw_categories = json.load(f)["data"]
            self._article_categories = {v["id"]: v for v in raw_categories.values()}
        return self._article_categories

    def get_custom_attribute_definitions(self) -> dict:
        """Returns the custom attribute definitions.

        Returns:
            dict: Custom attribute definitions
        """
        if self._custom_attribute_definitions is None:
            db_path = Path(self.base_url).joinpath("customAttributeDefinition.json")
            with open(db_path, "r") as f:
                raw_definitions = json.load(f)["data"]
            # Re-key by the WeClapp "id" field: pysondb's own dict keys are random
            # internal IDs and do NOT match customAttributes[].attributeDefinitionId
            self._custom_attribute_definitions = {v["id"]: v for v in raw_definitions.values()}
        return self._custom_attribute_definitions

    def get_articles(self) -> dict:
        """Returns all articles, keyed by WeClapp "id" (for articleId -> articleNumber lookups
        on entities that reference articles by id instead of embedding articleNumber directly,
        e.g. warehouseStockMovement).

        Returns:
            dict: Articles
        """
        if getattr(self, "_articles", None) is None:
            db_path = Path(self.base_url).joinpath("article.json")
            with open(db_path, "r") as f:
                raw = json.load(f)["data"]
            self._articles = {v["id"]: v for v in raw.values()}
        return self._articles

    def get_warehouses(self) -> dict:
        """Returns all warehouses, keyed by WeClapp "id".

        Returns:
            dict: Warehouses
        """
        if getattr(self, "_warehouses", None) is None:
            db_path = Path(self.base_url).joinpath("warehouse.json")
            with open(db_path, "r") as f:
                raw = json.load(f)["data"]
            self._warehouses = {v["id"]: v for v in raw.values()}
        return self._warehouses

    def get_storage_locations(self) -> dict:
        """Returns all storage locations (Lagerorte), keyed by WeClapp "id".

        Returns:
            dict: Storage locations
        """
        if getattr(self, "_storage_locations", None) is None:
            db_path = Path(self.base_url).joinpath("storageLocation.json")
            with open(db_path, "r") as f:
                raw = json.load(f)["data"]
            self._storage_locations = {v["id"]: v for v in raw.values()}
        return self._storage_locations

    def get_storage_places(self) -> dict:
        """Returns all storage places (Lagerplätze), keyed by WeClapp "id".

        Returns:
            dict: Storage places
        """
        if getattr(self, "_storage_places", None) is None:
            db_path = Path(self.base_url).joinpath("storagePlace.json")
            with open(db_path, "r") as f:
                raw = json.load(f)["data"]
            self._storage_places = {v["id"]: v for v in raw.values()}
        return self._storage_places

    def get_sales_invoices(self) -> dict:
        """Returns all sales invoices, keyed by WeClapp "id" (for salesInvoiceId lookups on
        salesOpenItem, which references invoices by id instead of embedding invoiceNumber).

        Returns:
            dict: Sales invoices
        """
        if getattr(self, "_sales_invoices", None) is None:
            db_path = Path(self.base_url).joinpath("salesInvoice.json")
            with open(db_path, "r") as f:
                raw = json.load(f)["data"]
            self._sales_invoices = {v["id"]: v for v in raw.values()}
        return self._sales_invoices

    def get_purchase_invoices(self) -> dict:
        """Returns all purchase invoices, keyed by WeClapp "id" (for purchaseInvoiceId lookups
        on purchaseOpenItem, which references invoices by id instead of embedding
        internalInvoiceNumber).

        Returns:
            dict: Purchase invoices
        """
        if getattr(self, "_purchase_invoices", None) is None:
            db_path = Path(self.base_url).joinpath("purchaseInvoice.json")
            with open(db_path, "r") as f:
                raw = json.load(f)["data"]
            self._purchase_invoices = {v["id"]: v for v in raw.values()}
        return self._purchase_invoices

    def get_bank_accounts(self) -> dict:
        """Returns all real WeClapp bank/loan/credit-card accounts, keyed by WeClapp "id".
        Each entry's "accountId" links to a ledger account (see get_ledger_accounts()).

        Returns:
            dict: Bank accounts
        """
        if getattr(self, "_bank_accounts", None) is None:
            db_path = Path(self.base_url).joinpath("bankAccount.json")
            with open(db_path, "r") as f:
                raw = json.load(f)["data"]
            self._bank_accounts = {v["id"]: v for v in raw.values()}
        return self._bank_accounts

    def get_cash_accounts(self) -> dict:
        """Returns all WeClapp cash accounts, keyed by WeClapp "id". Same "accountId" linkage
        as get_bank_accounts().

        Returns:
            dict: Cash accounts
        """
        if getattr(self, "_cash_accounts", None) is None:
            db_path = Path(self.base_url).joinpath("cashAccount.json")
            with open(db_path, "r") as f:
                raw = json.load(f)["data"]
            self._cash_accounts = {v["id"]: v for v in raw.values()}
        return self._cash_accounts

    def get_ledger_accounts(self) -> dict:
        """Returns WeClapp's full SKR03 ledger account tree, keyed by WeClapp "id" (7.5k+
        entries - resolves the "accountId" on bank/cash accounts and accountingTransaction
        transaction details to a real SKR03 accountNumber/description).

        Returns:
            dict: Ledger accounts
        """
        if getattr(self, "_ledger_accounts", None) is None:
            db_path = Path(self.base_url).joinpath("ledgerAccount.json")
            with open(db_path, "r") as f:
                raw = json.load(f)["data"]
            self._ledger_accounts = {v["id"]: v for v in raw.values()}
        return self._ledger_accounts

    def get_accounting_transaction_payment_index(self) -> dict:
        """Builds an index over WeClapp's accounting journal (accountingTransaction) for
        resolving a payment to the real bank/cash account and date it was actually settled with -
        see payment_entry_migration.py for how this is used and why (empirically the only
        reliable payment->account link; bankTransactionId/cashTransactionId on
        paymentApplications do NOT reliably indicate a real payment happened at all).

        Keyed by (accountingTransaction type, externalRecordNumber, bank/cash-side amount),
        rounded to 2 decimals - only accountingTransactions with a transactionDetail touching a
        real bank/cash account (see get_bank_accounts()/get_cash_accounts()) are included.

        Returns:
            dict: (type, externalRecordNumber, amount) -> list[(accountingTransaction, ledger_account_id)]
        """
        if getattr(self, "_accounting_transaction_payment_index", None) is None:
            real_account_ids = set(v["accountId"] for v in self.get_bank_accounts().values()) | \
                set(v["accountId"] for v in self.get_cash_accounts().values())

            db_path = Path(self.base_url).joinpath("accountingTransaction.json")
            with open(db_path, "r") as f:
                raw = json.load(f)["data"]

            index = {}
            for tx in raw.values():
                if tx.get("type") not in ("INCOMING_PAYMENT", "OUTGOING_PAYMENT"):
                    continue
                ref = tx.get("externalRecordNumber")
                if not ref:
                    continue
                for detail in tx.get("transactionDetails", []) or []:
                    account_id = detail.get("accountId")
                    if account_id not in real_account_ids:
                        continue
                    amount = round(abs(float(detail.get("amount") or 0)), 2)
                    key = (tx["type"], str(ref), amount)
                    index.setdefault(key, []).append((tx, account_id))
            self._accounting_transaction_payment_index = index
        return self._accounting_transaction_payment_index


    def open(self):
        """Opens the api connection.
        """
        # Checks the base file path
        path = Path(self.base_url)
        if not path.exists() or not path.is_dir():
            raise ApiException(
                message=f"Base file path '{self.base_url}' does not exist or is not a directory.",
                method="open",
                url=self.base_url
            )

    def close(self):
        """Closes the api connection.
        """
        pass

    def _get_db(self, doctype: WeClappDocType|str) -> PysonDB:
        """Returns the database for the given DocType.

        Args:
            doctype (WeClappDocType|str): DocType to get the database from

        Returns:
            PysonDB: Database
        """
        doctype_str = doctype.value if isinstance(doctype, WeClappDocType) else doctype

        # Checks if database is already open
        if self._open_conns.get(doctype_str, None):
            return self._open_conns[doctype_str]

        # Opens the database
        db_path = Path(self.base_url).joinpath(f"{doctype_str}.json")
        try:
            self._open_conns[doctype_str] = PysonDB(str(db_path))
            return self._open_conns[doctype_str]
        except Exception as e:
            raise ApiException(
                message=f"Could not get database for DocType '{doctype_str}'.",
                method="_get_db",
                url=self.base_url
            ) from e
        
    def _get_by_db_id(self, doctype: WeClappDocType|str, id: str) -> dict:
        """Returns the object with the given id from the given DocType.

        Args:
            doctype (str): DocType to get the object from
            id (str): ID of the object

        Returns:
            dict: Object
        """
        return self._get_db(doctype).get_by_id(id)

    def get_all(self, doctype: WeClappDocType|str) -> list:
        """Returns all objects of the given DocType.

        Args:
            doctype (str): DocType to get all objects from

        Returns:
            list: List of objects
        """
        return list(self._get_db(doctype).get_all().values())

    def get(self, doctype: WeClappDocType|str, id: str) -> dict:
        """Returns the object with the given name and DocType.

        Args:
            doctype (str): DocType of the object
            name (str): Name of the object

        Returns:
            dict: Object
        """
        return self._get_db(doctype).get_by_query(lambda x: x["id"] == id)

    def create(self, doctype: WeClappDocType|str, data: dict) -> dict:
        """Creates a new object of the given DocType.

        Args:
            doctype (str): DocType of the object
            data (dict): Data of the object

        Returns:
            dict: Created object
        """
        return self._get_by_db_id(doctype, self._get_db(doctype).add(data))
    
    def create_many(self, doctype: WeClappDocType|str, data : list) -> None:
        """Creates multiple new entities of the DocType
        
        Args:
            doc_type (WeClappDocType): DocType to create the entities for
            data (list): Data to fill the entities with
        """
        self._get_db(doctype).add_many(data)

    def update(self, doctype: WeClappDocType|str, id: str, data: dict) -> dict:
        """Updates the object with the given name and DocType.

        Args:
            doctype (str): DocType of the object
            name (str): Name of the object
            data (dict): Data of the object

        Returns:
            dict: Updated object
        """
        updated_ids = self._get_db(doctype).update_by_query(lambda x: x["id"] == id, data)
        if len(updated_ids) > 0:
            return self._get_by_db_id(updated_ids[0])

    def delete(self, doctype: WeClappDocType|str, id: str) -> None:
        """Deletes the object with the given name and DocType.

        Args:
            doctype (str): DocType of the object
            name (str): Name of the object
        """
        self._get_db(doctype).delete_by_query(lambda x: x["id"] == id)

    def get_count(self, doctype: WeClappDocType|str) -> int:
        """Returns the count of objects of the given DocType.

        Args:
            doctype (str): DocType to get the count from

        Returns:
            int: Count of objects
        """
        raise NotImplementedError("get_count is not implemented for WcCacheApi")

    def search(self, doctype: WeClappDocType|str, field: str, value: str) -> list:
        """Returns all objects of the given DocType with the given field-value.

        Args:
            doctype (str): DocType to search in
            field (str): Name of the field to check for
            value (str): The value to search for

        Returns:
            list: List of objects
        """
        return self._get_db(doctype).get_by_query(lambda x: x[field] == value)