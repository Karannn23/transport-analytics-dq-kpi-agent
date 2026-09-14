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

# 100+ rows covering ORD-0019 to ORD-0100
# Aligned with order table: pickup/delivery locs match ship_from/ship_to in order table
# DQ flags reflect Transport Analytics anomalies relevant to each order's own dq_flag

rows = [
    # ORD-0019 (Planned, No OS Match) -> No shipment mapped, ghost entry
    ("OS-019",  "OTM.ORD-2025-0019", "OTM.SHP-2025-020", 670,  "OTM.LOC-WHSE-01", "OTM.LOC-DC-EAST",  "YES", "STALE",  "Ghost Stale Delete"),
    # ORD-0020 (Planned, No OS Match) -> No shipment
    ("OS-020",  "OTM.ORD-2025-0020", "OTM.SHP-2025-021", 1100, "OTM.LOC-WHSE-03", "OTM.LOC-DC-SOUTH", "YES", "STALE",  "Ghost Stale Delete"),
    # ORD-0021
    ("OS-021",  "OTM.ORD-2025-0021", "OTM.SHP-2025-022", 1450, "OTM.LOC-WHSE-01", "OTM.LOC-DC-WEST",  "No",  "Active", "OK"),
    # ORD-0022
    ("OS-022",  "OTM.ORD-2025-0022", "OTM.SHP-2025-023", 980,  "OTM.LOC-WHSE-02", "OTM.LOC-DC-EAST",  "No",  "Active", "OK"),
    # ORD-0023
    ("OS-023",  "OTM.ORD-2025-0023", "OTM.SHP-2025-024", 2200, "OTM.LOC-WHSE-03", "OTM.LOC-DC-NORTH", "No",  "Active", "OK"),
    # ORD-0024
    ("OS-024",  "OTM.ORD-2025-0024", "OTM.SHP-2025-025", 750,  "OTM.LOC-WHSE-02", "OTM.LOC-DC-SOUTH", "No",  "Active", "OK"),
    # ORD-0025 (Planned, Zero Weight)
    ("OS-025",  "OTM.ORD-2025-0025", "OTM.SHP-2025-026", 0,    "OTM.LOC-WHSE-01", "OTM.LOC-DC-EAST",  "No",  "Active", "Zero Qty"),
    # ORD-0026
    ("OS-026",  "OTM.ORD-2025-0026", "OTM.SHP-2025-027", 1680, "OTM.LOC-WHSE-03", "OTM.LOC-DC-WEST",  "No",  "Active", "OK"),
    # ORD-0027 (Ghost Mapping) -> ghost stale delete + re-assigned
    ("OS-027",  "OTM.ORD-2025-0027", "OTM.SHP-2025-028", 540,  "OTM.LOC-WHSE-02", "OTM.LOC-DC-NORTH", "YES", "STALE",  "Ghost Stale Delete"),
    ("OS-027R", "OTM.ORD-2025-0027", "OTM.SHP-2025-089", 540,  "OTM.LOC-WHSE-02", "OTM.LOC-DC-NORTH", "No",  "Active", "Re-assigned"),
    # ORD-0028
    ("OS-028",  "OTM.ORD-2025-0028", "OTM.SHP-2025-029", 1990, "OTM.LOC-WHSE-01", "OTM.LOC-DC-SOUTH", "No",  "Active", "OK"),
    # ORD-0029
    ("OS-029",  "OTM.ORD-2025-0029", "OTM.SHP-2025-030", 870,  "OTM.LOC-WHSE-03", "OTM.LOC-DC-EAST",  "No",  "Active", "OK"),
    # ORD-0030
    ("OS-030",  "OTM.ORD-2025-0030", "OTM.SHP-2025-031", 1320, "OTM.LOC-WHSE-02", "OTM.LOC-DC-WEST",  "No",  "Active", "OK"),
    # ORD-0031
    ("OS-031",  "OTM.ORD-2025-0031", "OTM.SHP-2025-032", 1500, "OTM.LOC-WHSE-01", "OTM.LOC-DC-NORTH", "No",  "Active", "OK"),
    # ORD-0032 (Cancelled)
    ("OS-032",  "OTM.ORD-2025-0032", "OTM.SHP-2025-033", 910,  "OTM.LOC-WHSE-02", "OTM.LOC-DC-EAST",  "YES", "STALE",  "Cancelled Order"),
    # ORD-0033
    ("OS-033",  "OTM.ORD-2025-0033", "OTM.SHP-2025-034", 770,  "OTM.LOC-WHSE-03", "OTM.LOC-DC-SOUTH", "No",  "Active", "OK"),
    # ORD-0034
    ("OS-034",  "OTM.ORD-2025-0034", "OTM.SHP-2025-035", 2460, "OTM.LOC-WHSE-01", "OTM.LOC-DC-WEST",  "No",  "Active", "OK"),
    # ORD-0035
    ("OS-035",  "OTM.ORD-2025-0035", "OTM.SHP-2025-036", 1170, "OTM.LOC-WHSE-03", "OTM.LOC-DC-NORTH", "No",  "Active", "OK"),
    # ORD-0036
    ("OS-036",  "OTM.ORD-2025-0036", "OTM.SHP-2025-037", 650,  "OTM.LOC-WHSE-02", "OTM.LOC-DC-EAST",  "No",  "Active", "OK"),
    # ORD-0037 (Planned, Zero Weight)
    ("OS-037",  "OTM.ORD-2025-0037", "OTM.SHP-2025-038", 0,    "OTM.LOC-WHSE-01", "OTM.LOC-DC-SOUTH", "No",  "Active", "Zero Qty"),
    # ORD-0038
    ("OS-038",  "OTM.ORD-2025-0038", "OTM.SHP-2025-039", 1400, "OTM.LOC-WHSE-03", "OTM.LOC-DC-WEST",  "No",  "Active", "OK"),
    # ORD-0039
    ("OS-039",  "OTM.ORD-2025-0039", "OTM.SHP-2025-040", 800,  "OTM.LOC-WHSE-02", "OTM.LOC-DC-NORTH", "No",  "Active", "OK"),
    # ORD-0040 (No OS Match) -> split shipment with qty mismatch
    ("OS-040A", "OTM.ORD-2025-0040", "OTM.SHP-2025-041", 880,  "OTM.LOC-WHSE-01", "OTM.LOC-DC-EAST",  "No",  "Active", "Split Order"),
    ("OS-040B", "OTM.ORD-2025-0040", "OTM.SHP-2025-042", 900,  "OTM.LOC-WHSE-01", "OTM.LOC-DC-EAST",  "No",  "Active", "Split Qty Mismatch"),
    # ORD-0041
    ("OS-041",  "OTM.ORD-2025-0041", "OTM.SHP-2025-043", 920,  "OTM.LOC-WHSE-03", "OTM.LOC-DC-SOUTH", "No",  "Active", "OK"),
    # ORD-0042
    ("OS-042",  "OTM.ORD-2025-0042", "OTM.SHP-2025-044", 1350, "OTM.LOC-WHSE-02", "OTM.LOC-DC-WEST",  "No",  "Active", "OK"),
    # ORD-0043
    ("OS-043",  "OTM.ORD-2025-0043", "OTM.SHP-2025-045", 1800, "OTM.LOC-WHSE-01", "OTM.LOC-DC-NORTH", "No",  "Active", "OK"),
    # ORD-0044
    ("OS-044",  "OTM.ORD-2025-0044", "OTM.SHP-2025-046", 710,  "OTM.LOC-WHSE-03", "OTM.LOC-DC-EAST",  "No",  "Active", "OK"),
    # ORD-0045 (Cancelled)
    ("OS-045",  "OTM.ORD-2025-0045", "OTM.SHP-2025-047", 1260, "OTM.LOC-WHSE-02", "OTM.LOC-DC-SOUTH", "YES", "STALE",  "Cancelled Order"),
    # ORD-0046 (Ghost Mapping)
    ("OS-046",  "OTM.ORD-2025-0046", "OTM.SHP-2025-048", 580,  "OTM.LOC-WHSE-01", "OTM.LOC-DC-WEST",  "YES", "STALE",  "Ghost Stale Delete"),
    ("OS-046R", "OTM.ORD-2025-0046", "OTM.SHP-2025-090", 580,  "OTM.LOC-WHSE-01", "OTM.LOC-DC-WEST",  "No",  "Active", "Re-assigned"),
    # ORD-0047
    ("OS-047",  "OTM.ORD-2025-0047", "OTM.SHP-2025-049", 1480, "OTM.LOC-WHSE-03", "OTM.LOC-DC-NORTH", "No",  "Active", "OK"),
    # ORD-0048
    ("OS-048",  "OTM.ORD-2025-0048", "OTM.SHP-2025-050", 690,  "OTM.LOC-WHSE-02", "OTM.LOC-DC-EAST",  "No",  "Active", "OK"),
    # ORD-0049
    ("OS-049",  "OTM.ORD-2025-0049", "OTM.SHP-2025-051", 2140, "OTM.LOC-WHSE-01", "OTM.LOC-DC-SOUTH", "No",  "Active", "OK"),
    # ORD-0050
    ("OS-050",  "OTM.ORD-2025-0050", "OTM.SHP-2025-052", 470,  "OTM.LOC-WHSE-03", "OTM.LOC-DC-WEST",  "No",  "Active", "OK"),
    # ORD-0051
    ("OS-051",  "OTM.ORD-2025-0051", "OTM.SHP-2025-053", 930,  "OTM.LOC-WHSE-02", "OTM.LOC-DC-NORTH", "No",  "Active", "OK"),
    # ORD-0052
    ("OS-052",  "OTM.ORD-2025-0052", "OTM.SHP-2025-054", 1710, "OTM.LOC-WHSE-01", "OTM.LOC-DC-EAST",  "No",  "Active", "OK"),
    # ORD-0053
    ("OS-053",  "OTM.ORD-2025-0053", "OTM.SHP-2025-055", 740,  "OTM.LOC-WHSE-03", "OTM.LOC-DC-SOUTH", "No",  "Active", "OK"),
    # ORD-0054 (Planned, Zero Weight)
    ("OS-054",  "OTM.ORD-2025-0054", "OTM.SHP-2025-056", 0,    "OTM.LOC-WHSE-02", "OTM.LOC-DC-WEST",  "No",  "Active", "Zero Qty"),
    # ORD-0055
    ("OS-055",  "OTM.ORD-2025-0055", "OTM.SHP-2025-057", 1560, "OTM.LOC-WHSE-01", "OTM.LOC-DC-NORTH", "No",  "Active", "OK"),
    # ORD-0056
    ("OS-056",  "OTM.ORD-2025-0056", "OTM.SHP-2025-058", 640,  "OTM.LOC-WHSE-03", "OTM.LOC-DC-EAST",  "No",  "Active", "OK"),
    # ORD-0057
    ("OS-057",  "OTM.ORD-2025-0057", "OTM.SHP-2025-059", 1210, "OTM.LOC-WHSE-02", "OTM.LOC-DC-SOUTH", "No",  "Active", "OK"),
    # ORD-0058 (No OS Match) -> ghost stale
    ("OS-058",  "OTM.ORD-2025-0058", "OTM.SHP-2025-060", 820,  "OTM.LOC-WHSE-01", "OTM.LOC-DC-WEST",  "YES", "STALE",  "Ghost Stale Delete"),
    ("OS-058R", "OTM.ORD-2025-0058", "OTM.SHP-2025-091", 820,  "OTM.LOC-WHSE-01", "OTM.LOC-DC-WEST",  "No",  "Active", "Re-assigned"),
    # ORD-0059
    ("OS-059",  "OTM.ORD-2025-0059", "OTM.SHP-2025-061", 2250, "OTM.LOC-WHSE-03", "OTM.LOC-DC-NORTH", "No",  "Active", "OK"),
    # ORD-0060
    ("OS-060",  "OTM.ORD-2025-0060", "OTM.SHP-2025-062", 950,  "OTM.LOC-WHSE-02", "OTM.LOC-DC-EAST",  "No",  "Active", "OK"),
    # ORD-0061
    ("OS-061",  "OTM.ORD-2025-0061", "OTM.SHP-2025-063", 1450, "OTM.LOC-WHSE-01", "OTM.LOC-DC-SOUTH", "No",  "Active", "OK"),
    # ORD-0062
    ("OS-062",  "OTM.ORD-2025-0062", "OTM.SHP-2025-064", 700,  "OTM.LOC-WHSE-03", "OTM.LOC-DC-WEST",  "No",  "Active", "OK"),
    # ORD-0063
    ("OS-063",  "OTM.ORD-2025-0063", "OTM.SHP-2025-065", 1880, "OTM.LOC-WHSE-02", "OTM.LOC-DC-NORTH", "No",  "Active", "OK"),
    # ORD-0064 (Ghost Mapping)
    ("OS-064",  "OTM.ORD-2025-0064", "OTM.SHP-2025-066", 540,  "OTM.LOC-WHSE-01", "OTM.LOC-DC-EAST",  "YES", "STALE",  "Ghost Stale Delete"),
    ("OS-064R", "OTM.ORD-2025-0064", "OTM.SHP-2025-092", 540,  "OTM.LOC-WHSE-01", "OTM.LOC-DC-EAST",  "No",  "Active", "Re-assigned"),
    # ORD-0065
    ("OS-065",  "OTM.ORD-2025-0065", "OTM.SHP-2025-067", 1120, "OTM.LOC-WHSE-03", "OTM.LOC-DC-SOUTH", "No",  "Active", "OK"),
    # ORD-0066
    ("OS-066",  "OTM.ORD-2025-0066", "OTM.SHP-2025-068", 1730, "OTM.LOC-WHSE-02", "OTM.LOC-DC-WEST",  "No",  "Active", "OK"),
    # ORD-0067 (Cancelled)
    ("OS-067",  "OTM.ORD-2025-0067", "OTM.SHP-2025-069", 890,  "OTM.LOC-WHSE-01", "OTM.LOC-DC-NORTH", "YES", "STALE",  "Cancelled Order"),
    # ORD-0068
    ("OS-068",  "OTM.ORD-2025-0068", "OTM.SHP-2025-070", 1340, "OTM.LOC-WHSE-03", "OTM.LOC-DC-EAST",  "No",  "Active", "OK"),
    # ORD-0069
    ("OS-069",  "OTM.ORD-2025-0069", "OTM.SHP-2025-071", 660,  "OTM.LOC-WHSE-02", "OTM.LOC-DC-SOUTH", "No",  "Active", "OK"),
    # ORD-0070
    ("OS-070",  "OTM.ORD-2025-0070", "OTM.SHP-2025-072", 2100, "OTM.LOC-WHSE-01", "OTM.LOC-DC-WEST",  "No",  "Active", "OK"),
    # ORD-0071
    ("OS-071",  "OTM.ORD-2025-0071", "OTM.SHP-2025-073", 1080, "OTM.LOC-WHSE-03", "OTM.LOC-DC-NORTH", "No",  "Active", "OK"),
    # ORD-0072
    ("OS-072",  "OTM.ORD-2025-0072", "OTM.SHP-2025-074", 590,  "OTM.LOC-WHSE-02", "OTM.LOC-DC-EAST",  "No",  "Active", "OK"),
    # ORD-0073 (Planned, Zero Weight)
    ("OS-073",  "OTM.ORD-2025-0073", "OTM.SHP-2025-075", 0,    "OTM.LOC-WHSE-01", "OTM.LOC-DC-SOUTH", "No",  "Active", "Zero Qty"),
    # ORD-0074
    ("OS-074",  "OTM.ORD-2025-0074", "OTM.SHP-2025-076", 1490, "OTM.LOC-WHSE-03", "OTM.LOC-DC-WEST",  "No",  "Active", "OK"),
    # ORD-0075
    ("OS-075",  "OTM.ORD-2025-0075", "OTM.SHP-2025-077", 970,  "OTM.LOC-WHSE-02", "OTM.LOC-DC-NORTH", "No",  "Active", "OK"),
    # ORD-0076 (No OS Match) -> split
    ("OS-076A", "OTM.ORD-2025-0076", "OTM.SHP-2025-078", 1025, "OTM.LOC-WHSE-01", "OTM.LOC-DC-EAST",  "No",  "Active", "Split Order"),
    ("OS-076B", "OTM.ORD-2025-0076", "OTM.SHP-2025-079", 1050, "OTM.LOC-WHSE-01", "OTM.LOC-DC-EAST",  "No",  "Active", "Split Qty Mismatch"),
    # ORD-0077
    ("OS-077",  "OTM.ORD-2025-0077", "OTM.SHP-2025-080", 750,  "OTM.LOC-WHSE-03", "OTM.LOC-DC-SOUTH", "No",  "Active", "OK"),
    # ORD-0078
    ("OS-078",  "OTM.ORD-2025-0078", "OTM.SHP-2025-081", 1680, "OTM.LOC-WHSE-02", "OTM.LOC-DC-WEST",  "No",  "Active", "OK"),
    # ORD-0079
    ("OS-079",  "OTM.ORD-2025-0079", "OTM.SHP-2025-082", 830,  "OTM.LOC-WHSE-01", "OTM.LOC-DC-NORTH", "No",  "Active", "OK"),
    # ORD-0080
    ("OS-080",  "OTM.ORD-2025-0080", "OTM.SHP-2025-083", 1540, "OTM.LOC-WHSE-03", "OTM.LOC-DC-EAST",  "No",  "Active", "OK"),
    # ORD-0081
    ("OS-081",  "OTM.ORD-2025-0081", "OTM.SHP-2025-084", 620,  "OTM.LOC-WHSE-02", "OTM.LOC-DC-SOUTH", "No",  "Active", "OK"),
    # ORD-0082
    ("OS-082",  "OTM.ORD-2025-0082", "OTM.SHP-2025-085", 1820, "OTM.LOC-WHSE-01", "OTM.LOC-DC-WEST",  "No",  "Active", "OK"),
    # ORD-0083 (Ghost Mapping)
    ("OS-083",  "OTM.ORD-2025-0083", "OTM.SHP-2025-086", 1110, "OTM.LOC-WHSE-03", "OTM.LOC-DC-NORTH", "YES", "STALE",  "Ghost Stale Delete"),
    ("OS-083R", "OTM.ORD-2025-0083", "OTM.SHP-2025-093", 1110, "OTM.LOC-WHSE-03", "OTM.LOC-DC-NORTH", "No",  "Active", "Re-assigned"),
    # ORD-0084
    ("OS-084",  "OTM.ORD-2025-0084", "OTM.SHP-2025-094", 920,  "OTM.LOC-WHSE-02", "OTM.LOC-DC-EAST",  "No",  "Active", "OK"),
    # ORD-0085
    ("OS-085",  "OTM.ORD-2025-0085", "OTM.SHP-2025-095", 1430, "OTM.LOC-WHSE-01", "OTM.LOC-DC-SOUTH", "No",  "Active", "OK"),
    # ORD-0086
    ("OS-086",  "OTM.ORD-2025-0086", "OTM.SHP-2025-096", 510,  "OTM.LOC-WHSE-03", "OTM.LOC-DC-WEST",  "No",  "Active", "OK"),
    # ORD-0087
    ("OS-087",  "OTM.ORD-2025-0087", "OTM.SHP-2025-097", 2320, "OTM.LOC-WHSE-02", "OTM.LOC-DC-NORTH", "No",  "Active", "OK"),
    # ORD-0088 (Cancelled)
    ("OS-088",  "OTM.ORD-2025-0088", "OTM.SHP-2025-098", 690,  "OTM.LOC-WHSE-01", "OTM.LOC-DC-EAST",  "YES", "STALE",  "Cancelled Order"),
    # ORD-0089
    ("OS-089",  "OTM.ORD-2025-0089", "OTM.SHP-2025-099", 1270, "OTM.LOC-WHSE-03", "OTM.LOC-DC-SOUTH", "No",  "Active", "OK"),
    # ORD-0090
    ("OS-090",  "OTM.ORD-2025-0090", "OTM.SHP-2025-100", 840,  "OTM.LOC-WHSE-02", "OTM.LOC-DC-WEST",  "No",  "Active", "OK"),
    # ORD-0091
    ("OS-091",  "OTM.ORD-2025-0091", "OTM.SHP-2025-101", 1650, "OTM.LOC-WHSE-01", "OTM.LOC-DC-NORTH", "No",  "Active", "OK"),
    # ORD-0092
    ("OS-092",  "OTM.ORD-2025-0092", "OTM.SHP-2025-102", 730,  "OTM.LOC-WHSE-03", "OTM.LOC-DC-EAST",  "No",  "Active", "OK"),
    # ORD-0093
    ("OS-093",  "OTM.ORD-2025-0093", "OTM.SHP-2025-103", 1190, "OTM.LOC-WHSE-02", "OTM.LOC-DC-SOUTH", "No",  "Active", "OK"),
    # ORD-0094 (Planned, Zero Weight)
    ("OS-094",  "OTM.ORD-2025-0094", "OTM.SHP-2025-104", 0,    "OTM.LOC-WHSE-01", "OTM.LOC-DC-WEST",  "No",  "Active", "Zero Qty"),
    # ORD-0095
    ("OS-095",  "OTM.ORD-2025-0095", "OTM.SHP-2025-105", 1740, "OTM.LOC-WHSE-03", "OTM.LOC-DC-NORTH", "No",  "Active", "OK"),
    # ORD-0096
    ("OS-096",  "OTM.ORD-2025-0096", "OTM.SHP-2025-106", 610,  "OTM.LOC-WHSE-02", "OTM.LOC-DC-EAST",  "No",  "Active", "OK"),
    # ORD-0097 (No OS Match) -> ghost stale
    ("OS-097",  "OTM.ORD-2025-0097", "OTM.SHP-2025-107", 2080, "OTM.LOC-WHSE-01", "OTM.LOC-DC-SOUTH", "YES", "STALE",  "Ghost Stale Delete"),
    ("OS-097R", "OTM.ORD-2025-0097", "OTM.SHP-2025-108", 2080, "OTM.LOC-WHSE-01", "OTM.LOC-DC-SOUTH", "No",  "Active", "Re-assigned"),
    # ORD-0098
    ("OS-098",  "OTM.ORD-2025-0098", "OTM.SHP-2025-109", 480,  "OTM.LOC-WHSE-03", "OTM.LOC-DC-WEST",  "No",  "Active", "OK"),
    # ORD-0099
    ("OS-099",  "OTM.ORD-2025-0099", "OTM.SHP-2025-110", 950,  "OTM.LOC-WHSE-02", "OTM.LOC-DC-NORTH", "No",  "Active", "OK"),
    # ORD-0100
    ("OS-100",  "OTM.ORD-2025-0100", "OTM.SHP-2025-111", 1380, "OTM.LOC-WHSE-01", "OTM.LOC-DC-EAST",  "No",  "Active", "OK"),
]

# Build VALUES clause
values = ",\n".join(
    f"('{r[0]}','{r[1]}','{r[2]}',{r[3]},'{r[4]}','{r[5]}','{r[6]}','{r[7]}','{r[8]}')"
    for r in rows
)
insert_sql = f"INSERT INTO workspace.otm.ORDER_SHIPMENT VALUES\n{values}"

print(f"Inserting {len(rows)} rows into workspace.otm.ORDER_SHIPMENT ...")
cursor.execute(insert_sql)
print(f"[SUCCESS] {len(rows)} rows inserted successfully")

# Verify total
cursor.execute("SELECT COUNT(*) FROM workspace.otm.ORDER_SHIPMENT")
total = cursor.fetchone()[0]
print(f"\nTotal rows in workspace.otm.ORDER_SHIPMENT: {total}")

# DQ flag summary
cursor.execute("""
    SELECT dq_flag, COUNT(*) as cnt
    FROM workspace.otm.ORDER_SHIPMENT
    GROUP BY dq_flag
    ORDER BY cnt DESC
""")
summary = cursor.fetchall()
print("\nDQ Flag Summary:")
print(f"  {'Flag':<30} {'Count':>5}")
print("  " + "-" * 37)
for r in summary:
    print(f"  {r[0]:<30} {r[1]:>5}")

cursor.close()
conn.close()
