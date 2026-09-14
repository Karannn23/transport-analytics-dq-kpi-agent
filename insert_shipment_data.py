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
INSERT INTO workspace.otm.SHIPMENT
(shipment_gid, planned_pickup, planned_delivery, actual_departure, actual_arrival, weight_kg, status, dq_flag)
VALUES
('OTM.SHP-2025-001','2025-06-02','2025-06-03','2025-06-02','2025-06-03',1200,'Closed','OK'),
('OTM.SHP-2025-002','2025-06-02','2025-06-04','2025-06-02','2025-06-04',850,'Closed','OK'),
('OTM.SHP-2025-003','2025-06-03','2025-06-05','2025-06-03','2025-06-05',1150,'Closed','OK'),
('OTM.SHP-2025-004','2025-06-03','2025-06-05','2025-06-03','2025-06-05',1200,'Closed','OK'),
('OTM.SHP-2025-005','2025-06-03','2025-06-04','2025-06-03','2025-06-04',0,'Closed','Zero Weight'),
('OTM.SHP-2025-006','2025-06-04','2025-06-06','2025-06-04','2025-06-06',975,'Closed','OK'),
('OTM.SHP-2025-007','2025-06-04','2025-06-05','2025-06-04','2025-06-05',1450,'Closed','OK'),
('OTM.SHP-2025-008','2025-06-05','2025-06-06',NULL,NULL,630,'Planned','Ghost - OS link deleted in OTM'),
('OTM.SHP-2025-008R','2025-06-05','2025-06-06','2025-06-05','2025-06-06',630,'Closed','Re-assigned (active)'),
('OTM.SHP-2025-009','2025-06-05','2025-06-07','2025-06-05','2025-06-07',1100,'Closed','OK'),
('OTM.SHP-2025-010','2025-06-06','2025-06-07','2025-06-07','2025-06-06',760,'Closed','Date Seq Violation'),
('OTM.SHP-2025-011','2025-06-06','2025-06-08','2025-06-06','2025-06-08',2050,'Closed','OK'),
('OTM.SHP-2025-012','2025-06-07','2025-06-09','2025-06-07','2025-06-09',1300,'Closed','OK'),
('OTM.SHP-2025-013','2025-06-07','2025-06-08','2025-06-07','2025-06-08',500,'Closed','OK'),
('OTM.SHP-2025-014','2025-06-08','2025-06-10','2025-06-08','2025-06-10',1750,'Closed','OK'),
('OTM.SHP-2025-015','2025-06-08','2025-06-09',NULL,NULL,920,'Cancelled','OK'),
('OTM.SHP-2025-016','2025-06-09','2025-06-11','2025-06-09','2025-06-11',1600,'Closed','OK'),
('OTM.SHP-2025-017','2025-06-09','2025-06-10','2025-06-09',NULL,430,'In Transit','Missing Actual Arrival'),
('OTM.SHP-2025-018','2025-06-10','2025-06-11','2025-06-10','2025-06-11',890,'Closed','OK'),
('OTM.SHP-2025-019','2025-06-10','2025-06-12','2025-06-10','2025-06-12',1250,'Closed','OK'),
('OTM.SHP-2025-020','2025-06-11','2025-06-13','2025-06-11','2025-06-13',500,'DISPATCHED','Invalid Status'),
('OTM.SHP-2025-021','2025-06-11','2025-06-12','2025-06-11','2025-06-12',340,'Closed','Orphan - No ORDER'),
('OTM.SHP-2025-022','2025-06-12','2025-06-13','2025-06-12','2025-06-13',780,'Closed','Orphan - No ORDER')
"""

print("Inserting 23 rows into workspace.otm.SHIPMENT ...")
cursor.execute(insert_sql)
print("[SUCCESS] Rows inserted successfully")

# Verify total
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
print("\nDQ Flag Summary:")
print(f"  {'Flag':<40} {'Count':>5}")
print("  " + "-" * 47)
for r in rows:
    print(f"  {r[0]:<40} {r[1]:>5}")

cursor.close()
conn.close()
