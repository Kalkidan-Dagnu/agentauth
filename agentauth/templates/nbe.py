"""
NBE Ethiopia Policy Templates.

Natural language policy rule sets based on directives issued by the
National Bank of Ethiopia (NBE) — the central bank and financial regulator
of Ethiopia.

Templates:
  1. NBE_PAYMENT_AGENT      Payment System Directive FIS/01/2023
  2. NBE_FOREX_AGENT        Foreign Exchange Directive
  3. NBE_LENDING_AGENT      Credit and Lending Directive
  4. NBE_KYC_AGENT          AML / KYC Directive
  5. NBE_AUDIT_AGENT        Internal Audit and Compliance Directive
  6. NBE_MOBILE_BANKING     Mobile and Internet Banking Directive
  7. NBE_INSURANCE_AGENT    Insurance Business Directive

These rules are written in plain English so Gemini can reason over them
in context. Each rule corresponds to a real NBE regulatory requirement.
Developers can append overrides to tighten limits for their specific product.

References:
  - NBE website: https://nbe.gov.et
  - Directives library: https://nbe.gov.et/directives/
"""

from __future__ import annotations

from agentauth.templates.registry import PolicyTemplate, TemplateDefinition, registry

# ── 1. Payment Agent ──────────────────────────────────────────────────────────

registry.register(TemplateDefinition(
    name=PolicyTemplate.NBE_PAYMENT_AGENT,
    display_name="NBE Payment Agent",
    description=(
        "Governs AI agents processing electronic payments and fund transfers "
        "in Ethiopia under the NBE Payment System Directive (FIS/01/2023)."
    ),
    regulator="National Bank of Ethiopia (NBE)",
    jurisdiction="Ethiopia",
    version="1.0.0",
    tags=["payment", "transfer", "fintech", "ethiopia", "nbe"],
    references=[
        "NBE Payment System Directive FIS/01/2023",
        "NBE Electronic Fund Transfer Directive",
        "NBE Consumer Protection Directive FIS/02/2023",
    ],
    rules=[
        # Transaction limits
        "Agent may not process a single payment transaction exceeding ETB 200,000 "
        "without explicit human approval.",
        "Agent may not process more than ETB 1,000,000 in cumulative daily outgoing "
        "transfers from a single account without escalating for human review.",
        "Agent may not process international transfers exceeding USD 5,000 equivalent "
        "without documented NBE foreign exchange approval.",

        # KYC and onboarding
        "Agent must verify that the sender's account has completed Tier 2 KYC "
        "(national ID verified) before processing any transfer above ETB 10,000.",
        "Agent must reject transactions from accounts flagged as dormant, frozen, "
        "or under regulatory hold.",
        "Agent must confirm the recipient account exists and is active before "
        "initiating any fund transfer.",

        # Operational hours and settlement
        "Agent may only initiate inter-bank transfers during NBE-approved settlement "
        "windows: Monday to Friday, 08:00 to 17:00 EAT, excluding public holidays.",
        "Agent must route all transactions through the NBE-approved Ethiopian "
        "Interbank Settlement System (EISS).",

        # AML / sanctions
        "Agent must screen all parties against the NBE sanctions list and the "
        "Ethiopian Financial Intelligence Center (EFIC) watchlist before processing.",
        "Agent must flag and escalate any transaction that matches patterns of "
        "structuring, smurfing, or layering for human AML review.",
        "Agent must not process payments to or from countries on the FATF "
        "high-risk and non-cooperative jurisdictions list.",

        # Receipts and records
        "Agent must generate and store a transaction receipt for every completed "
        "payment, including timestamp, parties, amount, and reference number.",
        "Agent must retain all transaction records for a minimum of 10 years "
        "as required by NBE record-keeping directives.",

        # Error handling
        "Agent must not retry a failed transaction more than 3 times without "
        "notifying the account holder.",
        "Agent must immediately reverse and report any duplicate transaction "
        "detected within the same business day.",
    ],
))

# ── 2. Forex Agent ────────────────────────────────────────────────────────────

registry.register(TemplateDefinition(
    name=PolicyTemplate.NBE_FOREX_AGENT,
    display_name="NBE Foreign Exchange Agent",
    description=(
        "Governs AI agents handling foreign currency transactions, remittances, "
        "and forex operations under NBE foreign exchange directives."
    ),
    regulator="National Bank of Ethiopia (NBE)",
    jurisdiction="Ethiopia",
    version="1.0.0",
    tags=["forex", "remittance", "foreign exchange", "ethiopia", "nbe"],
    references=[
        "NBE Foreign Exchange Directive FXD/60/2024",
        "NBE Forex Bureaux Directive",
        "NBE Directive on Retention of Export Proceeds",
    ],
    rules=[
        # Approved currencies and rates
        "Agent may only transact in currencies officially listed on the NBE "
        "daily foreign exchange rate bulletin.",
        "Agent must use the NBE reference exchange rate or a rate within the "
        "NBE-permitted band (currently ±2% of the reference rate).",
        "Agent must not buy or sell foreign currency at a rate that deviates "
        "more than the NBE-permitted spread from the daily reference rate.",

        # Transaction limits and reporting
        "Agent may not execute a single forex transaction exceeding USD 50,000 "
        "or equivalent without NBE prior approval.",
        "Agent must report all forex transactions above USD 10,000 to the NBE "
        "within 24 hours of execution.",
        "Agent must submit daily consolidated forex position reports to NBE "
        "by 18:00 EAT.",

        # Export and import proceeds
        "Agent must ensure that 30% of all foreign currency export proceeds "
        "are surrendered to NBE as required by retention directives.",
        "Agent may only release import forex to entities with valid NBE-approved "
        "Letter of Credit (LC) or advance payment authorization.",

        # Remittances
        "Agent may process inbound remittances from licensed international money "
        "transfer operators (MTOs) only — unlicensed sources must be rejected.",
        "Agent must verify that outbound remittances have an approved NBE purpose "
        "code (education, medical, family support, business) before processing.",
        "Agent must flag and escalate remittances with no declared purpose or "
        "remittances to high-risk jurisdictions.",

        # AML
        "Agent must screen all forex counterparties against NBE and FATF "
        "sanctions lists before every transaction.",
        "Agent must escalate any customer who conducts multiple small forex "
        "transactions within a 24-hour period that collectively exceed the "
        "reporting threshold (structuring indicators).",

        # Records
        "Agent must maintain detailed forex transaction logs for 10 years, "
        "including rate used, purpose, counterparty identity, and NBE reference.",
    ],
))

# ── 3. Lending Agent ──────────────────────────────────────────────────────────

registry.register(TemplateDefinition(
    name=PolicyTemplate.NBE_LENDING_AGENT,
    display_name="NBE Lending Agent",
    description=(
        "Governs AI agents involved in credit assessment, loan approval, "
        "and collection under NBE credit and lending directives."
    ),
    regulator="National Bank of Ethiopia (NBE)",
    jurisdiction="Ethiopia",
    version="1.0.0",
    tags=["lending", "credit", "loan", "microfinance", "ethiopia", "nbe"],
    references=[
        "NBE Credit Risk Management Directive SBB/75/2022",
        "NBE Microfinance Institutions Directive MFI/23/2020",
        "NBE Interest Rate Directive",
    ],
    rules=[
        # Credit assessment
        "Agent must perform a creditworthiness assessment using NBE-approved "
        "criteria before recommending any loan approval.",
        "Agent must check the NBE Credit Reference Bureau (CRB) for the "
        "applicant's credit history before processing any loan above ETB 50,000.",
        "Agent may not approve a loan to a borrower who already has a "
        "non-performing loan (NPL) at any NBE-regulated institution.",

        # Loan limits and collateral
        "Agent may not approve an unsecured loan exceeding ETB 500,000 to "
        "an individual borrower without senior credit officer approval.",
        "Agent must verify that the declared collateral value covers at least "
        "125% of the loan principal before approval.",
        "Agent may not approve a loan where the borrower's total debt-to-income "
        "ratio would exceed 50% after the new loan.",

        # Interest rates
        "Agent must apply interest rates within the range set by the NBE "
        "monetary policy directive — currently a minimum lending rate of 7%.",
        "Agent must not apply compound interest in a manner that violates NBE "
        "consumer protection guidelines.",
        "Agent must clearly disclose the Annual Percentage Rate (APR), all fees, "
        "and penalty charges to the borrower before loan disbursement.",

        # Disbursement and collections
        "Agent may only disburse loan funds to the verified bank account of "
        "the borrower — third-party disbursements require escalation.",
        "Agent must not initiate any collection action before the loan is "
        "30 days past due, in compliance with NBE fair lending practices.",
        "Agent must escalate any loan that becomes 90 days past due for "
        "NPL classification and provision allocation.",

        # Reporting
        "Agent must report all new loans above ETB 1,000,000 to the NBE "
        "credit registry within 5 business days of disbursement.",
        "Agent must generate monthly loan portfolio quality reports for "
        "submission to NBE by the 10th of each month.",
    ],
))

# ── 4. KYC Agent ─────────────────────────────────────────────────────────────

registry.register(TemplateDefinition(
    name=PolicyTemplate.NBE_KYC_AGENT,
    display_name="NBE KYC / AML Agent",
    description=(
        "Governs AI agents performing customer identity verification, "
        "due diligence, and anti-money laundering screening under NBE "
        "AML/KYC directives and FATF recommendations."
    ),
    regulator="National Bank of Ethiopia (NBE)",
    jurisdiction="Ethiopia",
    version="1.0.0",
    tags=["kyc", "aml", "identity", "compliance", "ethiopia", "nbe"],
    references=[
        "NBE AML/CFT Directive SBB/55/2011 and amendments",
        "EFIC (Ethiopian Financial Intelligence Center) Guidelines",
        "FATF 40 Recommendations",
        "NBE Customer Due Diligence Directive",
    ],
    rules=[
        # Identity verification tiers
        "Agent may onboard a Tier 1 customer (transaction limit ETB 5,000/day) "
        "using mobile number and self-declared name only.",
        "Agent must collect and verify a government-issued national ID "
        "(Fayda ID, passport, or kebele ID) for Tier 2 onboarding "
        "(transaction limit ETB 50,000/day).",
        "Agent must collect utility bill or similar proof of address, plus "
        "source-of-funds declaration, for Tier 3 onboarding "
        "(transaction limit above ETB 50,000/day).",

        # Enhanced Due Diligence (EDD)
        "Agent must apply Enhanced Due Diligence (EDD) to all Politically "
        "Exposed Persons (PEPs), their immediate family, and close associates.",
        "Agent must escalate all PEP onboarding requests for senior compliance "
        "officer approval — agent may not onboard PEPs autonomously.",
        "Agent must apply EDD to customers from FATF high-risk jurisdictions, "
        "including documenting the business rationale for the relationship.",

        # Sanctions screening
        "Agent must screen every new customer against the NBE sanctions list, "
        "EFIC watchlist, UN Security Council list, and OFAC SDN list.",
        "Agent must re-screen all existing customers against updated sanctions "
        "lists at least once every 30 days.",
        "Agent must immediately freeze any account that matches a sanctions "
        "list entry and escalate to the compliance officer within 1 hour.",

        # Transaction monitoring
        "Agent must flag cash transactions above ETB 300,000 as a Suspicious "
        "Transaction Report (STR) trigger for human review.",
        "Agent must flag any customer whose transaction volume increases by "
        "more than 300% month-over-month for review.",
        "Agent must escalate all transactions with no plausible business "
        "purpose or inconsistent with the customer's known profile.",

        # Data and records
        "Agent must retain all KYC documents and verification records for "
        "a minimum of 10 years after the customer relationship ends.",
        "Agent must not share customer identity data with third parties "
        "without explicit NBE authorization or court order.",
    ],
))

# ── 5. Audit Agent ────────────────────────────────────────────────────────────

registry.register(TemplateDefinition(
    name=PolicyTemplate.NBE_AUDIT_AGENT,
    display_name="NBE Audit & Compliance Agent",
    description=(
        "Governs AI agents performing internal audit, compliance monitoring, "
        "and regulatory reporting under NBE audit directives. "
        "This template enforces strict read-only access — the agent cannot "
        "modify, delete, or approve anything."
    ),
    regulator="National Bank of Ethiopia (NBE)",
    jurisdiction="Ethiopia",
    version="1.0.0",
    tags=["audit", "compliance", "reporting", "read-only", "ethiopia", "nbe"],
    references=[
        "NBE Internal Audit Directive SBB/68/2019",
        "NBE Corporate Governance Directive SBB/66/2019",
        "NBE Risk Management Framework",
    ],
    rules=[
        # Read-only constraint
        "Agent may only read, query, and report on data — it must never "
        "create, modify, delete, approve, or execute any transaction or record.",
        "Agent must escalate any request to perform a write operation for "
        "human authorization before proceeding.",

        # Scope of access
        "Agent may access transaction records, account balances, and audit "
        "logs only for the entities explicitly assigned to its audit scope.",
        "Agent must not access customer personal data beyond what is strictly "
        "necessary for the audit task at hand (data minimization).",
        "Agent may not access production systems directly — all data access "
        "must be through read-only audit replicas or approved reporting APIs.",

        # Reporting obligations
        "Agent must generate quarterly internal audit reports covering "
        "all material risk areas as defined by NBE's Internal Audit Directive.",
        "Agent must report any material control deficiency to the Board "
        "Audit Committee within 5 business days of discovery.",
        "Agent must submit annual regulatory compliance reports to NBE "
        "by January 31 of each year.",

        # Independence and conflicts
        "Agent must flag and escalate any audit finding involving a "
        "director, senior officer, or related party for independent review.",
        "Agent must not suppress, alter, or selectively present audit "
        "findings — all material findings must be reported completely.",

        # Evidence handling
        "Agent must maintain a complete, tamper-evident audit trail of "
        "every query, report generated, and finding logged.",
        "Agent must retain all audit working papers for a minimum of "
        "7 years as required by NBE record retention directives.",
    ],
))

# ── 6. Mobile Banking Agent ───────────────────────────────────────────────────

registry.register(TemplateDefinition(
    name=PolicyTemplate.NBE_MOBILE_BANKING,
    display_name="NBE Mobile Banking Agent",
    description=(
        "Governs AI agents operating within mobile and internet banking "
        "platforms under NBE Mobile and Internet Banking Directive (FIS/03/2023). "
        "Covers session management, channel limits, device binding, and fraud."
    ),
    regulator="National Bank of Ethiopia (NBE)",
    jurisdiction="Ethiopia",
    version="1.0.0",
    tags=["mobile banking", "internet banking", "fintech", "ethiopia", "nbe"],
    references=[
        "NBE Mobile and Internet Banking Directive FIS/03/2023",
        "NBE Cyber Security Directive FIS/04/2023",
        "NBE Consumer Protection Directive FIS/02/2023",
    ],
    rules=[
        # Channel transaction limits
        "Agent may not process a single mobile banking transaction exceeding "
        "ETB 50,000 without triggering an additional OTP or biometric confirmation.",
        "Agent may not allow cumulative mobile channel transfers exceeding "
        "ETB 300,000 per customer per day.",
        "Agent must block any mobile banking session that has been inactive "
        "for more than 5 minutes and require re-authentication.",

        # Authentication and device binding
        "Agent must enforce multi-factor authentication (MFA) — at minimum "
        "password plus OTP — for all login and transaction approval actions.",
        "Agent must reject login attempts from unregistered devices and "
        "escalate for device binding confirmation by the account holder.",
        "Agent must lock the account after 5 consecutive failed PIN or "
        "password attempts and require a branch or call center unlock.",

        # Fraud detection
        "Agent must flag and block any transaction initiated from a device "
        "or IP address flagged as high-risk in the fraud detection system.",
        "Agent must escalate any transaction where the geolocation of the "
        "device is inconsistent with the customer's registered location "
        "by more than 500 km.",
        "Agent must detect and block SIM-swap fraud indicators: transactions "
        "initiated within 24 hours of a SIM change must require additional "
        "identity verification.",

        # Customer protection
        "Agent must send an SMS or push notification to the customer's "
        "registered number for every transaction above ETB 1,000.",
        "Agent must provide a cooling-off period of 10 minutes for "
        "first-time transfers to a new beneficiary above ETB 10,000, "
        "during which the customer can cancel.",
        "Agent must not store the customer's full PIN, password, or card "
        "number in device storage or application logs.",

        # Availability and incident response
        "Agent must escalate any service outage exceeding 2 hours to the "
        "NBE-designated incident reporting channel within 4 hours.",
        "Agent must maintain an audit log of all mobile banking sessions "
        "including device ID, IP address, and transaction details for 5 years.",
    ],
))

# ── 7. Insurance Agent ────────────────────────────────────────────────────────

registry.register(TemplateDefinition(
    name=PolicyTemplate.NBE_INSURANCE_AGENT,
    display_name="NBE Insurance Agent",
    description=(
        "Governs AI agents operating in the Ethiopian insurance sector under "
        "NBE Insurance Business Directive. Covers policy issuance, claims "
        "processing, premium handling, and consumer protection."
    ),
    regulator="National Bank of Ethiopia (NBE)",
    jurisdiction="Ethiopia",
    version="1.0.0",
    tags=["insurance", "claims", "premium", "ethiopia", "nbe"],
    references=[
        "NBE Insurance Business Directive IBD/19/2011 and amendments",
        "NBE Insurance Agents and Brokers Directive",
        "NBE Micro-Insurance Directive MID/01/2020",
        "Ethiopian Insurance Corporation Guidelines",
    ],
    rules=[
        # Policy issuance
        "Agent may only issue insurance policies for products that are "
        "pre-approved and registered with the NBE — no unapproved products.",
        "Agent must verify the customer's identity (Tier 2 KYC minimum) "
        "before issuing any insurance policy.",
        "Agent must clearly disclose all policy terms, exclusions, premium "
        "amounts, and claim procedures to the customer before issuance.",
        "Agent may not issue a life insurance policy with a sum assured "
        "above ETB 5,000,000 without underwriting officer approval.",

        # Premium collection
        "Agent must issue an official receipt for every premium payment "
        "collected, referencing the policy number and coverage period.",
        "Agent must not use premium funds collected for any purpose other "
        "than remitting to the insurer within 2 business days.",
        "Agent must escalate any premium refund request above ETB 50,000 "
        "for finance officer approval before processing.",

        # Claims processing
        "Agent may process and approve straightforward claims up to ETB 20,000 "
        "where the loss event is documented and policy is in force.",
        "Agent must escalate all claims above ETB 20,000 or any claim "
        "involving bodily injury, death, or third-party liability to a "
        "licensed claims adjuster.",
        "Agent must not deny a claim without providing the customer with "
        "a written reason and their right to appeal within 15 days.",
        "Agent must complete initial claims acknowledgment within 48 hours "
        "of a claim being filed, as required by NBE consumer protection rules.",

        # Reserves and solvency
        "Agent must flag any situation where claim payments would cause the "
        "insurer's solvency margin to fall below the NBE minimum (150%) "
        "and escalate immediately.",

        # Anti-fraud
        "Agent must flag duplicate claims, inconsistent loss narratives, or "
        "claims filed suspiciously close to policy inception for fraud review.",
        "Agent must screen claimants and beneficiaries against the NBE "
        "insurance fraud registry before processing any claim above ETB 10,000.",

        # Records
        "Agent must retain all policy documents, premium receipts, and "
        "claims records for a minimum of 10 years.",
    ],
))
