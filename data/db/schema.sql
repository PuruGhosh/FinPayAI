-- =====================================================================
-- SCHEMA NOTES FOR ACCESS CONTROL
-- Every table that needs scoping carries a `department_owner` column.
-- Every table with personal data carries an explicit PII column list
-- (see PII_COLUMNS in scoped_query.py) so masking is data-driven,
-- not guessed from column names at query time.
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- DEPARTMENTS
-- ---------------------------------------------------------------------
CREATE TABLE departments (
    department_id   TEXT PRIMARY KEY,   -- e.g. 'FIN', 'HR', 'ENG'
    name            TEXT NOT NULL,      -- e.g. 'Finance'
    head_employee_id TEXT,              -- FK to employees, set after seeding
    cost_center     TEXT
);

-- ---------------------------------------------------------------------
-- EMPLOYEES  (internal users)
-- PII columns: email, phone, address, salary, bank_account, national_id
-- ---------------------------------------------------------------------
CREATE TABLE employees (
    employee_id     TEXT PRIMARY KEY,
    full_name       TEXT NOT NULL,
    department_id   TEXT NOT NULL REFERENCES departments(department_id),
    role_title      TEXT NOT NULL,
    access_role     TEXT NOT NULL CHECK (access_role IN ('employee','manager','admin')),
    email           TEXT,   -- PII
    phone           TEXT,   -- PII
    address         TEXT,   -- PII
    salary          REAL,   -- PII
    bank_account    TEXT,   -- PII
    national_id     TEXT,   -- PII
    manager_id      TEXT REFERENCES employees(employee_id),
    hire_date       TEXT,
    status          TEXT DEFAULT 'active'
);

-- ---------------------------------------------------------------------
-- CUSTOMERS  (external, product users of the fintech app)
-- PII columns: email, phone, address, national_id, linked_bank_account
-- ---------------------------------------------------------------------
CREATE TABLE customers (
    customer_id     TEXT PRIMARY KEY,
    full_name       TEXT NOT NULL,
    email           TEXT,   -- PII
    phone           TEXT,   -- PII
    address         TEXT,   -- PII
    national_id     TEXT,   -- PII
    linked_bank_account TEXT, -- PII
    kyc_status      TEXT,
    risk_tier       TEXT,   -- low/medium/high, used by Compliance
    signup_date     TEXT,
    home_department_owner TEXT DEFAULT 'CUST_SUPPORT' -- which dept "owns" customer records
);

-- ---------------------------------------------------------------------
-- TRANSACTIONS
-- department_owner: which internal team this txn is scoped to
--   (Finance = settlement/ledger, Compliance = flagged/AML, CustSupport = disputes)
-- PII columns: none directly, but joins to customers leak PII -- handle in scoped_query
-- ---------------------------------------------------------------------
CREATE TABLE transactions (
    txn_id          TEXT PRIMARY KEY,
    customer_id     TEXT REFERENCES customers(customer_id),
    txn_type        TEXT,   -- 'p2p_transfer','bill_pay','merchant_payment','refund','cashback'
    amount          REAL,
    currency        TEXT DEFAULT 'INR',
    status          TEXT,   -- 'completed','pending','failed','flagged'
    channel         TEXT,   -- 'app','web','api'
    department_owner TEXT NOT NULL, -- 'FIN','COMPLIANCE','CUST_SUPPORT'
    flagged_reason  TEXT,   -- populated only for compliance-flagged txns
    created_at      TEXT
);

-- ---------------------------------------------------------------------
-- OFFERS  (promotions/cashback - mostly public-facing)
-- ---------------------------------------------------------------------
CREATE TABLE offers (
    offer_id        TEXT PRIMARY KEY,
    title           TEXT,
    description     TEXT,
    department_owner TEXT,  -- 'MARKETING'
    visibility      TEXT,   -- 'public','all_internal'
    target_segment  TEXT,   -- e.g. 'new_users','high_value','all'
    discount_pct    REAL,
    valid_from      TEXT,
    valid_to        TEXT,
    status          TEXT
);

-- ---------------------------------------------------------------------
-- SUPPORT_TICKETS  (customer support / dispute cases)
-- department_owner scoping + linked customer PII
-- ---------------------------------------------------------------------
CREATE TABLE support_tickets (
    ticket_id       TEXT PRIMARY KEY,
    customer_id     TEXT REFERENCES customers(customer_id),
    assigned_employee_id TEXT REFERENCES employees(employee_id),
    department_owner TEXT DEFAULT 'CUST_SUPPORT',
    subject         TEXT,
    status          TEXT,   -- 'open','resolved','escalated'
    priority        TEXT,
    created_at      TEXT
);

-- ---------------------------------------------------------------------
-- DOC_METADATA  (mirrors what will be stored as Chroma metadata,
-- kept here too so you can audit/query visibility rules relationally)
-- ---------------------------------------------------------------------
CREATE TABLE doc_metadata (
    doc_id          TEXT PRIMARY KEY,
    file_name       TEXT,
    doc_type        TEXT,       -- 'policy','handbook','compliance','public'
    visibility      TEXT,       -- 'public','all_internal','dept:<id>','admin_only'
    department_owner TEXT,
    title           TEXT
);
