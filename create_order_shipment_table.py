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

create_sql = """
CREATE TABLE IF NOT EXISTS workspace.otm.ORDER_SHIPMENT (
    os_id               STRING,
    order_release_gid   STRING,
    shipment_gid        STRING,
    quantity_kg         FLOAT,
    pickup_loc_gid      STRING,
    delivery_loc_gid    STRING,
    otm_deleted         STRING,
    lake_status         STRING,
    dq_flag             STRING
)
USING DELTA
"""

print("Creating table workspace.otm.ORDER_SHIPMENT ...")
cursor.execute(create_sql)
print("[SUCCESS] Table workspace.otm.ORDER_SHIPMENT created successfully")

# Verify
cursor.execute("SHOW TABLES IN workspace.otm")
rows = cursor.fetchall()
print(f"\nTables in workspace.otm ({len(rows)} total):")
print('-' * 40)
for r in rows:
    print(f"  - {r[1]}")

cursor.close()
conn.close()
