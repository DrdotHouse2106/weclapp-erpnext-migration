import config
from .base_migration import BaseMigration
from .address_migration import AddressMigration
from .contact_migration import ContactMigration
from .bank_account_migration import BankAccountMigration
from erpnext import ERPNextAPI, ERPNextDocType, ERPNextHelper
from weclapp import WeClappDocType

class CustomerMigration(BaseMigration):
    """Migration wrapper for a customer object from WeClapp to ERPNext.
    """

    def __init__(self, en_api: ERPNextAPI, wc_data: dict, wc_custom_attribute_definitions: dict):
        """Initializes the migration wrapper.

        Args:
            en_api (ERPNextAPI): ERPNext-API-Object
            wc_data (dict): WeClapp-API-Object
        """
        super().__init__(en_api, wc_data, wc_custom_attribute_definitions)

    def get_doctype(self) -> ERPNextDocType:
        return ERPNextDocType.CUSTOMER

    def get_wc_doctype(self) -> WeClappDocType:
        return WeClappDocType.CUSTOMER

    def migrate(self) -> dict:
        """Migrates a given WeClapp-Object and creates it in ERPNext.

        Returns:
            dict: Created ERPNext-Object
        """
        if not self.validate():
            return None

        # Base data
        en_data = self._transform()

        # Upsert: if the customer already exists (same WeClapp number), update it with the
        # current field mapping instead of failing with a duplicate error. Child entities
        # (addresses/contacts/bank accounts/documents) are skipped then to avoid duplicating them.
        existing = self._en_api.get(ERPNextDocType.CUSTOMER, en_data.get("name"))
        if existing:
            update_data = {k: v for k, v in en_data.items() if k != "name"}
            return self._en_api.update(ERPNextDocType.CUSTOMER, en_data.get("name"), update_data)["data"]

        # Addresses
        en_addresses = list()
        for addr in self.wc_data.get("addresses", []):
            addr_migration = AddressMigration(self._en_api, addr, self.wc_data)
            if addr_migration.validate():               # Only migrate valid addresses
                en_addr = addr_migration.migrate()      # Migrate address
                en_addresses.append(en_addr)            # Add address to list
                if addr_migration.is_primary():         # Primary address
                    en_data["customer_primary_address"] = en_addr["name"]
                    en_data["territory"] = ERPNextHelper.get_territory_string(en_addr["country"])

        # Contacts
        en_contacts = list()
        for contact in self.wc_data.get("contacts", []):
            contact_migration = ContactMigration(self._en_api, contact, self.wc_data, self.wc_custom_attribute_definitions)
            if contact_migration.validate():            # Only migrate valid contacts
                en_contact = contact_migration.migrate()
                en_contacts.append(en_contact)          # Add contact to list
                if contact_migration.is_primary():      # Primary contact
                    en_data["customer_primary_contact"] = en_contact["name"]

        # Create customer in ERPNext
        en_customer = self._en_api.create(ERPNextDocType.CUSTOMER, en_data)

        # Link addresses to customer
        self._link_addresses(en_customer, en_addresses)

        # Link contacts to customer
        self._link_contacts(en_customer, en_contacts)

        # Bank Accounts (can be disabled via config.EN_MIGRATE_BANK_ACCOUNTS)
        if config.EN_MIGRATE_BANK_ACCOUNTS:
            for bank_account in self.wc_data.get("bankAccounts", []):
                bank_account_migration = BankAccountMigration(self._en_api, bank_account, en_customer,
                                                                party_type=ERPNextDocType.CUSTOMER.value)
                if bank_account_migration.validate():
                    bank_account_migration.migrate()

        # Upload WeClapp documents (invoices, data sheets, etc.)
        self.upload_weclapp_documents(en_customer.get("name", str()))

        return en_customer


    def validate(self) -> bool:
        """
        Validates the given data.
        PERSON parties (the vast majority of customers) have no "company" - any usable display
        name (company for organizations, first/last name for persons) is enough.

        Returns:
            bool: True if valid, False if not
        """
        return bool(self.wc_data.get("partyType") and
                    self.wc_data.get("customerNumber") and
                    self._map_customer_name())

    def _transform(self) -> dict:
        """Transforms the data from WeClapp to ERPNext.

        Returns:
            dict: Transformed data
        """
        transformed_data = {
            "name"                          : self.wc_data.get("customerNumber", None),
            "customer_name"                 : self._map_customer_name(),
            "customer_group"                : self._map_customer_group(),
            "customer_type"                 : self._map_customer_type(),
            "website"                       : self.wc_data.get("website", None),
            "tax_id"                        : self.wc_data.get("vatRegistrationNumber", None),
            "phone"                         : ERPNextHelper.standardize_phone_number(self.wc_data.get("phone", str())),
            "email"                         : self.wc_data.get("email", None),
            "default_currency"              : self.wc_data.get("currencyName", None),
            # Always imported enabled - ERPNext refuses documents for disabled parties, and the
            # historical invoices/orders still need to be imported. WeClapp's blocked/insolvent
            # flags are applied afterwards by main.py's apply_wc_blocks() final phase.
            "disabled"                      : 0,
            "is_frozen"                     : 0,
            # Interne Notiz (see setup.setup_internal_note_fields) - Customer only has
            # "description", not recordFreeText/recordOpening/note like transactional documents
            "wc_interne_notiz"              : self._map_wc_notes(fields=("description",)) or None,
        }

        # Custom Attributes (Zusatzfelder)
        transformed_data.update(self._map_custom_attributes())

        return transformed_data
    
    def _is_company(self) -> bool:
        """Returns if the given customer is a company (true) or a person (false)
        """
        return not(self.wc_data["partyType"] == "PERSON")
    
    def _map_customer_name(self) -> str:
        """Maps the customer name based on the party type
        """
        return self.wc_data["company"] if self._is_company() \
            else f"{self.wc_data.get('firstName', str())} {self.wc_data.get('lastName', str())}".strip()
        
    def _map_customer_group(self) -> str:
        """Maps the customer group based on the party type
        """
        return config.EN_CUSTOMER_GROUP_COMPANY if self._is_company() else config.EN_CUSTOMER_GROUP_INDIVIDUAL
    
    def _map_customer_type(self) -> str:
        """Maps the customer type
        """
        return "Company" if self._is_company() else "Individual"
    
    def _link_addresses(self, en_customer: dict, en_addresses: list):
        """Links the addresses to the given customer
        """
        for en_addr in en_addresses:
            self._en_api.create_link(ERPNextDocType.CUSTOMER, en_customer["name"], \
                                     ERPNextDocType.ADDRESS, en_addr["name"])
            
    def _link_contacts(self, en_customer: dict, en_contacts: list):
        """Links the contacts to the given customer
        """
        for en_contact in en_contacts:
            self._en_api.create_link(ERPNextDocType.CUSTOMER, en_customer["name"], \
                                     ERPNextDocType.CONTACT, en_contact["name"])