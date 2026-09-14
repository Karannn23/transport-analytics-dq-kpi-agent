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
INSERT INTO workspace.otm.ORDER_SHIPMENT VALUES
('OS-001','OTM.ORD-2025-0001','OTM.SHP-2025-001',1200,'OTM.LOC-WHSE-01','OTM.LOC-DC-NORTH','No','Active','OK'),
('OS-002','OTM.ORD-2025-0002','OTM.SHP-2025-002',850,'OTM.LOC-WHSE-01','OTM.LOC-DC-EAST','No','Active','OK'),
('OS-003A','OTM.ORD-2025-0003','OTM.SHP-2025-003',1150,'OTM.LOC-WHSE-02','OTM.LOC-DC-SOUTH','No','Active','Split Order'),
('OS-003B','OTM.ORD-2025-0003','OTM.SHP-2025-004',1200,'OTM.LOC-WHSE-02','OTM.LOC-DC-SOUTH','No','Active','Split Qty Mismatch'),
('OS-004','OTM.ORD-2025-0004','OTM.SHP-2025-005',0,'OTM.LOC-WHSE-02','OTM.LOC-DC-WEST','No','Active','Zero Qty'),
('OS-005','OTM.ORD-2025-0005','OTM.SHP-2025-006',975,'OTM.LOC-WHSE-03','OTM.LOC-DC-NORTH','No','Active','OK'),
('OS-006','OTM.ORD-2025-0006','OTM.SHP-2025-007',1450,'OTM.LOC-WHSE-03','OTM.LOC-DC-EAST','No','Active','OK'),
('OS-007','OTM.ORD-2025-0007','OTM.SHP-2025-008',630,'OTM.LOC-WHSE-01','OTM.LOC-DC-SOUTH','YES','STALE','Ghost Stale Delete'),
('OS-007R','OTM.ORD-2025-0007','OTM.SHP-2025-088',630,'OTM.LOC-WHSE-01','OTM.LOC-DC-SOUTH','No','Active','Re-assigned'),
('OS-008','OTM.ORD-2025-0008','OTM.SHP-2025-009',1100,'OTM.LOC-WHSE-02','OTM.LOC-DC-EAST','No','Active','OK'),
('OS-009','OTM.ORD-2025-0009','OTM.SHP-2025-010',760,'OTM.LOC-WHSE-01','OTM.LOC-DC-SOUTH','No','Active','OK'),
('OS-010','OTM.ORD-2025-0010','OTM.SHP-2025-011',2050,'OTM.LOC-WHSE-03','OTM.LOC-DC-WEST','No','Active','OK'),
('OS-011','OTM.ORD-2025-0011','OTM.SHP-2025-012',1300,'OTM.LOC-WHSE-02','OTM.LOC-DC-NORTH','No','Active','OK'),
('OS-012','OTM.ORD-2025-0012','OTM.SHP-2025-013',500,'OTM.LOC-WHSE-01','OTM.LOC-DC-SOUTH','No','Active','OK'),
('OS-013','OTM.ORD-2025-0013','OTM.SHP-2025-014',1750,'OTM.LOC-WHSE-03','OTM.LOC-DC-EAST','No','Active','OK'),
('OS-014','OTM.ORD-2025-0014','OTM.SHP-2025-015',920,'OTM.LOC-WHSE-02','OTM.LOC-DC-NORTH','No','Active','OK'),
('OS-015','OTM.ORD-2025-0015','OTM.SHP-2025-016',1600,'OTM.LOC-WHSE-01','OTM.LOC-DC-SOUTH','No','Active','OK'),
('OS-016','OTM.ORD-2025-0016','OTM.SHP-2025-017',430,'OTM.LOC-WHSE-03','OTM.LOC-DC-WEST','No','Active','OK'),
('OS-017','OTM.ORD-2025-0017','OTM.SHP-2025-018',890,'OTM.LOC-WHSE-02','OTM.LOC-DC-NORTH','No','Active','OK'),
('OS-018','OTM.ORD-2025-0018','OTM.SHP-2025-019',1250,'OTM.LOC-WHSE-01','OTM.LOC-DC-SOUTH','No','Active','OK')
"""

print("Inserting rows into workspace.otm.ORDER_SHIPMENT ...")
cursor.execute(insert_sql)
print("[SUCCESS] Rows inserted successfully")

# Verify row count
cursor.execute("SELECT COUNT(*) FROM workspace.otm.ORDER_SHIPMENT")
count = cursor.fetchone()[0]
print(f"\nTotal rows in workspace.otm.ORDER_SHIPMENT: {count}")

cursor.close()
conn.close()
