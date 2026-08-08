"""One-time (but idempotent) ERPNext master-data setup that must run before the actual
migration: custom fields (Zusatzfelder), item groups (Artikelgruppen), warehouses and
manufacturers. Safe to re-run - existing records are skipped, not duplicated.
"""
import json
import config
import weclapp as wc
from erpnext import ERPNextAPI, ERPNextDocType, ERPNextHelper

# NOTE: Suppliers deliberately have no custom fields - none of the 389 cached suppliers carries
# a single custom attribute value. Contact is included per specification (vehicle/eBay/opt-out
# fields); the same party attributes stay on Customer too, since the actual values live on the
# WeClapp party (customer) records.
WC_ENTITY_TO_EN_DOCTYPE = {
    "article": [ERPNextDocType.ITEM.value],
    "party": [ERPNextDocType.CUSTOMER.value, ERPNextDocType.CONTACT.value],
    "salesInvoice": [ERPNextDocType.SALES_INVOICE.value],
    "salesOrder": [ERPNextDocType.SALES_ORDER.value],
    "shipment": [ERPNextDocType.DELIVERY_NOTE.value],
}

ATTR_TYPE_TO_FIELDTYPE = {
    "BOOLEAN": "Check",
    "DECIMAL": "Float",
    "STRING": "Data",
    "LARGE_TEXT": "Small Text",
    "URL": "Data",
    "LIST": "Data",
    "MULTISELECT_LIST": "Small Text",
}

# Manually curated layout of the Item "Freifelder" tab (as modeled by hand in Customize Form),
# reproduced 1:1 here so a fresh setup run creates the exact same tab/section/column structure
# instead of dumping every custom field flat into one section. Each entry is
# (section_fieldname, section_label, left_column_attribute_keys, right_column_attribute_keys) -
# attribute keys are raw WeClapp attributeKeys (see ERPNextHelper.get_custom_fieldname).
# A section with an empty right column gets no Column Break (single-column section).
ITEM_FREIFELDER_LAYOUT = [
    ("custom_originalnummern_und_typenzuordnung", "Originalnummern und Typenzuordnung",
        ["geeignet_fuer", "benoetigte_stueckzahl_je_fahrzeug", "geeignet_fuer_atyp"],
        ["citroenoriginalnummer", "nummer_mcda", "nummer_mcc"]),
    ("custom_shopkontrollfelder", "Shopkontrollfelder",
        ["4437i2eajrdks11ju7", "metatitel", "metabeschreibung", "metakeywords",
         "abverkauf", "preisbindung", "versandart"],
        []),
    ("custom_verlag", "Verlag",
        ["buchseitenanzahl", "isbnnr", "verlag"],
        ["buchautor", "buchsprache", "buchgroesse"]),
    ("custom_kfzisolierung", "KFZ-Isolierung",
        ["verkaufseinheit", "besondere_eigenschaften", "material", "grundpreis_masseinheit",
         "farbe", "rohdichte", "grundeinheit"],
        ["etikettentitel", "selbstklebend", "shoplink", "materialstaerke", "abmessungen", "verwendung"]),
    ("custom_kaffeemaschine", "Kaffeemaschine",
        ["melittaoriginalnummer", "geeignetfuerkaffeemaschine", "zustandkaffeemaschine"],
        []),
    ("custom_dezimalzahlen_shopware_einstellungen", "Dezimalzahlen Shopware Einstellungen",
        ["neon_unitarticles_minvalue1", "neon_unitarticles_stepsize1", "neon_unitarticles_unitlabel1",
         "neon_unitarticles_basepricevalue"],
        ["neon_unitarticles_description1", "neon_unitarticles_maxvalue1", "neon_unitarticles_defaultvalue1",
         "neon_unitarticles_isunitarticle", "neon_unitarticles_mergeuservalues"]),
]


def _resolve_custom_fieldtype(attribute_key: str, attr_def: dict) -> tuple[str, str]:
    """Resolves the ERPNext fieldtype/options for a WeClapp custom attribute, applying the same
    rules setup_custom_fields() and setup_multiselect_fields() use (type overrides, LIST ->
    Select with the WeClapp selectable values, MULTISELECT_LIST -> Table MultiSelect for
    attributes in config.EN_MULTISELECT_TABLE_FIELDS).

    Returns:
        tuple[str, str]: (fieldtype, options) - options is None if not applicable
    """
    fieldtype = config.EN_CUSTOM_ATTRIBUTE_TYPE_OVERRIDES.get(attribute_key) or \
        ATTR_TYPE_TO_FIELDTYPE.get(attr_def.get("attributeType"), "Data")
    options = None

    if attr_def.get("attributeType") == "LIST":
        fieldtype = "Select"
        values = [sv.get("value") for sv in attr_def.get("selectableValues", []) or [] if sv.get("value")]
        options = "\n".join([""] + values)

    if attribute_key in config.EN_MULTISELECT_TABLE_FIELDS:
        fieldtype = "Table MultiSelect"
        options = f"{config.EN_MULTISELECT_TABLE_FIELDS[attribute_key]} Eintrag"

    return fieldtype, options


def setup_custom_fields(en_api: ERPNextAPI):
    """Creates the ERPNext Custom Fields (Zusatzfelder) needed by _map_custom_attributes().
    Frappe silently drops unknown fields on insert, so these must exist before any migration
    that carries custom attributes runs (Article/Customer/Supplier/SalesOrder/SalesInvoice).
    Every target doctype first gets a "Freifelder" section break, so all custom fields
    appear together in a clearly named form section - except Item, which gets the manually
    modeled tab/section/column layout from setup_item_freifelder_tab() instead.
    Attributes in config.EN_CUSTOM_ATTRIBUTE_EXCLUDE are skipped entirely; attributes in
    config.EN_MULTISELECT_TABLE_FIELDS are created by setup_multiselect_fields() instead.
    """
    definitions = json.load(open(f"{config.WC_CACHE_BASE}customAttributeDefinition.json"))["data"]

    created, skipped, failed = 0, 0, 0

    # Section break per target doctype so all custom fields live under a "Freifelder" heading
    # (Item is excluded - see setup_item_freifelder_tab())
    all_doctypes = sorted({dt for dts in WC_ENTITY_TO_EN_DOCTYPE.values() for dt in dts} - {ERPNextDocType.ITEM.value})
    for doctype in all_doctypes:
        try:
            en_api.create(ERPNextDocType.CUSTOM_FIELD, {
                "dt": doctype,
                "fieldname": "freifelder_sektion",
                "label": "Freifelder",
                "fieldtype": "Section Break",
                "collapsible": 1,
            })
            created += 1
        except Exception as e:
            if "already exists" in str(e) or "DuplicateEntryError" in str(e):
                skipped += 1
            else:
                print(f"FAILED Section Break {doctype}.freifelder_sektion: {type(e).__name__}: {e}")
                failed += 1

    for d in definitions.values():
        attribute_key = d.get("attributeKey")
        if attribute_key in config.EN_CUSTOM_ATTRIBUTE_EXCLUDE or \
           attribute_key in config.EN_MULTISELECT_TABLE_FIELDS:
            continue
        fieldtype = config.EN_CUSTOM_ATTRIBUTE_TYPE_OVERRIDES.get(attribute_key) or \
            ATTR_TYPE_TO_FIELDTYPE.get(d.get("attributeType"), "Data")
        fieldname = ERPNextHelper.get_custom_fieldname(attribute_key)
        label = (d.get("label") or attribute_key)[:140]

        # WeClapp LIST attributes become real single-select dropdowns with the WeClapp values
        options = None
        if d.get("attributeType") == "LIST":
            fieldtype = "Select"
            values = [sv.get("value") for sv in d.get("selectableValues", []) or [] if sv.get("value")]
            options = "\n".join([""] + values)     # leading blank = "no selection" option

        for entity in d.get("entities", []) or []:
            for doctype in WC_ENTITY_TO_EN_DOCTYPE.get(entity, []):
                # Item fields are placed by setup_item_freifelder_tab() instead, at their
                # modeled position inside the Freifelder tab
                if doctype == ERPNextDocType.ITEM.value:
                    continue
                try:
                    field = {
                        "dt": doctype,
                        "fieldname": fieldname,
                        "label": label,
                        "fieldtype": fieldtype,
                        "allow_on_submit": 1 if doctype in ("Sales Invoice", "Sales Order") else 0,
                    }
                    if options is not None:
                        field["options"] = options
                    en_api.create(ERPNextDocType.CUSTOM_FIELD, field)
                    created += 1
                except Exception as e:
                    if "already exists" in str(e) or "DuplicateEntryError" in str(e):
                        skipped += 1
                    else:
                        print(f"FAILED Custom Field {doctype}.{fieldname}: {type(e).__name__}: {e}")
                        failed += 1
    print(f"--- Custom Fields: {created} created, {skipped} skipped (exists), {failed} failed ---")


def setup_multiselect_fields(en_api: ERPNextAPI):
    """Creates real multi-select dropdowns (fieldtype "Table MultiSelect") for the WeClapp
    MULTISELECT_LIST attributes configured in config.EN_MULTISELECT_TABLE_FIELDS.
    Per attribute this needs: an option DocType (filled with the WeClapp selectableValues),
    a child table DocType with a single Link field "wert", and the Custom Field itself.
    """
    definitions = json.load(open(f"{config.WC_CACHE_BASE}customAttributeDefinition.json"))["data"]
    defs_by_key = {d.get("attributeKey"): d for d in definitions.values()}

    created, skipped, failed = 0, 0, 0

    def _create(doctype, payload, what):
        nonlocal created, skipped, failed
        try:
            en_api.create(doctype, payload)
            created += 1
        except Exception as e:
            if "already exists" in str(e) or "DuplicateEntryError" in str(e):
                skipped += 1
            else:
                print(f"FAILED {what}: {type(e).__name__}: {e}")
                failed += 1

    for attribute_key, option_doctype in config.EN_MULTISELECT_TABLE_FIELDS.items():
        d = defs_by_key.get(attribute_key)
        if not d:
            print(f"FAILED multiselect field {attribute_key}: no WeClapp definition found")
            failed += 1
            continue
        child_doctype = f"{option_doctype} Eintrag"
        label = (d.get("label") or attribute_key)[:140]

        # 1. Option DocType (holds the selectable values as its records)
        _create("DocType", {
            "name": option_doctype,
            "module": "Custom",
            "custom": 1,
            "naming_rule": "By fieldname",
            "autoname": "field:wert",
            "fields": [{"fieldname": "wert", "fieldtype": "Data", "label": "Wert", "reqd": 1, "unique": 1}],
            "permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1}],
        }, f"DocType {option_doctype}")

        # 2. Child table DocType with a single Link field (required by Table MultiSelect)
        _create("DocType", {
            "name": child_doctype,
            "module": "Custom",
            "custom": 1,
            "istable": 1,
            "fields": [{"fieldname": "wert", "fieldtype": "Link", "options": option_doctype,
                        "label": "Wert", "in_list_view": 1, "reqd": 1}],
        }, f"DocType {child_doctype}")

        # 3. Option records from the WeClapp selectableValues
        for sv in d.get("selectableValues", []) or []:
            value = sv.get("value")
            if value:
                _create(option_doctype, {"wert": value}, f"{option_doctype} '{value}'")

        # 4. The Table MultiSelect Custom Field on every target doctype of the attribute
        # (Item is excluded - setup_item_freifelder_tab() places it at its modeled position)
        fieldname = ERPNextHelper.get_custom_fieldname(attribute_key)
        for entity in d.get("entities", []) or []:
            for doctype in WC_ENTITY_TO_EN_DOCTYPE.get(entity, []):
                if doctype == ERPNextDocType.ITEM.value:
                    continue
                _create(ERPNextDocType.CUSTOM_FIELD, {
                    "dt": doctype,
                    "fieldname": fieldname,
                    "label": label,
                    "fieldtype": "Table MultiSelect",
                    "options": child_doctype,
                    "allow_on_submit": 1 if doctype in ("Sales Invoice", "Sales Order") else 0,
                }, f"Custom Field {doctype}.{fieldname}")

    print(f"--- Multiselect Fields: {created} created, {skipped} skipped (exists), {failed} failed ---")


def setup_item_freifelder_tab(en_api: ERPNextAPI):
    """Creates the Item "Freifelder" tab exactly as manually modeled in Customize Form:
    a dedicated Tab Break (instead of Item sharing the generic collapsible section other
    doctypes get) holding the sections/columns/field order defined in ITEM_FREIFELDER_LAYOUT.
    Must run after setup_multiselect_fields(), since Table MultiSelect fields here reference
    the option child DocTypes created there.
    """
    definitions = json.load(open(f"{config.WC_CACHE_BASE}customAttributeDefinition.json"))["data"]
    defs_by_key = {d.get("attributeKey"): d for d in definitions.values()}

    created, skipped, failed = 0, 0, 0

    def _create(payload, what):
        nonlocal created, skipped, failed
        try:
            en_api.create(ERPNextDocType.CUSTOM_FIELD, payload)
            created += 1
        except Exception as e:
            if "already exists" in str(e) or "DuplicateEntryError" in str(e):
                skipped += 1
            else:
                print(f"FAILED {what}: {type(e).__name__}: {e}")
                failed += 1

    # Tab Break right after the standard "description" field
    _create({
        "dt": "Item",
        "fieldname": "custom_freifelder",
        "label": "Freifelder",
        "fieldtype": "Tab Break",
        "insert_after": "description",
    }, "Tab Break Item.custom_freifelder")

    last_fieldname = "custom_freifelder"

    def _add_field(attribute_key: str) -> None:
        nonlocal last_fieldname, failed
        d = defs_by_key.get(attribute_key)
        if not d:
            print(f"FAILED Item Freifelder field {attribute_key}: no WeClapp definition found")
            failed += 1
            return
        fieldtype, options = _resolve_custom_fieldtype(attribute_key, d)
        fieldname = ERPNextHelper.get_custom_fieldname(attribute_key)
        field = {
            "dt": "Item",
            "fieldname": fieldname,
            "label": (d.get("label") or attribute_key)[:140],
            "fieldtype": fieldtype,
            "insert_after": last_fieldname,
        }
        if options is not None:
            field["options"] = options
        _create(field, f"Custom Field Item.{fieldname}")
        last_fieldname = fieldname

    for section_fieldname, section_label, left_keys, right_keys in ITEM_FREIFELDER_LAYOUT:
        _create({
            "dt": "Item",
            "fieldname": section_fieldname,
            "label": section_label,
            "fieldtype": "Section Break",
            "insert_after": last_fieldname,
        }, f"Section Break Item.{section_fieldname}")
        last_fieldname = section_fieldname

        for key in left_keys:
            _add_field(key)

        if right_keys:
            column_break_fieldname = f"{section_fieldname}_column_break"
            _create({
                "dt": "Item",
                "fieldname": column_break_fieldname,
                "fieldtype": "Column Break",
                "insert_after": last_fieldname,
            }, f"Column Break Item.{column_break_fieldname}")
            last_fieldname = column_break_fieldname

            for key in right_keys:
                _add_field(key)

    print(f"--- Item Freifelder Tab: {created} created, {skipped} skipped (exists), {failed} failed ---")


def setup_link_fields(en_api: ERPNextAPI):
    """Creates the document-chain link fields (Belegkette): Angebot -> Auftrag -> Rechnung and
    Auftrag -> Bestellung -> Eingangsrechnung. Plain Link fields instead of ERPNext's native
    item-level references, because the native coupling enforces qty/billing consistency
    that migrated WeClapp documents can't generally satisfy.
    """
    link_fields = [
        # Vorwärts (werden direkt beim Import gesetzt, siehe _transform der Migrationen)
        ("Sales Order",      "wc_angebot",         "Angebot",          "Quotation"),
        ("Sales Invoice",    "wc_auftrag",         "Auftrag",          "Sales Order"),
        ("Purchase Order",   "wc_auftrag",         "Auftrag",          "Sales Order"),
        ("Purchase Invoice", "wc_bestellung",      "Bestellung",       "Purchase Order"),
        ("Delivery Note",    "wc_auftrag",         "Auftrag",          "Sales Order"),
        # Rückwärts (werden in der Schlussphase gesetzt, siehe main.apply_document_links)
        ("Quotation",        "wc_auftrag",         "Auftrag",          "Sales Order"),
        ("Sales Order",      "wc_rechnung",        "Rechnung",         "Sales Invoice"),
        ("Sales Order",      "wc_bestellung",      "Bestellung",       "Purchase Order"),
        ("Purchase Order",   "wc_eingangsrechnung", "Eingangsrechnung", "Purchase Invoice"),
    ]
    created, skipped, failed = 0, 0, 0

    # Own form section so the links don't end up inside the "Freifelder" section
    for doctype in sorted({dt for dt, *_ in link_fields}):
        try:
            en_api.create(ERPNextDocType.CUSTOM_FIELD, {
                "dt": doctype,
                "fieldname": "belegkette_sektion",
                "label": "Belegkette (WeClapp)",
                "fieldtype": "Section Break",
                # deliberately NOT collapsible - a collapsed section at the form end is
                # invisible enough that the links look missing
                "collapsible": 0,
            })
            created += 1
        except Exception as e:
            if "already exists" in str(e) or "DuplicateEntryError" in str(e):
                skipped += 1
            else:
                print(f"FAILED Section Break {doctype}.belegkette_sektion: {type(e).__name__}: {e}")
                failed += 1

    for doctype, fieldname, label, target in link_fields:
        try:
            en_api.create(ERPNextDocType.CUSTOM_FIELD, {
                "dt": doctype,
                "fieldname": fieldname,
                "label": label,
                "fieldtype": "Link",
                "options": target,
                "allow_on_submit": 1,
            })
            created += 1
        except Exception as e:
            if "already exists" in str(e) or "DuplicateEntryError" in str(e):
                skipped += 1
            else:
                print(f"FAILED Link Field {doctype}.{fieldname}: {type(e).__name__}: {e}")
                failed += 1
    print(f"--- Link Fields (Belegkette): {created} created, {skipped} skipped (exists), {failed} failed ---")


def setup_shipment_tracking_fields(en_api: ERPNextAPI):
    """Creates the carrier tracking fields on Delivery Note (packageTrackingNumber/
    shippingCarrierName from WeClapp shipment - plain top-level fields, not WeClapp custom
    attributes, so they're not covered by setup_custom_fields()/_map_custom_attributes()).
    """
    created, skipped, failed = 0, 0, 0

    def _create(payload, what):
        nonlocal created, skipped, failed
        try:
            en_api.create(ERPNextDocType.CUSTOM_FIELD, payload)
            created += 1
        except Exception as e:
            if "already exists" in str(e) or "DuplicateEntryError" in str(e):
                skipped += 1
            else:
                print(f"FAILED {what}: {type(e).__name__}: {e}")
                failed += 1

    _create({
        "dt": "Delivery Note",
        "fieldname": "versand_sektion",
        "label": "Versand (WeClapp)",
        "fieldtype": "Section Break",
        "collapsible": 0,
    }, "Section Break Delivery Note.versand_sektion")
    _create({
        "dt": "Delivery Note",
        "fieldname": "wc_tracking_nummer",
        "label": "Tracking-Nummer",
        "fieldtype": "Data",
    }, "Custom Field Delivery Note.wc_tracking_nummer")
    _create({
        "dt": "Delivery Note",
        "fieldname": "wc_versanddienstleister",
        "label": "Versanddienstleister",
        "fieldtype": "Data",
    }, "Custom Field Delivery Note.wc_versanddienstleister")

    print(f"--- Shipment Tracking Fields: {created} created, {skipped} skipped (exists), {failed} failed ---")


def setup_internal_note_fields(en_api: ERPNextAPI):
    """Creates the "wc_interne_notiz" Custom Field (WeClapp's internal free-text/note fields -
    recordFreeText/recordOpening/note on transactional documents, "description" on
    Customer/Supplier - see BaseMigration._map_wc_notes()) on every doctype that carries them.
    """
    doctypes = ["Sales Order", "Sales Invoice", "Purchase Order", "Purchase Invoice",
                "Quotation", "Delivery Note", "Customer", "Supplier"]
    created, skipped, failed = 0, 0, 0

    def _create(payload, what):
        nonlocal created, skipped, failed
        try:
            en_api.create(ERPNextDocType.CUSTOM_FIELD, payload)
            created += 1
        except Exception as e:
            if "already exists" in str(e) or "DuplicateEntryError" in str(e):
                skipped += 1
            else:
                print(f"FAILED {what}: {type(e).__name__}: {e}")
                failed += 1

    for doctype in doctypes:
        _create({
            "dt": doctype,
            "fieldname": "notizen_sektion",
            "label": "Interne Notizen (WeClapp)",
            "fieldtype": "Section Break",
            "collapsible": 1,
        }, f"Section Break {doctype}.notizen_sektion")
        _create({
            "dt": doctype,
            "fieldname": "wc_interne_notiz",
            "label": "Interne Notiz (WeClapp)",
            # Text Editor, not Small Text: WeClapp's recordFreeText/description are rich text
            # (always contain HTML markup in the cached data) - Small Text would show raw tags
            "fieldtype": "Text Editor",
        }, f"Custom Field {doctype}.wc_interne_notiz")

    print(f"--- Internal Note Fields: {created} created, {skipped} skipped (exists), {failed} failed ---")


def setup_item_groups(en_api: ERPNextAPI):
    """Creates the ERPNext Item Group hierarchy from WeClapp's articleCategory cache."""
    categories = json.load(open(f"{config.WC_CACHE_BASE}articleCategory.json"))["data"]
    categories = {v["id"]: v for v in categories.values()}
    parent_ids = {c.get("parentCategoryId") for c in categories.values() if c.get("parentCategoryId")}
    root = "All Item Groups"

    created, skipped, failed = 0, 0, 0
    creation_state = {}
    remaining = dict(categories)
    while remaining:
        progressed = False
        for cid, cat in list(remaining.items()):
            parent_id = cat.get("parentCategoryId")
            if parent_id and parent_id not in creation_state:
                continue
            parent_name = categories.get(parent_id, {}).get("name") if parent_id else root
            try:
                en_api.create(ERPNextDocType.ITEM_GROUP, {
                    "item_group_name": cat["name"],
                    "parent_item_group": parent_name or root,
                    "is_group": 1 if cid in parent_ids else 0
                })
                created += 1
            except Exception as e:
                if "already exists" in str(e) or "DuplicateEntryError" in str(e):
                    skipped += 1
                else:
                    print(f"FAILED Item Group '{cat['name']}': {type(e).__name__}: {e}")
                    failed += 1
            creation_state[cid] = True
            del remaining[cid]
            progressed = True
        if not progressed:
            # Unresolved parents (shouldn't happen) - fall back to root
            for cid, cat in remaining.items():
                try:
                    en_api.create(ERPNextDocType.ITEM_GROUP, {
                        "item_group_name": cat["name"],
                        "parent_item_group": root,
                        "is_group": 1 if cid in parent_ids else 0
                    })
                    created += 1
                except Exception as e:
                    if "already exists" in str(e) or "DuplicateEntryError" in str(e):
                        skipped += 1
                    else:
                        print(f"FAILED Item Group '{cat['name']}': {type(e).__name__}: {e}")
                        failed += 1
            break
    print(f"--- Item Groups: {created} created, {skipped} skipped (exists), {failed} failed ---")


def setup_warehouses(en_api: ERPNextAPI):
    """Creates the ERPNext Warehouse tree from WeClapp's warehouse/storageLocation/storagePlace
    caches, 1:1 (Warehouse -> Storage Location -> Storage Place, each as an ERPNext Warehouse,
    the first two as groups and Storage Place as the postable leaf). Used as the target for the
    full historical warehouseStockMovement/shipment replay (see stock_entry_migration.py and
    delivery_note_migration.py); the whole tree is disabled again afterwards by
    main.disable_legacy_warehouses(), once the replay has posted against it - disabling only
    hides it from pickers for new transactions, the stock ledger history stays intact.
    Names are deterministic (see ERPNextHelper.get_wc_warehouse_name) so the migrations can
    reference them without needing a persisted id->name mapping from this run.
    """
    warehouses = json.load(open(f"{config.WC_CACHE_BASE}warehouse.json"))["data"]
    warehouses = {v["id"]: v for v in warehouses.values()}
    storage_locations = json.load(open(f"{config.WC_CACHE_BASE}storageLocation.json"))["data"]
    storage_locations = {v["id"]: v for v in storage_locations.values()}
    storage_places = json.load(open(f"{config.WC_CACHE_BASE}storagePlace.json"))["data"]
    storage_places = {v["id"]: v for v in storage_places.values()}

    created, skipped, failed = 0, 0, 0

    def _full_name(base_name: str) -> str:
        """ERPNext appends " - {company_abbr}" to the warehouse_name on creation - this
        predicts that final name so it can be used as a parent_warehouse/warehouse reference."""
        return f"{base_name} - {config.EN_COMPANY_ABBR}"

    def _create(warehouse_name: str, parent_name: str, is_group: int, what: str) -> None:
        nonlocal created, skipped, failed
        try:
            en_api.create(ERPNextDocType.WAREHOUSE, {
                "warehouse_name": warehouse_name,
                "company": config.EN_COMPANY,
                "parent_warehouse": parent_name,
                "is_group": is_group,
            })
            created += 1
        except Exception as e:
            if "already exists" in str(e) or "DuplicateEntryError" in str(e):
                skipped += 1
            else:
                print(f"FAILED Warehouse '{what}': {type(e).__name__}: {e}")
                failed += 1

    # Level 1: WeClapp Warehouse -> ERPNext Warehouse group (top of tree)
    for w in warehouses.values():
        name = ERPNextHelper.get_wc_warehouse_name(w["name"], w["id"])
        _create(name, None, 1, name)

    # Level 2: WeClapp Storage Location -> ERPNext Warehouse group, child of its Warehouse
    for loc in storage_locations.values():
        name = ERPNextHelper.get_wc_warehouse_name(loc["name"], loc["id"])
        parent_wc = warehouses.get(loc.get("warehouseId"))
        if not parent_wc:
            print(f"FAILED Storage Location '{name}': no parent warehouse {loc.get('warehouseId')} found")
            failed += 1
            continue
        parent_name = _full_name(ERPNextHelper.get_wc_warehouse_name(parent_wc["name"], parent_wc["id"]))
        _create(name, parent_name, 1, name)

    # Level 3: WeClapp Storage Place -> ERPNext Warehouse leaf (postable), child of its
    # Storage Location, or directly of its Warehouse if storageLocationId is missing
    for place in storage_places.values():
        name = ERPNextHelper.get_wc_warehouse_name(place["name"], place["id"])
        parent_loc = storage_locations.get(place.get("storageLocationId"))
        if parent_loc:
            parent_name = _full_name(ERPNextHelper.get_wc_warehouse_name(parent_loc["name"], parent_loc["id"]))
        else:
            parent_wc = warehouses.get(place.get("warehouseId"))
            if not parent_wc:
                print(f"FAILED Storage Place '{name}': no parent location/warehouse found")
                failed += 1
                continue
            parent_name = _full_name(ERPNextHelper.get_wc_warehouse_name(parent_wc["name"], parent_wc["id"]))
        _create(name, parent_name, 0, name)

    print(f"--- Warehouses: {created} created, {skipped} skipped (exists), {failed} failed ---")


def get_wc_warehouse_full_names() -> list[str]:
    """Returns the full ERPNext Warehouse names (incl. the company-abbr suffix ERPNext appends
    on creation) for the entire WeClapp warehouse/storageLocation/storagePlace tree created by
    setup_warehouses(). Used by main.disable_legacy_warehouses() to deactivate the whole
    "Lager_old" tree again once the historical Stock Entry/Delivery Note replay has posted
    against it - names are re-derived from the same cache data rather than persisted, consistent
    with ERPNextHelper.get_wc_warehouse_name()'s no-shared-state design.
    """
    warehouses = json.load(open(f"{config.WC_CACHE_BASE}warehouse.json"))["data"]
    storage_locations = json.load(open(f"{config.WC_CACHE_BASE}storageLocation.json"))["data"]
    storage_places = json.load(open(f"{config.WC_CACHE_BASE}storagePlace.json"))["data"]

    names = []
    for raw in (warehouses, storage_locations, storage_places):
        for v in raw.values():
            base_name = ERPNextHelper.get_wc_warehouse_name(v["name"], v["id"])
            names.append(f"{base_name} - {config.EN_COMPANY_ABBR}")
    return names


def setup_bank_accounts(en_api: ERPNextAPI):
    """Creates WeClapp's real bank/loan/credit-card/cash accounts (bankAccount.json,
    cashAccount.json) as individual ERPNext Accounts, and the receivable write-off account used
    for WeClapp payments that turn out to have no real bank/cash movement behind them (see
    payment_entry_migration.py). Portable across WeClapp accounts: the bank/loan split is
    inferred from the SKR03 account-number convention (numbers starting with "0" are loan/credit
    accounts, not a hardcoded list of specific FranceTec accounts) - see
    ERPNextHelper.get_wc_account_name() for the two accounts (1200, 1000) that already exist in
    ERPNext under a generic label and are intentionally left as-is rather than renamed.
    """
    wc_api = wc.WcCacheApi(config.WC_CACHE_BASE)
    wc_api.open()
    ledger_accounts = wc_api.get_ledger_accounts()

    created, skipped, failed = 0, 0, 0

    def _create_payment_account(ledger: dict):
        nonlocal created, skipped, failed
        number = ledger.get("accountNumber")
        if not number:
            print(f"FAILED Account '{ledger.get('description')}': ledger account {ledger.get('id')} has no accountNumber")
            failed += 1
            return
        description = ledger.get("description") or number
        is_loan = number.startswith("0")
        payload = {
            "account_name": ERPNextHelper.get_wc_account_label(number, description),
            "account_number": number,
            "company": config.EN_COMPANY,
            "parent_account": config.EN_LOAN_ACCOUNT_GROUP if is_loan else config.EN_BANK_ACCOUNT_GROUP,
        }
        if not is_loan:
            payload["account_type"] = "Bank"
        try:
            en_api.create(ERPNextDocType.ACCOUNT, payload)
            created += 1
        except Exception as e:
            if "already exists" in str(e) or "DuplicateEntryError" in str(e):
                skipped += 1
            else:
                print(f"FAILED Account {number} - {description}: {type(e).__name__}: {e}")
                failed += 1

    # Resolve via ledgerAccount.description (the WeClapp chart-of-accounts label, e.g.
    # "Kreditkarte Barclays") rather than bankAccount.creditInstitute/cashAccount.description
    # (the plain institution name) - the latter is ambiguous where multiple WeClapp payment
    # accounts share the same institution (e.g. two "Barclays Bank Hamburg" accounts, 0656/0657,
    # a financing line and a credit card - ledgerAccount.description tells them apart).
    for v in wc_api.get_bank_accounts().values():
        ledger = ledger_accounts.get(v["accountId"])
        if not ledger:
            print(f"FAILED bank account '{v.get('creditInstitute')}': no ledger account found for accountId {v['accountId']}")
            failed += 1
            continue
        _create_payment_account(ledger)

    for v in wc_api.get_cash_accounts().values():
        ledger = ledger_accounts.get(v["accountId"])
        if not ledger:
            print(f"FAILED cash account '{v.get('description')}': no ledger account found for accountId {v['accountId']}")
            failed += 1
            continue
        _create_payment_account(ledger)

    # Receivable/payable write-off account (see payment_entry_migration.py)
    try:
        en_api.create(ERPNextDocType.ACCOUNT, {
            "account_name": "Forderungsverluste",
            "account_number": "2400",
            "company": config.EN_COMPANY,
            "parent_account": config.EN_RECEIVABLE_WRITEOFF_ACCOUNT_GROUP,
            "account_type": config.EN_RECEIVABLE_WRITEOFF_ACCOUNT_TYPE,
        })
        created += 1
    except Exception as e:
        if "already exists" in str(e) or "DuplicateEntryError" in str(e):
            skipped += 1
        else:
            print(f"FAILED Account 2400 - Forderungsverluste: {type(e).__name__}: {e}")
            failed += 1

    print(f"--- Bank/Loan/Write-off Accounts: {created} created, {skipped} skipped (exists), {failed} failed ---")


def setup_manufacturers(en_api: ERPNextAPI):
    """Creates the ERPNext Manufacturer master records referenced by article.manufacturerName."""
    articles = json.load(open(f"{config.WC_CACHE_BASE}article.json"))["data"]
    names = sorted(set(v.get("manufacturerName") for v in articles.values() if v.get("manufacturerName")))

    created, skipped, failed = 0, 0, 0
    for name in names:
        try:
            en_api.create(ERPNextDocType.MANUFACTURER, {"short_name": name})
            created += 1
        except Exception as e:
            if "already exists" in str(e) or "DuplicateEntryError" in str(e):
                skipped += 1
            else:
                print(f"FAILED Manufacturer '{name}': {type(e).__name__}: {e}")
                failed += 1
    print(f"--- Manufacturers: {created} created, {skipped} skipped (exists), {failed} failed ---")


def setup_free_text_item(en_api: ERPNextAPI):
    """Creates the placeholder item for free-text document lines.
    Sales/Purchase Orders and Quotations require an item_code on every line, but WeClapp
    allows free-text positions without an article - those lines reference this item and
    carry their actual text in item_name/description.
    """
    try:
        en_api.create(ERPNextDocType.ITEM, {
            "item_code": config.EN_FREE_TEXT_ITEM,
            "item_name": "Freitext-Position",
            "item_group": config.EN_DEFAULT_ITEM_GROUP,
            "description": "Platzhalter für Freitext-Positionen aus WeClapp (Positionen ohne Artikel)",
            "stock_uom": config.EN_DEFAULT_UOM,
            "is_stock_item": 0,
        })
        print(f"--- Free-text item {config.EN_FREE_TEXT_ITEM}: created ---")
    except Exception as e:
        if "already exists" in str(e) or "DuplicateEntryError" in str(e):
            print(f"--- Free-text item {config.EN_FREE_TEXT_ITEM}: exists ---")
        else:
            print(f"FAILED free-text item {config.EN_FREE_TEXT_ITEM}: {type(e).__name__}: {e}")


def setup_accounts(en_api: ERPNextAPI):
    """Creates the OSS VAT liability account for non-German EU sales VAT.
    The SKR03 chart in ERPNext only ships German Umsatzsteuer accounts - foreign EU VAT
    amounts from WeClapp (AT/IT/NL/...) are booked collectively to this account so invoice
    totals stay exact (see InvoiceMigration.OSS_ACCOUNT).
    """
    try:
        en_api.create(ERPNextDocType.ACCOUNT, {
            "account_name": "Umsatzsteuer OSS (EU-Ausland)",
            "account_number": "1767",
            "parent_account": "Umsatzsteuer - FT",
            "account_type": "Tax",
            "root_type": "Liability",
            "company": "FranceTec",
        })
        print("--- Account 1767 - Umsatzsteuer OSS (EU-Ausland) - FT: created ---")
    except Exception as e:
        if "already exists" in str(e) or "DuplicateEntryError" in str(e):
            print("--- Account 1767 - Umsatzsteuer OSS (EU-Ausland) - FT: exists ---")
        else:
            print(f"FAILED Account 1767 - Umsatzsteuer OSS: {type(e).__name__}: {e}")


def setup_naming(en_api: ERPNextAPI):
    """Switches document naming to "Prompt" for all doctypes the migration passes an explicit
    "name" for, so ERPNext keeps the original WeClapp numbers as document IDs (unambiguous
    mapping between the systems). Without this, ERPNext silently ignores the passed name and
    assigns its own naming-series number instead.
    """
    doctypes = [
        ERPNextDocType.CUSTOMER.value,
        ERPNextDocType.SUPPLIER.value,
        ERPNextDocType.SALES_INVOICE.value,
        ERPNextDocType.SALES_ORDER.value,
        ERPNextDocType.PURCHASE_INVOICE.value,
        ERPNextDocType.PURCHASE_ORDER.value,
        ERPNextDocType.QUOTATION.value,
        ERPNextDocType.STOCK_ENTRY.value,
        ERPNextDocType.DELIVERY_NOTE.value,
        ERPNextDocType.PAYMENT_ENTRY.value,
        ERPNextDocType.JOURNAL_ENTRY.value,
    ]
    created, skipped, failed = 0, 0, 0
    for doctype in doctypes:
        try:
            en_api.create(ERPNextDocType.PROPERTY_SETTER, {
                "doctype_or_field": "DocType",
                "doc_type": doctype,
                "property": "autoname",
                "property_type": "Data",
                "value": "Prompt",
            })
            created += 1
        except Exception as e:
            if "already exists" in str(e) or "DuplicateEntryError" in str(e):
                skipped += 1
            else:
                print(f"FAILED Property Setter (autoname=Prompt) for {doctype}: {type(e).__name__}: {e}")
                failed += 1
    print(f"--- Naming (autoname=Prompt): {created} created, {skipped} skipped (exists), {failed} failed ---")


def run_setup():
    """Runs all setup steps. Must run before the actual migration (main.py)."""
    en_api = ERPNextAPI(config.EN_API_KEY, config.EN_API_SECRET, config.EN_API_BASE)
    en_api.open()
    setup_custom_fields(en_api)
    setup_multiselect_fields(en_api)
    setup_item_freifelder_tab(en_api)
    setup_link_fields(en_api)
    setup_shipment_tracking_fields(en_api)
    setup_internal_note_fields(en_api)
    setup_item_groups(en_api)
    setup_warehouses(en_api)
    setup_bank_accounts(en_api)
    setup_manufacturers(en_api)
    setup_accounts(en_api)
    setup_free_text_item(en_api)
    setup_naming(en_api)
    en_api.close()


if __name__ == "__main__":
    run_setup()
