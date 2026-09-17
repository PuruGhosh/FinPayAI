---
doc_id: POL-005
doc_type: compliance
title: Anti-Money Laundering (AML) & Transaction Monitoring Policy
visibility: admin_only
department_owner: COMPLIANCE
version: 3.2
last_updated: 2026-03-05
classification: restricted
---

# AML & Transaction Monitoring Policy

*Classification: Restricted. Access limited to Compliance department and
Admin-tier roles (CEO/CTO/Executive). Contains detection thresholds that
must not be disclosed broadly, as disclosure could allow circumvention of
monitoring controls.*

## 1. Purpose
Defines FinPay's controls for detecting and reporting suspicious transaction
activity in line with applicable AML/KYC regulation.

## 2. Risk Tiering
Customers are assigned a risk_tier (low/medium/high) based on transaction
velocity, geography, KYC completeness, and behavioral signals.

## 3. Monitoring Triggers (illustrative categories)
Transactions may be auto-flagged based on velocity checks, geographic
mismatch signals, and threshold-based rules calibrated by the Compliance
team. Specific numeric thresholds are maintained in the Compliance system of
record and reviewed quarterly.

## 4. Escalation Process
Flagged transactions are queued for Compliance Officer review within 24
hours. Confirmed suspicious activity is escalated to the Risk Manager and,
where required, reported to the relevant regulatory body via a Suspicious
Transaction Report (STR).

## 5. Record Retention
Flagged transaction records and STR filings are retained for 5 years,
accessible only to Compliance and Executive roles.

## 6. Access Restriction
This policy and associated detection logic are restricted to Compliance and
Admin-tier roles. Finance and Customer Support may see that a transaction is
"flagged" and its status, but not the underlying detection rule or threshold.
