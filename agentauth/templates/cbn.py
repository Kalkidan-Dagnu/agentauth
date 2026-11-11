"""
CBN Nigeria Policy Templates.

Natural language policy rule sets based on directives issued by the
Central Bank of Nigeria (CBN) — the apex bank and financial regulator
of Nigeria.

Templates:
  1. CBN_PAYMENT_AGENT      CBN Payment Systems Directive
  2. CBN_LENDING_AGENT      CBN Credit / Lending Guidelines
  3. CBN_KYC_AGENT          CBN AML/CFT/KYC Regulations
  4. CBN_MOBILE_MONEY       CBN Mobile Money Operations Regulations
  5. CBN_INSURANCE_AGENT    NAICOM / CBN Insurance Directives

These rules are written in plain English so Gemini can reason over them
in context. Each rule corresponds to a real CBN regulatory requirement.
Developers can append overrides to tighten limits for their specific product.

References:
  - CBN website: https://www.cbn.gov.ng
  - CBN regulations: https://www.cbn.gov.ng/Regulations/
  - NIBSS (Nigeria Inter-Bank Settlement System): https://www.nibss-plc.com.ng
"""

from __future__ import annotations

from agentauth.templates.registry import PolicyTemplate, TemplateDefinition, registry

# ── 1. Payment Agent ──────────────────────────────────────────────────────────

registry.register(TemplateDefinition(
    name=PolicyTemplate.CBN_PAYMENT_AGENT,
    display_name="CBN Payment Agent",
    description=(
        "Governs AI agents processing electronic payments, fund transfers, "
        "and instant payments in Nigeria under CBN payment systems regulations "
        "and NIBSS guidelines."
    ),
    regulator="Central Bank of Nigeria (CBN)",
    jurisdiction="Nigeria",
    version="1.0.0",
    tags=["payment", "transfer", "fintech", "nigeria", "cbn", "nibss"],
    references=[
        "CBN Payment Systems Management Guidelines (2019)",
        "CBN Regulation on Electronic Payments and Transfers (2019)",
        "NIBSS Instant Payment (NIP) Operating Rules",
        "CBN Consumer Protection Regulations (2019)",
    ],
    rules=[
        # Transaction limits
        "Agent may not process a single payment transaction exceeding NGN 5,000,000 "
        "without explicit human approval and a second factor authentication.",
        "Agent may not process more than NGN 10,000,000 in cumulative daily outgoing "
        "transfers from a single account without escalating for human review.",
        "Agent may not process international transfers exceeding USD 10,000 equivalent "
        "without CBN-approved FX documentation.",

        # KYC and account validation
        "Agent must verify that the sender's account has completed Tier 2 KYC "
        "(BVN verified) before processing any transfer above NGN 50,000.",
        "Agent must reject transactions from accounts flagged as Post-No-Debit (PND) "
        "or under regulatory/CBN hold.",
        "Agent must validate the recipient's Bank Verification Number (BVN) and "
        "confirm the account is active before initiating any transfer.",

        # NIBSS and settlement
        "Agent may only route inter-bank transfers through NIBSS-approved channels: "
        "NIP (Instant), NEFT, or NAPS during CBN-approved settlement windows.",
        "Agent must complete NIP transfers within 10 seconds of authorisation or "
        "escalate to the payment operations team.",

        # AML / sanctions
        "Agent must screen all parties against the Nigerian Financial Intelligence "
        "Centre (NFIC) watchlist and CBN sanctions list before processing.",
        "Agent must flag and escalate any transaction that matches structuring, "
        "smurfing, or layering patterns for human AML review.",
        "Agent must not process payments to or from countries on the FATF "
        "high-risk and non-cooperative jurisdictions list.",

        # BVN (Bank Verification Number) compliance
        "Agent must verify the BVN of the sender for any transaction above "
        "NGN 1,000,000 and confirm the BVN matches the account holder.",
        "Agent must not process transactions for accounts with mismatched BVN "
        "data — these must be escalated immediately.",

        # Receipts and records
        "Agent must generate and store a transaction receipt for every completed "
        "payment including timestamp, parties, amount, and NIBSS reference number.",
        "Agent must retain all transaction records for a minimum of 7 years "
        "as required by CBN record-keeping regulations.",

        # Error handling
        "Agent must not retry a failed transaction more than 3 times without "
        "notifying the account holder.",
        "Agent must immediately reverse and report any duplicate transaction "
        "detected within the same business day to NIBSS.",
    ],
))

# ── 2. Lending Agent ──────────────────────────────────────────────────────────

registry.register(TemplateDefinition(
    name=PolicyTemplate.CBN_LENDING_AGENT,
    display_name="CBN Lending Agent",
    description=(
        "Governs AI agents involved in credit assessment, loan approval, "
        "and collection under CBN credit and lending guidelines. "
        "Covers microfinance, digital lending, and consumer credit."
    ),
    regulator="Central Bank of Nigeria (CBN)",
    jurisdiction="Nigeria",
    version="1.0.0",
    tags=["lending", "credit", "loan", "microfinance", "nigeria", "cbn"],
    references=[
        "CBN Consumer Credit Regulations",
        "CBN Microfinance Banks Guidelines (2012)",
        "CBN Digital Lending Guidelines",
        "CBN Credit Risk Management Directive",
    ],
    rules=[
        # Credit assessment
        "Agent must perform a creditworthiness assessment using CBN-approved "
        "criteria before recommending any loan approval.",
        "Agent must check the Credit Bureau (CRC, CreditRegistry, or CRIF) for the "
        "applicant's credit history before processing any loan above NGN 100,000.",
        "Agent may not approve a loan to a borrower who has a non-performing loan "
        "at any CBN-licensed institution.",

        # Loan limits and collateral
        "Agent may not approve an unsecured loan exceeding NGN 2,000,000 to "
        "an individual borrower without senior credit officer approval.",
        "Agent must verify that the declared collateral value covers at least "
        "120% of the loan principal before approval.",
        "Agent may not approve a loan where the borrower's debt-to-income ratio "
        "would exceed 33% after the new loan — CBN's threshold for consumer lending.",

        # Interest rates
        "Agent must apply interest rates within the range set by CBN monetary "
        "policy — currently a maximum of MPR + 22% for consumer lending.",
        "Agent must not apply compound interest in a manner that violates CBN "
        "consumer protection guidelines.",
        "Agent must clearly disclose the Annual Percentage Rate (APR), all fees, "
        "and penalty charges to the borrower before loan disbursement, per CBN "
        "consumer protection rules.",

        # Disbursement and collections
        "Agent may only disburse loan funds to the verified bank account of "
        "the borrower — third-party disbursements require escalation.",
        "Agent must not initiate any collection action before the loan is "
        "30 days past due, in compliance with CBN fair lending practices.",
        "Agent must escalate any loan that becomes 90 days past due for "
        "NPL classification and provisioning.",

        # Digital lending specific
        "Agent must not deduct more than one-third of the borrower's net monthly "
        "income as loan repayment — CBN's maximum deduction limit.",
        "Agent must not disburse loans without explicit, documented borrower "
        "consent — auto-debit authorisation must be verified.",

        # Reporting
        "Agent must report all new loans above NGN 5,000,000 to the Credit "
        "Bureau within 5 business days of disbursement.",
        "Agent must generate monthly loan portfolio quality reports for "
        "submission to CBN by the 10th of each month.",
    ],
))

# ── 3. KYC / AML Agent ────────────────────────────────────────────────────────

registry.register(TemplateDefinition(
    name=PolicyTemplate.CBN_KYC_AGENT,
    display_name="CBN KYC / AML Agent",
    description=(
        "Governs AI agents performing customer identity verification, "
        "due diligence, and anti-money laundering screening under CBN "
        "AML/CFT/KYC Regulations and FATF recommendations."
    ),
    regulator="Central Bank of Nigeria (CBN)",
    jurisdiction="Nigeria",
    version="1.0.0",
    tags=["kyc", "aml", "identity", "compliance", "nigeria", "cbn", "bvn"],
    references=[
        "CBN AML/CFT/CPF Regulations (2022)",
        "CBN Customer Due Diligence (CDD) Regulations",
        "Nigerian Financial Intelligence Centre (NFIC) Guidelines",
        "FATF 40 Recommendations",
    ],
    rules=[
        # Tiered KYC (CBN's three-tier framework)
        "Agent may onboard a Tier 1 customer (maximum balance NGN 50,000, "
        "cumulative daily transfer NGN 20,000) using a phone number, email, "
        "and self-declared name only.",
        "Agent must collect and verify a BVN (Bank Verification Number) and "
        "valid government-issued ID for Tier 2 onboarding (maximum balance "
        "NGN 400,000, cumulative daily transfer NGN 200,000).",
        "Agent must collect proof of address (utility bill), BVN, valid ID, "
        "and source-of-funds declaration for Tier 3 onboarding (no limit) — "
        "full CDD required.",

        # BVN (Bank Verification Number)
        "Agent must verify every customer's BVN against the NIBSS BVN database "
        "before completing Tier 2 or Tier 3 onboarding.",
        "Agent must reject onboarding if the BVN provided does not match the "
        "declared name and date of birth of the customer.",

        # Enhanced Due Diligence (EDD)
        "Agent must apply Enhanced Due Diligence (EDD) to all Politically "
        "Exposed Persons (PEPs), their immediate family, and close associates.",
        "Agent must escalate all PEP onboarding requests for senior compliance "
        "officer approval — agent may not onboard PEPs autonomously.",
        "Agent must apply EDD to customers from FATF high-risk jurisdictions, "
        "including documenting the business rationale for the relationship.",

        # Sanctions screening
        "Agent must screen every new customer against the NFIC watchlist, "
        "UN Security Council sanctions list, and OFAC SDN list.",
        "Agent must re-screen all existing customers against updated sanctions "
        "lists at least once every 30 days.",
        "Agent must immediately freeze any account that matches a sanctions "
        "list entry and escalate to the compliance officer within 1 hour.",

        # Transaction monitoring and STR/CTR
        "Agent must flag cash transactions above NGN 5,000,000 for individuals "
        "or NGN 10,000,000 for corporates as a Suspicious Transaction Report "
        "(STR) trigger for human review.",
        "Agent must flag any customer whose transaction volume increases by "
        "more than 200% month-over-month for review.",
        "Agent must escalate all transactions with no plausible business "
        "purpose or inconsistent with the customer's known profile.",
        "Agent must file Currency Transaction Reports (CTRs) for cash "
        "transactions above NGN 5,000,000 within 7 days.",

        # Data and records
        "Agent must retain all KYC documents, verification records, and "
        "transaction monitoring logs for a minimum of 7 years after the "
        "customer relationship ends.",
        "Agent must not share customer identity data with third parties "
        "without explicit CBN authorization or court order.",
    ],
))

# ── 4. Mobile Money Agent ────────────────────────────────────────────────────

registry.register(TemplateDefinition(
    name=PolicyTemplate.CBN_MOBILE_MONEY,
    display_name="CBN Mobile Money Agent",
    description=(
        "Governs AI agents operating within mobile money and mobile payment "
        "platforms in Nigeria under CBN Mobile Money Operations Regulations. "
        "Covers wallet management, agent networks, USSD, and fraud prevention."
    ),
    regulator="Central Bank of Nigeria (CBN)",
    jurisdiction="Nigeria",
    version="1.0.0",
    tags=["mobile money", "mobile payment", "fintech", "nigeria", "cbn", "ussd", "wallet"],
    references=[
        "CBN Mobile Money Operations Regulations (2015)",
        "CBN Guidelines for Mobile Money Operations",
        "CBN Agent Banking Guidelines",
        "CBN Cyber Security Regulations",
    ],
    rules=[
        # Wallet limits (CBN mobile money tiering)
        "Agent may not allow a Tier 1 mobile money wallet to hold more than "
        "NGN 50,000 at any time or process cumulative daily transactions "
        "above NGN 20,000.",
        "Agent may not allow a Tier 2 wallet (BVN verified) to hold more than "
        "NGN 400,000 or process cumulative daily transactions above NGN 200,000.",
        "Agent must enforce Tier 3 wallet limits per CBN regulations — "
        "no wallet may exceed NGN 5,000,000 in balance.",

        # Authentication
        "Agent must enforce PIN-based authentication for all mobile money "
        "transactions above NGN 1,000.",
        "Agent must require OTP verification for any single transaction "
        "above NGN 50,000.",
        "Agent must lock the mobile money wallet after 5 consecutive failed "
        "PIN attempts and require a branch or agent network unlock.",
        "Agent must enforce a 10-minute session timeout for all mobile money "
        "sessions with no activity.",

        # Agent network (mobile money agents)
        "Agent must verify that a mobile money agent has completed CBN-approved "
        "agent banking training before processing cash-in or cash-out transactions.",
        "Agent must not allow a single mobile money agent to process more than "
        "NGN 500,000 in cumulative daily cash-in/cash-out transactions without "
        "escalation.",

        # USSD and channel security
        "Agent must enforce per-transaction limits on USSD channels: a maximum "
        "of NGN 100,000 per transaction and NGN 500,000 cumulative daily.",
        "Agent must block any USSD session that uses an unregistered phone "
        "number and escalate for SIM-to-account verification.",

        # Fraud detection
        "Agent must flag and block any mobile money transaction initiated from "
        "a device or phone number flagged as high-risk in the fraud system.",
        "Agent must detect and block SIM-swap fraud: transactions initiated "
        "within 24 hours of a SIM change must require additional identity "
        "verification via BVN or OTP.",
        "Agent must flag multiple failed transaction attempts followed by "
        "a successful one as a potential brute-force attack indicator.",

        # Customer protection
        "Agent must send an SMS confirmation to the customer's registered "
        "phone number for every mobile money transaction above NGN 500.",
        "Agent must not store the customer's full PIN in any device storage, "
        "USSD log, or application log — PINs must be hashed.",
        "Agent must provide a 10-minute cooling-off period for first-time "
        "transfers to a new beneficiary above NGN 10,000.",

        # NIBSS and settlement
        "Agent must settle all mobile money transactions through the NIBSS "
        "mobile money settlement platform within 24 hours.",
        "Agent must retain all mobile money transaction logs including "
        "phone number, USSD code, and transaction details for 7 years.",
    ],
))

# ── 5. Insurance Agent ────────────────────────────────────────────────────────

registry.register(TemplateDefinition(
    name=PolicyTemplate.CBN_INSURANCE_AGENT,
    display_name="CBN Insurance Agent",
    description=(
        "Governs AI agents operating in the Nigerian insurance sector under "
        "NAICOM (National Insurance Commission) and CBN directives. "
        "Covers policy issuance, claims processing, premium handling, and "
        "consumer protection."
    ),
    regulator="National Insurance Commission (NAICOM) / CBN",
    jurisdiction="Nigeria",
    version="1.0.0",
    tags=["insurance", "claims", "premium", "nigeria", "cbn", "naicom"],
    references=[
        "Insurance Act 2003 and Amendments",
        "NAICOM Guidelines on Insurance Operations",
        "NAICOM Claims Settlement Policy",
        "CBN Consumer Protection Regulations (2019)",
    ],
    rules=[
        # Policy issuance
        "Agent may only issue insurance policies for products registered with "
        "NAICOM — no unapproved or unregistered products.",
        "Agent must verify the customer's identity (Tier 2 KYC minimum: BVN "
        "and valid government-issued ID) before issuing any insurance policy.",
        "Agent must clearly disclose all policy terms, exclusions, premium "
        "amounts, and claim procedures to the customer before issuance.",
        "Agent may not issue a life insurance policy with a sum assured above "
        "NGN 10,000,000 without underwriting officer approval.",

        # Premium collection
        "Agent must issue an official receipt for every premium payment "
        "collected, referencing the policy number and coverage period.",
        "Agent must not use premium funds collected for any purpose other "
        "than remitting to the insurer within 2 business days.",
        "Agent must escalate any premium refund request above NGN 200,000 "
        "for finance officer approval before processing.",

        # Claims processing
        "Agent may process and approve straightforward claims up to NGN 50,000 "
        "where the loss event is documented and the policy is in force.",
        "Agent must escalate all claims above NGN 50,000 or any claim involving "
        "bodily injury, death, or third-party liability to a licensed claims "
        "adjuster.",
        "Agent must not deny a claim without providing the customer with a "
        "written reason and their right to appeal within 15 days, per NAICOM "
        "claims settlement policy.",
        "Agent must complete initial claims acknowledgment within 7 days of "
        "a claim being filed, as required by NAICOM consumer protection rules.",

        # Reserves and solvency
        "Agent must flag any situation where claim payments would cause the "
        "insurer's solvency margin to fall below the NAICOM minimum "
        "requirements and escalate immediately.",

        # Anti-fraud
        "Agent must flag duplicate claims, inconsistent loss narratives, or "
        "claims filed suspiciously close to policy inception for fraud review.",
        "Agent must screen claimants and beneficiaries against the Nigerian "
        "Insurance Fraud Database before processing any claim above NGN 25,000.",

        # Records
        "Agent must retain all policy documents, premium receipts, and "
        "claims records for a minimum of 7 years as required by the "
        "Insurance Act and NAICOM regulations.",
    ],
))
