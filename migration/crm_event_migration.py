from .base_migration import BaseMigration
from erpnext import ERPNextAPI, ERPNextDocType, ERPNextHelper
from weclapp import WeClappDocType

class CrmEventMigration(BaseMigration):
    """Migration wrapper for a WeClapp crmEvent (Ereignis) to an ERPNext Communication.
    Only phone calls occur in the real data (type INCOMING_CALL/OUTGOING_CALL, ~3.9k events,
    no meetings/emails/other types) - CRM_CALL_TYPE_MAP covers exactly those two.

    A crmEvent's partyId resolves to either a Customer or a Supplier (both share the same
    WeClapp party id space) - about 2.7% resolve to neither (mostly leads, out of scope for
    this migration) and are skipped by validate().
    """

    CRM_CALL_TYPE_MAP = {
        "OUTGOING_CALL": "Sent",
        "INCOMING_CALL": "Received",
    }

    def __init__(self, en_api: ERPNextAPI, wc_data: dict, wc_custom_attribute_definitions: dict,
                 wc_parties: dict = None):
        """Initializes the migration wrapper.

        Args:
            en_api (ERPNextAPI): ERPNext-API-Object
            wc_data (dict): WeClapp-API-Object (a single crmEvent)
            wc_custom_attribute_definitions (dict): WeClapp custom attribute definitions
            wc_parties (dict, optional): WeClapp parties keyed by id (see WcCacheApi.get_parties())
        """
        super().__init__(en_api, wc_data, wc_custom_attribute_definitions)
        self.wc_parties = wc_parties or {}

    def get_doctype(self) -> ERPNextDocType:
        return ERPNextDocType.COMMUNICATION

    def get_wc_doctype(self) -> WeClappDocType:
        return WeClappDocType.CRM_EVENT

    def _get_party(self) -> dict:
        return self.wc_parties.get(self.wc_data.get("partyId"))

    def _get_reference(self) -> tuple[str, str]:
        """Resolves the crmEvent's partyId to an (reference_doctype, reference_name) tuple,
        or (None, None) if it resolves to neither a customer nor a supplier.
        """
        party = self._get_party()
        if not party:
            return None, None
        if party.get("customerNumber"):
            return ERPNextDocType.CUSTOMER.value, party["customerNumber"]
        if party.get("supplierNumber"):
            return ERPNextDocType.SUPPLIER.value, party["supplierNumber"]
        return None, None

    def validate(self) -> bool:
        """
        Validates the given data.
        Returns: True if valid, False if not
        """
        if self.wc_data.get("type") not in self.CRM_CALL_TYPE_MAP:
            return False
        reference_doctype, reference_name = self._get_reference()
        if not reference_doctype:
            return False
        return bool(self._en_api.get(ERPNextDocType(reference_doctype), reference_name))

    def _transform(self) -> dict:
        """Transforms the data from WeClapp to ERPNext.

        Returns:
            dict: Transformed data
        """
        reference_doctype, reference_name = self._get_reference()
        start_ts = self.wc_data.get("startDate") or self.wc_data.get("createdDate")
        return {
            "name"                  : f"CRM-{self.wc_data['id']}",
            "communication_type"    : "Communication",
            "communication_medium"  : "Phone",
            "sent_or_received"      : self.CRM_CALL_TYPE_MAP[self.wc_data.get("type")],
            "subject"               : (self.wc_data.get("subject") or "")[:140],
            "content"               : self.wc_data.get("description") or "",
            "communication_date"    : ERPNextHelper.get_date_from_weclapp_ts(start_ts) if start_ts else None,
            "reference_doctype"     : reference_doctype,
            "reference_name"        : reference_name,
        }
