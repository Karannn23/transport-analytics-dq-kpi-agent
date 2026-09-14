from dotenv import load_dotenv
import os
from datetime import date, timedelta
from databricks import sql

load_dotenv()

conn = sql.connect(
    server_hostname=os.getenv('DATABRICKS_SERVER_HOSTNAME'),
    http_path=os.getenv('DATABRICKS_HTTP_PATH'),
    access_token=os.getenv('DATABRICKS_ACCESS_TOKEN')
)
cursor = conn.cursor()

# Fetch all order_shipment rows not yet in shipment, joined to order for dates/status
cursor.execute("""
    SELECT os.shipment_gid, os.quantity_kg, os.otm_deleted, os.lake_status, os.dq_flag,
           o.order_date, o.order_status
    FROM workspace.otm.order_shipment os
    LEFT JOIN workspace.otm.order o ON os.order_release_gid = o.order_release_gid
    WHERE os.shipment_gid NOT IN (SELECT shipment_gid FROM workspace.otm.shipment)
    ORDER BY os.shipment_gid
""")
source_rows = cursor.fetchall()
print(f"Found {len(source_rows)} shipment_gids to insert")

def derive_shipment_row(shipment_gid, quantity_kg, otm_deleted, lake_status, os_dq,
                        order_date, order_status):
    """
    Derive SHIPMENT row fields from order_shipment + order context.
    planned_pickup  = order_date + 1
    planned_delivery = order_date + 3
    """
    if order_date is None:
        order_date = date(2025, 6, 1)

    planned_pickup   = order_date + timedelta(days=1)
    planned_delivery = order_date + timedelta(days=3)

    # Derive status and actual dates based on DQ flags
    if os_dq == 'Zero Qty':
        status          = 'Planned'
        actual_dep      = None
        actual_arr      = None
        dq_flag         = 'Zero Weight'

    elif os_dq == 'Ghost Stale Delete' or (otm_deleted == 'YES' and lake_status == 'STALE'):
        status          = 'Planned'
        actual_dep      = None
        actual_arr      = None
        dq_flag         = 'Ghost - OS link deleted in source system'

    elif os_dq == 'Re-assigned':
        status          = 'Closed'
        actual_dep      = planned_pickup
        actual_arr      = planned_delivery
        dq_flag         = 'Re-assigned (active)'

    elif os_dq == 'Cancelled Order' or order_status == 'Cancelled':
        status          = 'Cancelled'
        actual_dep      = None
        actual_arr      = None
        dq_flag         = 'OK'

    elif os_dq in ('Split Order', 'Split Qty Mismatch'):
        status          = 'Closed'
        actual_dep      = planned_pickup
        actual_arr      = planned_delivery
        dq_flag         = 'Split Shipment'

    elif os_dq == 'OK' and order_status == 'Shipped':
        status          = 'Closed'
        actual_dep      = planned_pickup
        actual_arr      = planned_delivery
        dq_flag         = 'OK'

    elif order_status == 'Planned':
        status          = 'Planned'
        actual_dep      = None
        actual_arr      = None
        dq_flag         = 'OK'

    else:
        status          = 'Closed'
        actual_dep      = planned_pickup
        actual_arr      = planned_delivery
        dq_flag         = 'OK'

    def fmt(d):
        return f"'{d}'" if d else 'NULL'

    return (
        f"('{shipment_gid}','{planned_pickup}','{planned_delivery}',"
        f"{fmt(actual_dep)},{fmt(actual_arr)},"
        f"{quantity_kg},'{status}','{dq_flag}')"
    )

# Build VALUES
value_parts = []
for row in source_rows:
    value_parts.append(derive_shipment_row(
        shipment_gid=row[0],
        quantity_kg=row[1],
        otm_deleted=row[2],
        lake_status=row[3],
        os_dq=row[4],
        order_date=row[5],
        order_status=row[6]
    ))

insert_sql = (
    "INSERT INTO workspace.otm.SHIPMENT\n"
    "(shipment_gid, planned_pickup, planned_delivery, actual_departure, actual_arrival, weight_kg, status, dq_flag)\nVALUES\n"
    + ",\n".join(value_parts)
)

print(f"Inserting {len(value_parts)} rows into workspace.otm.SHIPMENT ...")
cursor.execute(insert_sql)
print("[SUCCESS] Rows inserted successfully")

# Total count
cursor.execute("SELECT COUNT(*) FROM workspace.otm.SHIPMENT")
print(f"\nTotal rows in workspace.otm.SHIPMENT: {cursor.fetchone()[0]}")

# DQ flag summary
cursor.execute("""
    SELECT dq_flag, COUNT(*) as cnt
    FROM workspace.otm.SHIPMENT
    GROUP BY dq_flag
    ORDER BY cnt DESC
""")
rows = cursor.fetchall()
print("\nDQ Flag Summary (all rows):")
print(f"  {'Flag':<40} {'Count':>5}")
print("  " + "-" * 48)
for r in rows:
    print(f"  {r[0]:<40} {r[1]:>5}")

# Status summary
cursor.execute("""
    SELECT status, COUNT(*) as cnt
    FROM workspace.otm.SHIPMENT
    GROUP BY status
    ORDER BY cnt DESC
""")
rows = cursor.fetchall()
print("\nStatus Summary:")
print(f"  {'Status':<20} {'Count':>5}")
print("  " + "-" * 27)
for r in rows:
    print(f"  {r[0]:<20} {r[1]:>5}")

cursor.close()
conn.close()
