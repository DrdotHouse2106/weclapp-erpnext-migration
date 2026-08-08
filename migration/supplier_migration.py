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

    def __init__(self, en_api: ERPNextAPI, wc_data: dict, wc_custom_attribute_definitions: dict):
        """Initializes the migration wrapper.

        Args:
            en_api (ERPNextAPI): ERPNext-API-Object
            wc_data (dict): WeClapp-API-Object
        """
        super().__init__(en_api, wc_data, wc_custom_attribute_definitions)

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
            # Interne Notiz (see setup.setup_internal_note_fields) - Supplier only has
            # "description", not recordFreeText/recordOpening/note like transactional documents
            "wc_interne_notiz"  : self._map_wc_notes(fields=("description",)) or None,
        }

        # Custom Attributes (Zusatzfelder)
        transformed_data.update(self._map_custom_attributes())

        return transformed_data

    def _is_company(self) -> bool:
        """Returns if the given supplier is a company (true) or a person (false)
        """
        return not(self.wc_data["partyType"] == "PERSON")

    def _map_supplier_name(self) -> str:
        """Maps the supplier name based on the party type
        """
        return self.wc_data["company"] if self._is_company() \
            else f"{self.wc_data.get('firstName', str())} {self.wc_data.get('lastName', str())}".strip()

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
