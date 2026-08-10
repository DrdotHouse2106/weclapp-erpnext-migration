import config
from .base_migration import BaseMigration
from .address_migration import AddressMigration
from .contact_migration import ContactMigration
from .bank_account_migration import BankAccountMigration
from erpnext import ERPNextAPI, ERPNextDocType, ERPNextHelper
from weclapp import WeClappDocType

class SupplierMigration(BaseMigration):
    """Migration wrapper for a supplier object from WeClapp to ERPNext.
    """

    def __init__(self, en_api: ERPNextAPI, wc_data: dict, wc_custom_attribute_definitions: dict,
                 wc_parties: dict = None, wc_comments: dict = None):
        """Initializes the migration wrapper.

        Args:
            en_api (ERPNextAPI): ERPNext-API-Object
            wc_data (dict): WeClapp-API-Object
            wc_parties (dict, optional): WeClapp parties keyed by id (see WcCacheApi.get_parties()) -
                carries the supplier's individual sub-ledger account (Personenkonto) and any
                distinct invoice-email override, neither of which supplier.json itself exposes.
            wc_comments (dict, optional): WeClapp linked comments ("Kommentare"), keyed by party
                id (see WcCacheApi.get_comments()) - WeClapp's general-purpose internal-note
                feature, separate from the "description" field already covered by
                BaseMigration._map_wc_notes().
        """
        super().__init__(en_api, wc_data, wc_custom_attribute_definitions)
        self.wc_parties = wc_parties or {}
        self.wc_comments = wc_comments or {}

    def get_doctype(self) -> ERPNextDocType:
        return ERPNextDocType.SUPPLIER

    def get_wc_doctype(self) -> WeClappDocType:
        return WeClappDocType.SUPPLIER

    def migrate(self) -> dict:
        """Migrates a given WeClapp-Object and creates it in ERPNext.

        Returns:
            dict: Created ERPNext-Object
        """
        if not self.validate():
            return None

        # Base data
        en_data = self._transform()

        # Upsert: if the supplier already exists (same WeClapp number), update it with the
        # current field mapping instead of failing with a duplicate error. Child entities
        # (addresses/contacts/bank accounts/documents) are skipped then to avoid duplicating them.
        existing = self._en_api.get(ERPNextDocType.SUPPLIER, en_data.get("name"))
        if existing:
            update_data = {k: v for k, v in en_data.items() if k != "name"}
            return self._en_api.update(ERPNextDocType.SUPPLIER, en_data.get("name"), update_data)["data"]

        # Addresses
        en_addresses = list()
        for addr in self.wc_data.get("addresses", []):
            addr_migration = AddressMigration(self._en_api, addr, self.wc_data)
            if addr_migration.validate():               # Only migrate valid addresses
                en_addr = addr_migration.migrate()      # Migrate address
                en_addresses.append(en_addr)            # Add address to list
                if addr_migration.is_primary():         # Primary address
                    en_data["supplier_primary_address"] = en_addr["name"]

        # Contacts
        en_contacts = list()
        for contact in self.wc_data.get("contacts", []):
            contact_migration = ContactMigration(self._en_api, contact, self.wc_data, self.wc_custom_attribute_definitions)
            if contact_migration.validate():            # Only migrate valid contacts
                en_contact = contact_migration.migrate()
                en_contacts.append(en_contact)          # Add contact to list
                if contact_migration.is_primary():      # Primary contact
                    en_data["supplier_primary_contact"] = en_contact["name"]

        # Invoice-email override (party.salesInvoiceEmailAddressesId, see _map_invoice_email()) -
        # modeled as a real Contact, not a plain data field: ERPNext only ever picks up an email
        # address automatically (e.g. as the default recipient for a new Purchase Invoice against
        # this supplier) via supplier_primary_contact -> Contact.email_id. A Custom Field would
        # just sit there inert. Only takes over as the primary contact if WeClapp didn't already
        # give this supplier a real named one above.
        invoice_email = self._map_invoice_email()
        if invoice_email:
            en_invoice_contact = self._en_api.create(ERPNextDocType.CONTACT, {
                "first_name": "Rechnungsversand",
                "last_name": self._map_supplier_name(),
                "email_ids": [{"email_id": invoice_email, "is_primary": 1}],
            })
            en_contacts.append(en_invoice_contact)
            if "supplier_primary_contact" not in en_data:
                en_data["supplier_primary_contact"] = en_invoice_contact["name"]

        # Create supplier in ERPNext
        en_supplier = self._en_api.create(ERPNextDocType.SUPPLIER, en_data)

        # Link addresses to supplier
        self._link_addresses(en_supplier, en_addresses)

        # Link contacts to supplier
        self._link_contacts(en_supplier, en_contacts)

        # Bank Accounts (can be disabled via config.EN_MIGRATE_BANK_ACCOUNTS)
        if config.EN_MIGRATE_BANK_ACCOUNTS:
            for bank_account in self.wc_data.get("bankAccounts", []):
                bank_account_migration = BankAccountMigration(self._en_api, bank_account, en_supplier,
                                                                party_type=ERPNextDocType.SUPPLIER.value)
                if bank_account_migration.validate():
                    bank_account_migration.migrate()

        # Upload WeClapp documents (order confirmations, data sheets, etc.)
        self.upload_weclapp_documents(en_supplier.get("name", str()))

        return en_supplier

    def validate(self) -> bool:
        """
        Validates the given data.
        PERSON parties have no "company" - any usable display name (company for organizations,
        first/last name for persons) is enough.

        Returns:
            bool: True if valid, False if not
        """
        return bool(self.wc_data.get("partyType") and
                    self.wc_data.get("supplierNumber") and
                    self._map_supplier_name())

    def _transform(self) -> dict:
        """Transforms the data from WeClapp to ERPNext.

        Returns:
            dict: Transformed data
        """
        transformed_data = {
            "name"              : self.wc_data.get("supplierNumber", None),
            "supplier_name"     : self._map_supplier_name(),
            "supplier_group"    : config.EN_DEFAULT_SUPPLIER_GROUP,
            "supplier_type"     : self._map_supplier_type(),
            "website"           : self.wc_data.get("website", None),
            "tax_id"            : self.wc_data.get("vatRegistrationNumber", None),
            "mobile_no"         : ERPNextHelper.standardize_phone_number(self.wc_data.get("phone", str())),
            "email_id"          : self.wc_data.get("email", None),
            "default_currency"  : self.wc_data.get("currencyName", None),
            # Always imported enabled - blocks are applied by main.py's apply_wc_blocks() after
            # all documents are in (ERPNext refuses documents for disabled parties).
            "disabled"          : 0,
            # ERPNext's own native "Supplier Details" field - not a custom field, see
            # _map_notes_and_comments(). Combines WeClapp's "description" with its
            # separately-fetched linked comments ("Kommentare", see _map_wc_comments()).
            "supplier_details"  : self._map_notes_and_comments() or None,
            # Individual sub-ledger account (Personenkonto, see setup.setup_personal_accounts())
            "accounts"          : self._map_creditor_account(),
        }

        # Custom Attributes (Zusatzfelder)
        transformed_data.update(self._map_custom_attributes())

        return transformed_data

    def _map_notes_and_comments(self) -> str:
        """Combines the "description" field (_map_wc_notes()) with WeClapp's separately-fetched
        linked comments (_map_wc_comments()) for this supplier's party id into a single string
        for ERPNext's native "supplier_details" field (plain Text, not Text Editor - description
        is WeClapp rich-text HTML and needs stripping to avoid literal tags showing up).
        """
        notes = ERPNextHelper.strip_html(self._map_wc_notes(fields=("description",)))
        comments = self._map_wc_comments(self.wc_comments.get(self.wc_data.get("id"), []))
        return "\n".join(p for p in (notes, comments) if p)

    def _get_party(self) -> dict:
        """Resolves this supplier's richer WeClapp party record (supplier.id == party.id,
        verified 1:1 across the full cache) - carries fields supplier.json itself doesn't
        expose (see WcCacheApi.get_parties()).
        """
        return self.wc_parties.get(self.wc_data.get("id"))

    def _map_creditor_account(self) -> list:
        """Maps the supplier's individual sub-ledger account (Personenkonto,
        party.supplierCreditorAccountNumber) to ERPNext's per-company Supplier.accounts override -
        WeClapp sets this for 100% of real suppliers. The account itself is created by
        setup.setup_personal_accounts(); the name is recomputed here from the same party data
        rather than persisted, same no-shared-state pattern as ERPNextHelper.get_wc_warehouse_name().
        Falls back to the collective payable account (config.EN_PURCHASE_PAID_TO_ACCOUNT) if
        WeClapp has none set.

        Returns:
            list: [{"company": ..., "account": ...}], or [] if no Personenkonto is set
        """
        party = self._get_party()
        number = party.get("supplierCreditorAccountNumber") if party else None
        if not number:
            return []
        # .strip(): some WeClapp company names carry trailing whitespace, which would otherwise
        # silently diverge from the name setup.setup_personal_accounts() computes for the same
        # account (confirmed live: "Sattlerei Gawenda " caused a LinkValidationError).
        label = (party.get("company") or self._map_supplier_name()).strip()
        account_name = f"{ERPNextHelper.get_wc_account_name(number, label)} - {config.EN_COMPANY_ABBR}"
        return [{"company": config.EN_COMPANY, "account": account_name}]

    def _map_invoice_email(self) -> str:
        """Maps WeClapp's distinct invoice-email override (party.salesInvoiceEmailAddressesId ->
        partyEmailAddresses), if the supplier has one set - rare, most just use the general
        "email" field.

        Returns:
            str: The invoice email address, or None if no override is set
        """
        party = self._get_party()
        target_id = party.get("salesInvoiceEmailAddressesId") if party else None
        if not target_id:
            return None
        for entry in party.get("partyEmailAddresses") or []:
            if entry.get("id") == target_id:
                return entry.get("toAddresses")
        return None

    def _is_company(self) -> bool:
        """Returns if the given supplier is a company (true) or a person (false)
        """
        return not(self.wc_data["partyType"] == "PERSON")

    def _map_supplier_name(self) -> str:
        """Maps the supplier name based on the party type
        """
        return self.wc_data["company"] if self._is_company() \
            else f"{self.wc_data.get('firstName') or ''} {self.wc_data.get('lastName') or ''}".strip()

    def _map_supplier_type(self) -> str:
        """Maps the supplier type
        """
        return "Company" if self._is_company() else "Individual"

    def _link_addresses(self, en_supplier: dict, en_addresses: list):
        """Links the addresses to the given supplier
        """
        for en_addr in en_addresses:
            self._en_api.create_link(ERPNextDocType.SUPPLIER, en_supplier["name"], \
                                     ERPNextDocType.ADDRESS, en_addr["name"])

    def _link_contacts(self, en_supplier: dict, en_contacts: list):
        """Links the contacts to the given supplier
        """
        for en_contact in en_contacts:
            self._en_api.create_link(ERPNextDocType.SUPPLIER, en_supplier["name"], \
                                     ERPNextDocType.CONTACT, en_contact["name"])
