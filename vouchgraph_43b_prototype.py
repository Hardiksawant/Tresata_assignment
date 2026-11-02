"""
VouchGraph-43B: Neuro-Symbolic Entity Resolution & Deterministic Tax Audit Prototype
Author: Hardik Sawant (EP22B048, IIT Madras)
Target Jurisdiction: India — Income Tax Act, 1961 (Sec 43B(h), Form 3CD Clause 22) & MSMED Act, 2006 (Sec 15, 16, 23)
Transition Ready: Income Tax Act, 2025 (Form 26 Unified Tax Audit Schedule)
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional, List, Dict, Tuple
import json
import re

# ==============================================================================
# 1. VERSIONED STATUTORY RULES CONFIG (Knowledge-in-Code, Never in LLM Weights)
# ==============================================================================
STATUTORY_RULES_V2026 = {
    "rule_version": "CBDT-Form3CD-Cl22-FY2025-26-v2.4",
    "fy_start": date(2025, 4, 1),
    "fy_end": date(2026, 3, 31),
    "rbi_bank_rate_annual": 0.0675,  # 6.75% RBI Bank Rate -> 3x = 20.25% p.a. under Sec 16 MSMED Act
    "msme_multiplier": 3.0,
    "default_no_agreement_days": 15,
    "max_written_agreement_days": 45,
    "objection_window_days": 15,
    "eligible_tiers": {"MICRO", "SMALL"},
    "eligible_activities": {"MANUFACTURING", "SERVICES"},
    "excluded_nic_prefixes": {"45", "46", "47"},  # OM No. 5/2(2)/2021-E/P & G/Policy (Wholesale/Retail Trade excluded)
    "confidence_gate_threshold": 0.88,
}

# ==============================================================================
# 2. DATA CONTRACTS (Strict Boundary Between Probabilistic AI & Audit Kernel)
# ==============================================================================
@dataclass
class ProvenanceSpan:
    doc_id: str
    field_name: str
    extracted_value: str
    page_num: int
    char_span: Tuple[int, int]
    verbatim_quote: str
    confidence: float

@dataclass
class ExtractedVoucherPacket:
    case_id: str
    vendor_name_invoice: str
    vendor_name_erp: str
    gstin: str
    udyam_reg_no: Optional[str]
    enterprise_tier: Optional[str]       # MICRO, SMALL, MEDIUM, NON_MSME
    major_activity: Optional[str]        # MANUFACTURING, SERVICES, TRADING
    nic_2digit: Optional[str]            # e.g., "25", "62", "46"
    has_written_agreement: bool
    agreed_credit_days: Optional[int]
    invoice_date: date
    delivery_date: Optional[date]
    objection_raised_date: Optional[date]
    objection_resolved_date: Optional[date]
    actual_payment_date: Optional[date]  # None if unpaid as of audit cutoff
    base_amount_inr: float
    gst_amount_inr: float
    itc_claimed_in_gstr3b: bool
    min_extraction_confidence: float
    provenance_log: List[ProvenanceSpan] = field(default_factory=list)
    notes: str = ""

@dataclass
class AuditDecisionRecord:
    case_id: str
    statutory_status: str                # EXEMPT_TRADER, EXEMPT_MEDIUM, COMPLIANT_ON_TIME, LATE_PAID_IN_FY_INT_ONLY, DISALLOWED_43BH, ESCALATED_HITL
    day_of_acceptance: Optional[date]
    statutory_credit_days: int
    sec15_due_date: Optional[date]
    days_delayed: int
    principal_disallowed_43bh_inr: float
    sec23_inadmissible_interest_inr: float
    clause_22_bucket: str
    human_review_required: bool
    escalation_reason: Optional[str]
    rule_trace: List[str]

# ==============================================================================
# 3. PROBABILISTIC EXTRACTION & ENTITY RESOLUTION SIMULATOR (LLM + OCR + RAG)
# ==============================================================================
class ProbabilisticExtractionAgent:
    """
    Simulates the LLM + Layout-Aware OCR extraction layer over raw PDF Invoices,
    Udyam Certificates, MSAs, and QA Objection Emails.
    In production (and tested via OpenRouter Qwen-2.5-72B-Instruct / Llama-3.3-70B),
    this agent emits JSON adhering strictly to ExtractedVoucherPacket with span citations.
    """
    UDYAM_REGEX = re.compile(r"UDYAM-[A-Z]{2}-\d{2}-\d{7}")

    @staticmethod
    def validate_and_gate(packet: ExtractedVoucherPacket, rules: dict) -> Tuple[bool, Optional[str]]:
        # 1. Confidence threshold check
        if packet.min_extraction_confidence < rules["confidence_gate_threshold"]:
            return False, f"Low extraction confidence ({packet.min_extraction_confidence:.2f} < {rules['confidence_gate_threshold']})"
        # 2. Udyam regex sanity check if Udyam is claimed
        if packet.udyam_reg_no and not ProbabilisticExtractionAgent.UDYAM_REGEX.match(packet.udyam_reg_no):
            return False, f"Malformed Udyam Registration ID ({packet.udyam_reg_no})"
        # 3. Missing delivery/acceptance date check
        if packet.delivery_date is None:
            return False, "Missing GRN/Delivery Date and unreadable invoice dispatch timestamp"
        # 4. Contradictory objection dates
        if packet.objection_raised_date and packet.objection_resolved_date is None:
            return False, "Open/unresolved QA objection without resolution date in email thread"
        return True, None

# ==============================================================================
# 4. DETERMINISTIC STATUTORY CALCULATOR (Zero-Hallucination Audit Kernel)
# ==============================================================================
class DeterministicAuditKernel:
    """
    Pure symbolic engine implementing Section 43B(h) of the Income Tax Act, 1961
    and Sections 15, 16, and 23 of the MSMED Act, 2006.
    """
    @staticmethod
    def evaluate(packet: ExtractedVoucherPacket, rules: dict = STATUTORY_RULES_V2026) -> AuditDecisionRecord:
        trace = [f"Loaded rule-pack: {rules['rule_version']}"]

        # Step 0: Epistemic Uncertainty Gate (Route to Human-in-the-Loop if extraction is uncertain)
        passed_gate, gate_reason = ProbabilisticExtractionAgent.validate_and_gate(packet, rules)
        if not passed_gate:
            trace.append(f"GATE_REJECT: {gate_reason} -> Routed to CA Audit Workqueue.")
            return AuditDecisionRecord(
                case_id=packet.case_id,
                statutory_status="ESCALATED_HITL",
                day_of_acceptance=packet.delivery_date,
                statutory_credit_days=0,
                sec15_due_date=None,
                days_delayed=0,
                principal_disallowed_43bh_inr=0.0,
                sec23_inadmissible_interest_inr=0.0,
                clause_22_bucket="PENDING_CA_VERIFICATION",
                human_review_required=True,
                escalation_reason=gate_reason,
                rule_trace=trace
            )

        # Step 1: Verify MSE Eligibility (Tier + Major Activity + NIC Trader Carve-Out)
        if packet.enterprise_tier not in rules["eligible_tiers"]:
            trace.append(f"Tier={packet.enterprise_tier} not in {rules['eligible_tiers']} -> Outside Sec 43B(h).")
            return AuditDecisionRecord(
                case_id=packet.case_id,
                statutory_status="EXEMPT_MEDIUM_OR_NON_MSME",
                day_of_acceptance=packet.delivery_date,
                statutory_credit_days=0,
                sec15_due_date=None,
                days_delayed=0,
                principal_disallowed_43bh_inr=0.0,
                sec23_inadmissible_interest_inr=0.0,
                clause_22_bucket="NOT_APPLICABLE",
                human_review_required=False,
                escalation_reason=None,
                rule_trace=trace
            )

        if packet.major_activity == "TRADING" or (packet.nic_2digit and packet.nic_2digit in rules["excluded_nic_prefixes"]):
            trace.append(f"Activity={packet.major_activity}, NIC={packet.nic_2digit} -> Excluded Trader per MSME OM 02-Jul-2021.")
            return AuditDecisionRecord(
                case_id=packet.case_id,
                statutory_status="EXEMPT_TRADER_OM2021",
                day_of_acceptance=packet.delivery_date,
                statutory_credit_days=0,
                sec15_due_date=None,
                days_delayed=0,
                principal_disallowed_43bh_inr=0.0,
                sec23_inadmissible_interest_inr=0.0,
                clause_22_bucket="EXEMPT_TRADER_PSL_ONLY",
                human_review_required=False,
                escalation_reason=None,
                rule_trace=trace
            )

        # Step 2: Compute Legal "Day of Acceptance" under Sec 15 Explanation (i)
        day_of_acceptance = packet.delivery_date
        if packet.objection_raised_date:
            days_to_objection = (packet.objection_raised_date - packet.delivery_date).days
            if 0 <= days_to_objection <= rules["objection_window_days"]:
                day_of_acceptance = packet.objection_resolved_date
                trace.append(f"Valid written objection raised in {days_to_objection}d (<=15d) -> Day of Acceptance shifted to resolution date {day_of_acceptance}.")
            else:
                trace.append(f"Objection raised after {days_to_objection}d (>15d statutory window) -> Deemed acceptance remains {day_of_acceptance}.")

        # Step 3: Compute Statutory Credit Period (15d without written agreement; min(agreed, 45d) with agreement)
        if packet.has_written_agreement and packet.agreed_credit_days is not None:
            statutory_days = min(packet.agreed_credit_days, rules["max_written_agreement_days"])
            trace.append(f"Written MSA present (agreed={packet.agreed_credit_days}d) -> Capped at statutory {statutory_days}d under Sec 15.")
        else:
            statutory_days = rules["default_no_agreement_days"]
            trace.append(f"No written agreement -> Statutory window fixed at {statutory_days}d under Sec 15.")

        sec15_due_date = day_of_acceptance + timedelta(days=statutory_days)
        trace.append(f"Sec 15 Statutory Due Date = {sec15_due_date.isoformat()}.")

        # Step 4: Determine GST ITC Carve-Out for Disallowance Base
        gross_amount = packet.base_amount_inr + packet.gst_amount_inr
        disallowable_base = packet.base_amount_inr if packet.itc_claimed_in_gstr3b else gross_amount
        trace.append(f"ITC Claimed={packet.itc_claimed_in_gstr3b} -> Disallowable principal base = INR {disallowable_base:,.2f}.")

        # Step 5: Evaluate Payment Timing vs. Sec 15 Due Date and FY End (31-Mar-2026)
        fy_end = rules["fy_end"]
        annual_penal_rate = rules["rbi_bank_rate_annual"] * rules["msme_multiplier"]  # 20.25%

        # Case A: Paid on or before Section 15 Due Date
        if packet.actual_payment_date and packet.actual_payment_date <= sec15_due_date:
            trace.append(f"Paid on {packet.actual_payment_date} (<= Due Date {sec15_due_date}) -> Fully deductible in FY 2025-26.")
            return AuditDecisionRecord(
                case_id=packet.case_id,
                statutory_status="COMPLIANT_ON_TIME",
                day_of_acceptance=day_of_acceptance,
                statutory_credit_days=statutory_days,
                sec15_due_date=sec15_due_date,
                days_delayed=0,
                principal_disallowed_43bh_inr=0.0,
                sec23_inadmissible_interest_inr=0.0,
                clause_22_bucket="Cl.22(ii)_PAID_WITHIN_SEC15",
                human_review_required=False,
                escalation_reason=None,
                rule_trace=trace
            )

        # Case B: Paid late, but actual payment completed WITHIN the same FY (on or before 31-Mar-2026)
        if packet.actual_payment_date and packet.actual_payment_date <= fy_end and packet.actual_payment_date > sec15_due_date:
            days_delayed = (packet.actual_payment_date - sec15_due_date).days
            # Monthly compounding approximation or exact daily accrual for Sec 16 interest on gross amount
            months_delayed = max(1, (days_delayed + 29) // 30)
            penal_interest = round(gross_amount * ((1 + annual_penal_rate / 12) ** months_delayed - 1), 2)
            trace.append(
                f"Paid {days_delayed}d late on {packet.actual_payment_date}, but WITHIN FY25-26 -> "
                f"Principal deductible on actual-payment basis; reported under Cl.22(iii)(b) & Sec 23 interest INR {penal_interest:,.2f} disallowed."
            )
            return AuditDecisionRecord(
                case_id=packet.case_id,
                statutory_status="LATE_PAID_IN_FY_INT_ONLY",
                day_of_acceptance=day_of_acceptance,
                statutory_credit_days=statutory_days,
                sec15_due_date=sec15_due_date,
                days_delayed=days_delayed,
                principal_disallowed_43bh_inr=0.0,
                sec23_inadmissible_interest_inr=penal_interest,
                clause_22_bucket="Cl.22(iii)(b)_LATE_PAID_IN_FY_SEC23_INT",
                human_review_required=False,
                escalation_reason=None,
                rule_trace=trace
            )

        # Case C: Unpaid at FY End (31-Mar-2026) OR Paid in Next FY AFTER Sec 15 Due Date
        ref_date = min(packet.actual_payment_date, fy_end) if packet.actual_payment_date and packet.actual_payment_date <= fy_end else fy_end
        days_delayed = max(1, (ref_date - min(sec15_due_date, fy_end)).days)
        months_delayed = max(1, (days_delayed + 29) // 30)
        penal_interest = round(gross_amount * ((1 + annual_penal_rate / 12) ** months_delayed - 1), 2)
        trace.append(
            f"Unpaid as of FY-end or paid in next FY after Sec 15 deadline ({sec15_due_date}) -> "
            f"100% Principal Disallowance under Sec 43B(h) = INR {disallowable_base:,.2f} + Sec 23 Interest = INR {penal_interest:,.2f}."
        )
        return AuditDecisionRecord(
            case_id=packet.case_id,
            statutory_status="DISALLOWED_43BH",
            day_of_acceptance=day_of_acceptance,
            statutory_credit_days=statutory_days,
            sec15_due_date=sec15_due_date,
            days_delayed=days_delayed,
            principal_disallowed_43bh_inr=disallowable_base,
            sec23_inadmissible_interest_inr=penal_interest,
            clause_22_bucket="Cl.22(iii)(b)_AND_CL26_SEC43BH_DISALLOWED",
            human_review_required=True,  # Statutory disallowance requires CA sign-off
            escalation_reason="Material tax disallowance under Sec 43B(h) — requires CA Form 3CD sign-off",
            rule_trace=trace
        )

# ==============================================================================
# 5. SYNTHETIC BENCHMARK SUITE (12 Realistic B2B Procurement Scenarios)
# ==============================================================================
def build_test_suite() -> List[Tuple[ExtractedVoucherPacket, str, str]]:
    """
    Returns (Packet, Expected_Ground_Truth_Status, Failure_Mode_Analysis_Note)
    Note: Cases 10 and 11 simulate real upstream extraction/OCR failure modes to
    demonstrate how the system fails and where the epistemic gate catches vs misses them.
    """
    return [
        # C01: Standard Micro Manufacturer, 60-day MSA capped to 45d, unpaid on Mar 31 -> Disallowed (Base only, ITC claimed)
        (ExtractedVoucherPacket(
            case_id="C01", vendor_name_invoice="Shree Balaji Precision Tools Pvt Ltd", vendor_name_erp="S.B. Precision Tools",
            gstin="27AABCS1429B1Z1", udyam_reg_no="UDYAM-MH-19-0041829", enterprise_tier="MICRO", major_activity="MANUFACTURING",
            nic_2digit="25", has_written_agreement=True, agreed_credit_days=60,
            invoice_date=date(2026, 1, 20), delivery_date=date(2026, 1, 22), objection_raised_date=None, objection_resolved_date=None,
            actual_payment_date=date(2026, 4, 18), base_amount_inr=1_200_000, gst_amount_inr=216_000, itc_claimed_in_gstr3b=True,
            min_extraction_confidence=0.96, notes="60d MSA overridden by 45d Sec 15 cap; paid in April -> Sec 43B(h) disallowance on base INR 12L."
        ), "DISALLOWED_43BH", "PASS"),

        # C02: Small Service Provider, NO written agreement (15d rule), unpaid on Mar 31, GST NOT claimed as ITC -> Gross Disallowed
        (ExtractedVoucherPacket(
            case_id="C02", vendor_name_invoice="Apex CloudSec Auditors LLP", vendor_name_erp="Apex CloudSec",
            gstin="29AAJFA9912K1Z5", udyam_reg_no="UDYAM-KA-03-0192834", enterprise_tier="SMALL", major_activity="SERVICES",
            nic_2digit="62", has_written_agreement=False, agreed_credit_days=None,
            invoice_date=date(2026, 2, 25), delivery_date=date(2026, 2, 25), objection_raised_date=None, objection_resolved_date=None,
            actual_payment_date=None, base_amount_inr=500_000, gst_amount_inr=90_000, itc_claimed_in_gstr3b=False,
            min_extraction_confidence=0.94, notes="No MSA -> 15d limit; blocked ITC -> Full INR 5.90L gross disallowed."
        ), "DISALLOWED_43BH", "PASS"),

        # C03: Wholesale Chemical Trader holding valid Udyam Certificate (NIC 46) -> Exempt under Jul 2021 OM!
        (ExtractedVoucherPacket(
            case_id="C03", vendor_name_invoice="Vardhman Polymer Traders", vendor_name_erp="Vardhman Polymers",
            gstin="24AAACV8821M1Z2", udyam_reg_no="UDYAM-GJ-01-0088123", enterprise_tier="SMALL", major_activity="TRADING",
            nic_2digit="46", has_written_agreement=True, agreed_credit_days=45,
            invoice_date=date(2026, 1, 10), delivery_date=date(2026, 1, 12), objection_raised_date=None, objection_resolved_date=None,
            actual_payment_date=None, base_amount_inr=2_400_000, gst_amount_inr=432_000, itc_claimed_in_gstr3b=True,
            min_extraction_confidence=0.97, notes="ERP flagged MSME=Yes, but Udyam NIC 46 is Wholesale Trade -> Exempt from 43B(h)."
        ), "EXEMPT_TRADER_OM2021", "PASS"),

        # C04: Late payment WITHIN the same FY (Aug invoice paid in Nov) -> Principal allowed, only Sec 23 Interest disallowed!
        (ExtractedVoucherPacket(
            case_id="C04", vendor_name_invoice="Kalyani Die Castings", vendor_name_erp="Kalyani Die Castings",
            gstin="27AAECK4410P1Z8", udyam_reg_no="UDYAM-MH-26-0011223", enterprise_tier="MICRO", major_activity="MANUFACTURING",
            nic_2digit="24", has_written_agreement=True, agreed_credit_days=30,
            invoice_date=date(2025, 8, 1), delivery_date=date(2025, 8, 5), objection_raised_date=None, objection_resolved_date=None,
            actual_payment_date=date(2025, 11, 10), base_amount_inr=800_000, gst_amount_inr=144_000, itc_claimed_in_gstr3b=True,
            min_extraction_confidence=0.95, notes="Paid 67d past Sec 15 due date, but inside FY25-26 -> Principal deductible; Sec 23 interest disallowed."
        ), "LATE_PAID_IN_FY_INT_ONLY", "PASS"),

        # C05: March invoice (20-Mar-2026) with 45d MSA paid on 28-Apr-2026 (within 45d window!) -> Fully Deductible in FY25-26!
        (ExtractedVoucherPacket(
            case_id="C05", vendor_name_invoice="Southern Circuit Boards Pvt Ltd", vendor_name_erp="Southern Circuits",
            gstin="33AABCS7721Q1Z4", udyam_reg_no="UDYAM-TN-02-0055432", enterprise_tier="SMALL", major_activity="MANUFACTURING",
            nic_2digit="26", has_written_agreement=True, agreed_credit_days=45,
            invoice_date=date(2026, 3, 18), delivery_date=date(2026, 3, 20), objection_raised_date=None, objection_resolved_date=None,
            actual_payment_date=date(2026, 4, 28), base_amount_inr=1_500_000, gst_amount_inr=270_000, itc_claimed_in_gstr3b=True,
            min_extraction_confidence=0.98, notes="Cross-year payment on 28-Apr is before 04-May Sec 15 deadline -> Allowed in FY25-26."
        ), "COMPLIANT_ON_TIME", "PASS"),

        # C06: Valid QA Written Objection raised within 10 days -> Resets Day of Acceptance by 25 days -> Paid on time!
        (ExtractedVoucherPacket(
            case_id="C06", vendor_name_invoice="Deccan Valve & Forgings", vendor_name_erp="Deccan Forgings",
            gstin="36AAACD3319H1Z9", udyam_reg_no="UDYAM-TS-07-0033912", enterprise_tier="SMALL", major_activity="MANUFACTURING",
            nic_2digit="28", has_written_agreement=True, agreed_credit_days=45,
            invoice_date=date(2026, 1, 15), delivery_date=date(2026, 1, 18),
            objection_raised_date=date(2026, 1, 28), objection_resolved_date=date(2026, 2, 15),
            actual_payment_date=date(2026, 3, 28), base_amount_inr=950_000, gst_amount_inr=171_000, itc_claimed_in_gstr3b=True,
            min_extraction_confidence=0.92, notes="QA objection raised in 10d (<15d) shifts acceptance to 15-Feb -> Due 01-Apr -> Paid 28-Mar (Compliant)."
        ), "COMPLIANT_ON_TIME", "PASS"),

        # C07: Late QA Objection raised after 22 days (>15d window) -> Deemed acceptance NOT reset -> Unpaid on Mar 31 -> Disallowed!
        (ExtractedVoucherPacket(
            case_id="C07", vendor_name_invoice="Narmada Industrial Packagings", vendor_name_erp="Narmada Packaging",
            gstin="23AAACN9911D1Z1", udyam_reg_no="UDYAM-MP-11-0077129", enterprise_tier="MICRO", major_activity="MANUFACTURING",
            nic_2digit="17", has_written_agreement=True, agreed_credit_days=30,
            invoice_date=date(2026, 1, 25), delivery_date=date(2026, 1, 26),
            objection_raised_date=date(2026, 2, 17), objection_resolved_date=date(2026, 3, 10),
            actual_payment_date=date(2026, 4, 12), base_amount_inr=620_000, gst_amount_inr=111_600, itc_claimed_in_gstr3b=True,
            min_extraction_confidence=0.91, notes="Objection raised 22d after delivery (>15d statutory limit) -> Clock did NOT reset -> Disallowed."
        ), "DISALLOWED_43BH", "PASS"),

        # C08: Medium Enterprise (Upgraded from Small in FY25-26) -> Exempt from Section 43B(h)
        (ExtractedVoucherPacket(
            case_id="C08", vendor_name_invoice="Bharat Heavy Fasteners Ltd", vendor_name_erp="Bharat Fasteners",
            gstin="06AAACB1123F1Z3", udyam_reg_no="UDYAM-HR-05-0019283", enterprise_tier="MEDIUM", major_activity="MANUFACTURING",
            nic_2digit="25", has_written_agreement=True, agreed_credit_days=60,
            invoice_date=date(2026, 1, 19), delivery_date=date(2026, 1, 20), objection_raised_date=None, objection_resolved_date=None,
            actual_payment_date=None, base_amount_inr=3_100_000, gst_amount_inr=558_000, itc_claimed_in_gstr3b=True,
            min_extraction_confidence=0.96, notes="Medium Enterprise under MSMED Act -> Excluded from Sec 43B(h)."
        ), "EXEMPT_MEDIUM_OR_NON_MSME", "PASS"),

        # C09: Smudged rubber-stamp Udyam ID on thermal scan (Confidence 0.64 < 0.88) -> Caught by Epistemic Gate (HITL)
        (ExtractedVoucherPacket(
            case_id="C09", vendor_name_invoice="Sri Sai Baba Engineering Works", vendor_name_erp="Sai Baba Engg",
            gstin="33AAECS5512N1Z7", udyam_reg_no="UDYAM-TN-01-0091823", enterprise_tier="MICRO", major_activity="MANUFACTURING",
            nic_2digit="25", has_written_agreement=False, agreed_credit_days=None,
            invoice_date=date(2026, 3, 2), delivery_date=date(2026, 3, 3), objection_raised_date=None, objection_resolved_date=None,
            actual_payment_date=None, base_amount_inr=410_000, gst_amount_inr=73_800, itc_claimed_in_gstr3b=True,
            min_extraction_confidence=0.64, notes="Faint purple rubber-stamp Udyam number -> Low OCR confidence (0.64) -> Safely abstained to HITL."
        ), "ESCALATED_HITL", "PASS (Safe Abstention)"),

        # C10: Missing GRN delivery date + unresolved email objection -> Caught by Epistemic Gate (HITL)
        (ExtractedVoucherPacket(
            case_id="C10", vendor_name_invoice="Konkan Marine Logistics & Maint.", vendor_name_erp="Konkan Marine",
            gstin="27AAFCK6621E1Z0", udyam_reg_no="UDYAM-MH-33-0029184", enterprise_tier="SMALL", major_activity="SERVICES",
            nic_2digit="52", has_written_agreement=True, agreed_credit_days=30,
            invoice_date=date(2026, 2, 14), delivery_date=date(2026, 2, 14),
            objection_raised_date=date(2026, 2, 20), objection_resolved_date=None,
            actual_payment_date=None, base_amount_inr=780_000, gst_amount_inr=140_400, itc_claimed_in_gstr3b=True,
            min_extraction_confidence=0.90, notes="QA dispute email has no resolution timestamp -> Safely escalated to CA review."
        ), "ESCALATED_HITL", "PASS (Safe Abstention)"),

        # C11: HONEST FAILURE MODE 1 — Composite Trader+Manufacturer Udyam Certificate where LLM extracts only Primary NIC 46 (Trading)
        # even though the invoice is for custom-manufactured CNC brackets (HSN 8466). System falsely exempts as Trader!
        (ExtractedVoucherPacket(
            case_id="C11", vendor_name_invoice="Mehta Industrial Solutions Pvt Ltd", vendor_name_erp="Mehta Ind Solutions",
            gstin="24AABCM7732L1Z6", udyam_reg_no="UDYAM-GJ-04-0061234", enterprise_tier="SMALL",
            major_activity="TRADING",  # <-- LLM extracted header 'Major Activity: Trading' ignoring page-2 NIC 25 manufacturing table!
            nic_2digit="46", has_written_agreement=True, agreed_credit_days=45,
            invoice_date=date(2026, 1, 15), delivery_date=date(2026, 1, 16), objection_raised_date=None, objection_resolved_date=None,
            actual_payment_date=None, base_amount_inr=1_100_000, gst_amount_inr=198_000, itc_claimed_in_gstr3b=True,
            min_extraction_confidence=0.93, notes="FAILURE: Vendor has dual NICs (46 Trading + 25 Manufacturing); LLM read only page-1 'Major Activity: Trading' with high confidence (0.93), causing false exemption on a manufacturing invoice."
        ), "DISALLOWED_43BH", "FAIL (False Negative: Dual-NIC Udyam Header Bias)"),

        # C12: HONEST FAILURE MODE 2 — Vernacular Marathi/Hindi handwritten GRN rejection slip ("Mal parat pathavla / Defective return")
        # missed by English-centric OCR parser, so objection_raised_date=None with 0.89 confidence -> False Disallowance!
        (ExtractedVoucherPacket(
            case_id="C12", vendor_name_invoice="Sahyadri Agro-Tech Components", vendor_name_erp="Sahyadri Agro",
            gstin="27AAICS8812R1Z2", udyam_reg_no="UDYAM-MH-14-0051920", enterprise_tier="MICRO", major_activity="MANUFACTURING",
            nic_2digit="28", has_written_agreement=True, agreed_credit_days=30,
            invoice_date=date(2026, 2, 1), delivery_date=date(2026, 2, 2),
            objection_raised_date=None,  # <-- LLM missed handwritten Marathi rejection note on gate challan!
            objection_resolved_date=None,
            actual_payment_date=date(2026, 3, 29), base_amount_inr=540_000, gst_amount_inr=97_200, itc_claimed_in_gstr3b=True,
            min_extraction_confidence=0.89, notes="FAILURE: Handwritten Marathi gate-return note missed by parser; system treated 29-Mar payment as In-FY Late (Sec 23 interest disallowance) instead of On-Time after replacement delivery."
        ), "COMPLIANT_ON_TIME", "FAIL (False Positive: Handwritten Vernacular Challan Margin Note)"),
    ]

if __name__ == "__main__":
    suite = build_test_suite()
    results = []
    correct = 0
    for packet, expected_status, mode_note in suite:
        decision = DeterministicAuditKernel.evaluate(packet)
        is_match = (decision.statutory_status == expected_status)
        if is_match:
            correct += 1
        results.append({
            "case_id": packet.case_id,
            "vendor": packet.vendor_name_erp,
            "tier_activity": f"{packet.enterprise_tier}/{packet.major_activity}",
            "predicted": decision.statutory_status,
            "expected": expected_status,
            "match": is_match,
            "disallowed_43bh_inr": decision.principal_disallowed_43bh_inr,
            "sec23_interest_inr": decision.sec23_inadmissible_interest_inr,
            "hitl": decision.human_review_required,
            "note": mode_note
        })
    print(f"Executed {len(suite)} test cases | System Accuracy: {correct}/{len(suite)} ({100*correct/len(suite):.1f}%)")
    print(json.dumps(results, indent=2))