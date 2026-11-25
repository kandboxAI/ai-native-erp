"""本模块拥有的列表展示排序声明，保留原有查询权限与数据范围。"""
from app.framework.db.list_sorting import DISPLAY_FIELDS, ListSortPolicy

LIST_FIELDS = DISPLAY_FIELDS | frozenset(
    """
    account_name account_no_masked action_code address_name adjusted_amount amount
    application_no asset_count asset_name asset_no asset_type_code available_count
    available_quantity balance_quantity batch_name batch_no bed_no bill_count bill_date bill_no
    binding_no building_name business_date category_code category_id category_name category_no
    chapter_name check_date check_no check_time cohort connection_name counted_quantity
    counterparty_name_snapshot custodian_name date deadline_at deduction_amount
    default_custodian_user_id default_department_id default_from_status_code
    default_supplier_name default_to_status_code department_name departure_date description
    difficulty_code direction_code due_date entered_count expected_count expected_return_date
    expiry_date field file_name file_size floor_no form from_at from_date from_warehouse
    from_warehouse_label grand_total handling_method_code handover_date handover_no incident_no
    incident_type_code inspection_date inventory_value is_active is_approval_required
    is_asset_managed is_builtin is_lot_controlled is_negative_allowed is_primary is_reversal
    item_name item_names item_no item_type_code lent_quantity line_no location_name location_no
    location_type_code lot_no lower_quantity major_name major_no management_mode max_quantity
    message min_quantity month occurred_at offboarding_no offering_no on_hand_quantity order_no
    order_type_name org_id org_name outstanding_amount paid_amount paid_at parent_id parent_name
    party_type_code pay_method_code payable_amount payment_no pending_count performance_base
    period_end period_label period_start plan_name plan_no point_name point_no
    position_allowance priority_code progress quantity radius record_no refund_no refunded_at
    registration_status_code remark repair_no report_no reserved_quantity result_code
    returned_quantity reviewed_count room_name room_no room_number row rule_name rule_no
    safety_stock scenario_key session_date session_name settlement_cycle_code
    settlement_method_code sheet sheet_no sort_no source_code source_type_code specification
    standard_name status_change status_code stock_alert_label stock_status_code submitted_count
    suggested_replenishment_quantity supplier_name supplier_no target_stock task_name task_no
    to_at to_date to_warehouse to_warehouse_label total_amount total_quantity transaction_no
    transferor_name_snapshot type_name type_no unallocated_amount unit_code unit_price
    updated_at uploaded_at upper_quantity urgency_code version_no warehouse_name warehouse_no
    location year
    """.split()
)

LIST_SORT_POLICIES = (
    ListSortPolicy('GET', '/api/inventory_product_category/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/inventory_product/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/inventory_warehouse/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/inventory_item/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/inventory_item/balance/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/inventory_stock_alert/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/inventory_item_warehouse_setting/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/inventory_movement/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/inventory_stock_order_type/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/inventory_stock_order/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/supplier_category/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/supplier/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/inventory_requisition/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/asset/ledger', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/asset/locations', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/asset-handovers', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/asset-handovers/mine', fields=LIST_FIELDS),
)
