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
CREATE TABLE IF NOT EXISTS workspace.otm.ORDER (
    order_release_gid   VARCHAR(50),
    order_date          DATE,
    ship_from_loc_gid   VARCHAR(50),
    ship_to_loc_gid     VARCHAR(50),
    total_weight_kg     FLOAT,
    order_status        VARCHAR(20),
    dq_flag             VARCHAR(30)
)
"""

print("Creating table workspace.otm.ORDER ...")
cursor.execute(create_sql)
print("[SUCCESS] Table workspace.otm.ORDER created successfully")

# Verify
cursor.execute("SHOW TABLES IN workspace.otm")
rows = cursor.fetchall()
print(f"\nTables in workspace.otm ({len(rows)} total):")
print('-' * 40)
for r in rows:
    print(f"  - {r[1]}")

cursor.close()
conn.close()
