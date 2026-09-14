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
CREATE TABLE IF NOT EXISTS workspace.otm.SHIPMENT (
    shipment_gid        STRING,
    planned_pickup      DATE,
    planned_delivery    DATE,
    actual_departure    DATE,
    actual_arrival      DATE,
    weight_kg           FLOAT,
    status              STRING,
    dq_flag             STRING
)
USING DELTA
"""

print("Creating table workspace.otm.SHIPMENT ...")
cursor.execute(create_sql)
print("[SUCCESS] Table workspace.otm.SHIPMENT created successfully")

# Verify all tables in schema
cursor.execute("SHOW TABLES IN workspace.otm")
rows = cursor.fetchall()
print(f"\nTables in workspace.otm ({len(rows)} total):")
print('-' * 40)
for r in rows:
    print(f"  - {r[1]}")

cursor.close()
conn.close()
