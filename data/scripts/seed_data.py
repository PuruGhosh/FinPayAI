"""
Synthetic data generator for the Google-Pay-style fintech POC.
All data is fake (Faker), no real people/accounts. Safe to publish/demo.
"""
import sqlite3
import random
from pathlib import Path
from faker import Faker

fake = Faker()
Faker.seed(42)
random.seed(42)

DATA_DIR = Path(__file__).resolve().parents[1]
DB_PATH = DATA_DIR / "db" / "finpay_poc.db"
SCHEMA_PATH = DATA_DIR / "db" / "schema.sql"

if DB_PATH.exists():
    DB_PATH.unlink()

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

with SCHEMA_PATH.open(encoding="utf-8") as f:
    cur.executescript(f.read())

# ----------------------------------------------------------------------
# DEPARTMENTS
# ----------------------------------------------------------------------
DEPARTMENTS = [
    ("FIN", "Finance", "CC-100"),
    ("HR", "Human Resources", "CC-200"),
    ("ENG", "Engineering", "CC-300"),
    ("COMPLIANCE", "Compliance & Risk", "CC-400"),
    ("CUST_SUPPORT", "Customer Support", "CC-500"),
    ("MARKETING", "Marketing & Growth", "CC-600"),
    ("EXEC", "Executive Office", "CC-000"),
]
for dept_id, name, cc in DEPARTMENTS:
    cur.execute(
        "INSERT INTO departments (department_id, name, cost_center) VALUES (?,?,?)",
        (dept_id, name, cc),
    )

# ----------------------------------------------------------------------
# EMPLOYEES
# ----------------------------------------------------------------------
ROLE_TITLES = {
    "FIN": ["Finance Analyst", "Accounts Manager", "Finance Lead"],
    "HR": ["HR Executive", "Recruiter", "HR Manager"],
    "ENG": ["Software Engineer", "Backend Engineer", "Engineering Manager"],
    "COMPLIANCE": ["Compliance Officer", "AML Analyst", "Risk Manager"],
    "CUST_SUPPORT": ["Support Agent", "Support Team Lead"],
    "MARKETING": ["Marketing Executive", "Campaign Manager"],
    "EXEC": ["CEO", "CTO", "COO"],
}

employees = []
emp_counter = 1

def new_emp_id():
    global emp_counter
    eid = f"EMP{emp_counter:04d}"
    emp_counter += 1
    return eid

# Executives first (admins)
for title in ROLE_TITLES["EXEC"]:
    eid = new_emp_id()
    employees.append({
        "employee_id": eid,
        "full_name": fake.name(),
        "department_id": "EXEC",
        "role_title": title,
        "access_role": "admin",
        "email": f"{eid.lower()}@finpay-demo.com",
        "phone": fake.phone_number(),
        "address": fake.address().replace("\n", ", "),
        "salary": round(random.uniform(4500000, 9000000), 2),
        "bank_account": fake.iban(),
        "national_id": fake.ssn(),
        "manager_id": None,
        "hire_date": fake.date_between(start_date="-6y", end_date="-2y").isoformat(),
    })

# Regular departments
for dept_id, name, cc in DEPARTMENTS:
    if dept_id == "EXEC":
        continue
    n_employees = random.randint(5, 8)
    manager_id = None
    for i in range(n_employees):
        eid = new_emp_id()
        is_manager = "Manager" in ROLE_TITLES[dept_id][-1] and i == 0
        role_title = ROLE_TITLES[dept_id][-1] if is_manager else random.choice(ROLE_TITLES[dept_id][:-1])
        access_role = "manager" if is_manager else "employee"
        emp = {
            "employee_id": eid,
            "full_name": fake.name(),
            "department_id": dept_id,
            "role_title": role_title,
            "access_role": access_role,
            "email": f"{eid.lower()}@finpay-demo.com",
            "phone": fake.phone_number(),
            "address": fake.address().replace("\n", ", "),
            "salary": round(random.uniform(600000, 2200000), 2),
            "bank_account": fake.iban(),
            "national_id": fake.ssn(),
            "manager_id": None,  # fill below
            "hire_date": fake.date_between(start_date="-5y", end_date="-1y").isoformat(),
        }
        if is_manager:
            manager_id = eid
        employees.append(emp)
    # backfill manager_id for non-managers in this dept
    for emp in employees[-n_employees:]:
        if emp["access_role"] == "employee":
            emp["manager_id"] = manager_id

for emp in employees:
    cur.execute("""
        INSERT INTO employees (employee_id, full_name, department_id, role_title,
            access_role, email, phone, address, salary, bank_account, national_id,
            manager_id, hire_date, status)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, 'active')
    """, (emp["employee_id"], emp["full_name"], emp["department_id"], emp["role_title"],
          emp["access_role"], emp["email"], emp["phone"], emp["address"], emp["salary"],
          emp["bank_account"], emp["national_id"], emp["manager_id"], emp["hire_date"]))

# set department heads
for dept_id, name, cc in DEPARTMENTS:
    heads = [e for e in employees if e["department_id"] == dept_id and e["access_role"] in ("manager", "admin")]
    if heads:
        cur.execute("UPDATE departments SET head_employee_id=? WHERE department_id=?",
                    (heads[0]["employee_id"], dept_id))

# ----------------------------------------------------------------------
# CUSTOMERS
# ----------------------------------------------------------------------
customers = []
for i in range(60):
    cid = f"CUST{i+1:05d}"
    customers.append({
        "customer_id": cid,
        "full_name": fake.name(),
        "email": fake.email(),
        "phone": fake.phone_number(),
        "address": fake.address().replace("\n", ", "),
        "national_id": fake.ssn(),
        "linked_bank_account": fake.iban(),
        "kyc_status": random.choice(["verified", "verified", "verified", "pending"]),
        "risk_tier": random.choices(["low", "medium", "high"], weights=[0.75, 0.18, 0.07])[0],
        "signup_date": fake.date_between(start_date="-3y", end_date="today").isoformat(),
    })
    cur.execute("""
        INSERT INTO customers (customer_id, full_name, email, phone, address,
            national_id, linked_bank_account, kyc_status, risk_tier, signup_date)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, tuple(customers[-1].values()))

# ----------------------------------------------------------------------
# TRANSACTIONS
# ----------------------------------------------------------------------
TXN_TYPES = ["p2p_transfer", "bill_pay", "merchant_payment", "refund", "cashback"]
for i in range(400):
    txn_id = f"TXN{i+1:06d}"
    cust = random.choice(customers)
    status = random.choices(["completed", "pending", "failed", "flagged"], weights=[0.8, 0.08, 0.07, 0.05])[0]
    dept_owner = "COMPLIANCE" if status == "flagged" else random.choices(["FIN", "CUST_SUPPORT"], weights=[0.7, 0.3])[0]
    created = fake.date_time_between(start_date="-180d", end_date="now")
    cur.execute("""
        INSERT INTO transactions (txn_id, customer_id, txn_type, amount, currency,
            status, channel, department_owner, flagged_reason, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (
        txn_id, cust["customer_id"], random.choice(TXN_TYPES),
        round(random.uniform(50, 75000), 2), "INR", status,
        random.choice(["app", "web", "api"]), dept_owner,
        random.choice(["velocity_check", "geo_mismatch", "amount_threshold", None]) if status == "flagged" else None,
        created.isoformat(),
    ))

# ----------------------------------------------------------------------
# OFFERS
# ----------------------------------------------------------------------
OFFERS = [
    ("First Transfer Free", "Zero fee on your first 5 P2P transfers.", "public", "new_users", 100.0),
    ("5% Cashback on Bill Payments", "Get 5% cashback up to ₹100 on electricity & water bills.", "public", "all", 5.0),
    ("Referral Bonus ₹150", "Refer a friend, both get ₹150 after their first transaction.", "public", "all", 0.0),
    ("Premium Cashback for High-Value Users", "10% cashback for customers with >₹5L monthly volume.", "all_internal", "high_value", 10.0),
    ("Employee FinPay Card Perks", "Internal staff cashback program on the corporate card.", "all_internal", "employees", 8.0),
    ("Festive Season Merchant Offer", "Flat 20% off at partner merchants during festive week.", "public", "all", 20.0),
]
for i, (title, desc, vis, seg, disc) in enumerate(OFFERS):
    cur.execute("""
        INSERT INTO offers (offer_id, title, description, department_owner, visibility,
            target_segment, discount_pct, valid_from, valid_to, status)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (f"OFFER{i+1:03d}", title, desc, "MARKETING", vis, seg, disc,
          "2026-01-01", "2026-12-31", "active"))

# ----------------------------------------------------------------------
# SUPPORT TICKETS
# ----------------------------------------------------------------------
support_agents = [e for e in employees if e["department_id"] == "CUST_SUPPORT"]
for i in range(50):
    tid = f"TICK{i+1:05d}"
    cust = random.choice(customers)
    agent = random.choice(support_agents)
    cur.execute("""
        INSERT INTO support_tickets (ticket_id, customer_id, assigned_employee_id,
            department_owner, subject, status, priority, created_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, (tid, cust["customer_id"], agent["employee_id"], "CUST_SUPPORT",
          random.choice(["Failed transaction refund", "Unable to link bank account",
                         "KYC verification issue", "Disputed cashback amount",
                         "App login issue"]),
          random.choice(["open", "resolved", "resolved", "escalated"]),
          random.choice(["low", "medium", "high"]),
          fake.date_time_between(start_date="-90d", end_date="now").isoformat()))

conn.commit()

# ----------------------------------------------------------------------
# Summary
# ----------------------------------------------------------------------
for table in ["departments", "employees", "customers", "transactions", "offers", "support_tickets"]:
    n = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"{table:20s}: {n} rows")

conn.close()
print(f"\nDB written to {DB_PATH}")
