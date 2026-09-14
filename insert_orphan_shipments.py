from dotenv import load_dotenv
import os
from databricks import sql

load_dotenv()

conn = sql.connect(
    server_hostname=os.getenv('DATABRICKS_SERVER_HOSTNAME'),
    http_path=os.getenv('DATABRICKS_HTTP_PATH'),
    access_token=os.getenv('DATABRICKS_ACCESS_TOKEN')
)
cursor = conn.cursor()

insert_sql = """
INSERT INTO workspace.otm.ORDER_SHIPMENT
(os_id, order_release_gid, shipment_gid, quantity_kg, pickup_loc_gid, delivery_loc_gid, otm_deleted, lake_status, dq_flag)
VALUES
('OS-X01','OTM.ORD-UNKNOWN-1','OTM.SHP-2025-020',500,'OTM.LOC-WHSE-01','OTM.LOC-DC-EAST','No','Active','Orphan - No ORDER'),
('OS-X02','OTM.ORD-UNKNOWN-2','OTM.SHP-2025-021',340,'OTM.LOC-WHSE-03','OTM.LOC-DC-SOUTH','No','Active','Orphan - No ORDER'),
('OS-X03','OTM.ORD-UNKNOWN-3','OTM.SHP-2025-022',780,'OTM.LOC-WHSE-02','OTM.LOC-DC-EAST','No','Active','Orphan - No ORDER')
"""

print("Inserting 3 new Orphan rows into workspace.otm.ORDER_SHIPMENT ...")
cursor.execute(insert_sql)
print("[SUCCESS] Rows inserted")

# Verify total and show the new orphan rows
cursor.execute("SELECT COUNT(*) FROM workspace.otm.ORDER_SHIPMENT")
print(f"\nTotal rows in workspace.otm.ORDER_SHIPMENT: {cursor.fetchone()[0]}")

cursor.execute("""
    SELECT os_id, order_release_gid, shipment_gid, quantity_kg, dq_flag
    FROM workspace.otm.ORDER_SHIPMENT
    WHERE os_id IN ('OS-X01','OS-X02','OS-X03')
""")
rows = cursor.fetchall()
print("\nNewly inserted Orphan rows:")
print(f"  {'os_id':<10} {'order_release_gid':<25} {'shipment_gid':<22} {'qty_kg':<8} {'dq_flag'}")
print("  " + "-" * 85)
for r in rows:
    print(f"  {r[0]:<10} {r[1]:<25} {r[2]:<22} {r[3]:<8} {r[4]}")

cursor.close()
conn.close()
