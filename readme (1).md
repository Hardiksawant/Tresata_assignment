# VouchGraph-43B: Neuro-Symbolic Entity Resolution & Deterministic Tax Audit Engine

**Author:** Hardik Sawant (`EP22B048` | B.Tech Engineering Physics & M.Tech Electrical Engineering, IIT Madras)  
**Submission:** Tresata Take-Home Assignment (Agentic AI Engineering — FDE & SWE-I Data for Agents)  
**Jurisdiction Covered:** India — Income Tax Act, 1961 (`Section 43B(h)`, `Section 44AB Form 3CD Clauses 22 & 26`) & MSMED Act, 2006 (`Sections 15, 16, 23`); Transition-Ready for Income Tax Act, 2025 (`Form 26` Unified Tax Audit Schedule)

## 1. Overview & Architectural Philosophy

`VouchGraph-43B` solves a high-cost compliance bottleneck in Indian corporate finance: **reconciling unstructured B2B vendor procurement packets (PDF Tax Invoices, Udyam Registration Certificates, signed Master Service Agreements, and GRN/QA dispute emails) against structured ERP Accounts Payable and GSTR-3B Input Tax Credit (ITC) ledgers** to certify statutory MSME payment disallowances under **Section 43B(h)** and **Form 3CD Clause 22**.

Rather than relying on a monolithic LLM prompt to compute dates or tax liabilities, `VouchGraph-43B` enforces a strict **Neuro-Symbolic Epistemic Boundary**:

1. **Probabilistic Extraction & Entity Resolution Layer (`ProbabilisticExtractionAgent`)**:
   - Uses layout-aware OCR and clause-targeted context window budgeting (~74% prompt token reduction by stripping boilerplate legal sections from 60-page MSAs) to extract structured JSON packets (`ExtractedVoucherPacket`).
   - Tested with **OpenRouter free-tier model `qwen/qwen-2.5-72b-instruct:free`** (and `meta-llama/llama-3.3-70b-instruct:free` fallback) for structured JSON extraction with character-span provenance citations (`ProvenanceSpan`).
   - **Strict Constraint**: The LLM *never* computes calendar day counts, statutory deadlines, principal disallowances, or compound interest.
2. **Epistemic Uncertainty Gate (`validate_and_gate`)**:
   - Validates extraction confidence (`min_extraction_confidence >= 0.88`), `UDYAM-XX-00-0000000` regex/GSTIN checksums, delivery/GRN timestamp presence, and QA objection resolution closure.
   - Any ambiguous or low-confidence packet safely abstains (`ESCALATED_HITL`) and routes to the Chartered Accountant (CA) review queue.
3. **Deterministic Statutory Audit Kernel (`DeterministicAuditKernel`)**:
   - Pure Python state machine driven by version-pinned statutory rules (`STATUTORY_RULES_V2026` / `CBDT-Form3CD-Cl22-FY2025-26-v2.4`).
   - Deterministically executes:
     - **Wholesale/Retail Trader Exemption**: Filters out `NIC 45, 46, 47` and `TRADING` activity per Ministry of MSME OM No. `5/2(2)/2021-E/P & G/Policy` (July 2, 2021).
     - **Medium Enterprise Carve-Out**: Filters out `MEDIUM` tier vendors (`Section 43B(h)` applies strictly to `MICRO` and `SMALL` enterprises).
     - **Legal "Day of Acceptance" Shift**: Shifts acceptance date to `objection_resolved_date` if and only if a written quality objection is raised within `15 days` of delivery under Section 15 Explanation (i).
     - **Statutory Credit Window**: `15 days` without a written agreement; `min(agreed_credit_days, 45 days)` with a mutually executed written agreement/MSA.
     - **GST Input Tax Credit (ITC) Carve-Out**: Disallows only `base_amount_inr` if GST is claimed as ITC in `GSTR-3B`; disallows `base_amount_inr + gst_amount_inr` if ITC is blocked (`Section 17(5)`) or expensed to P&L.
     - **Same-FY Late Payment vs. Cross-FY Disallowance Split**: Correctly distinguishes invoices paid late *within* the same fiscal year (100% principal deductible on actual-payment basis under Section 43B, reported under `Form 3CD Clause 22(iii)(b)` with permanent disallowance of **3x RBI Bank Rate = 20.25% p.a.** monthly-compounded penal interest under `Section 23 MSMED Act`) from invoices unpaid at March 31 or paid late in the next fiscal year (100% principal disallowance under `Section 43B(h)` + `Section 23` penal interest).

## 2. How to Run the Prototype

The deterministic audit kernel and the 12-case benchmark suite run out-of-the-box using **Python 3.10+ standard library only** (zero external dependencies or paid API keys required to verify all 12 benchmark cases).

```bash
# Clone the repository
git clone https://github.com/<your-username>/vouchgraph-43b-tresata.git
cd vouchgraph-43b-tresata

# Run the 12-case benchmark suite and print the JSON audit trace
python3 vouchgraph_43b_prototype.py
```

## 3. Summary of the 12 Tested Scenarios (`C01` – `C12`)

| Case ID | Vendor & Scenario Summary | Tier / NIC | Predicted Status | Expected Status | Sec 43B(h) Principal Disallowed (INR) | Sec 23 Penal Interest Disallowed (INR) | Evaluation Outcome |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | :--- |
| **C01** | *S.B. Precision Tools*: 60d MSA capped to 45d; Jan delivery paid Apr 18; ITC claimed | `MICRO` / `Mfg (25)` | `DISALLOWED_43BH` | `DISALLOWED_43BH` | 12,00,000.00 | 23,895.00 | **PASS** (CA Sign-Off) |
| **C02** | *Apex CloudSec*: No written MSA (15d rule); Feb invoice unpaid Mar 31; ITC blocked | `SMALL` / `Svc (62)` | `DISALLOWED_43BH` | `DISALLOWED_43BH` | 5,90,000.00 | 9,956.25 | **PASS** (CA Sign-Off) |
| **C03** | *Vardhman Polymers*: ERP flags MSME=Yes, but Udyam Cert is Wholesale Trade | `SMALL` / `Trade (46)` | `EXEMPT_TRADER_OM2021` | `EXEMPT_TRADER_OM2021` | 0.00 | 0.00 | **PASS** |
| **C04** | *Kalyani Die Castings*: Aug invoice paid 67d late in Nov (within FY25-26) | `MICRO` / `Mfg (24)` | `LATE_PAID_IN_FY_INT_ONLY` | `LATE_PAID_IN_FY_INT_ONLY` | 0.00 | 48,600.99 | **PASS** |
| **C05** | *Southern Circuits*: Mar 20 delivery (45d MSA) paid Apr 28 (within 45d Sec 15 window) | `SMALL` / `Mfg (26)` | `COMPLIANT_ON_TIME` | `COMPLIANT_ON_TIME` | 0.00 | 0.00 | **PASS** |
| **C06** | *Deccan Forgings*: Written QA objection in 10d (<=15d) shifts acceptance to Feb 15; paid Mar 28 | `SMALL` / `Mfg (28)` | `COMPLIANT_ON_TIME` | `COMPLIANT_ON_TIME` | 0.00 | 0.00 | **PASS** |
| **C07** | *Narmada Packaging*: QA objection raised after 22d (>15d window); clock not reset; paid Apr 12 | `MICRO` / `Mfg (17)` | `DISALLOWED_43BH` | `DISALLOWED_43BH` | 6,20,000.00 | 24,899.83 | **PASS** (CA Sign-Off) |
| **C08** | *Bharat Fasteners*: Graduated from Small to Medium tier in Udyam annexure | `MEDIUM` / `Mfg (25)` | `EXEMPT_MEDIUM_OR_NON_MSME` | `EXEMPT_MEDIUM_OR_NON_MSME` | 0.00 | 0.00 | **PASS** |
| **C09** | *Sai Baba Engg*: Smudged purple rubber-stamp Udyam ID on thermal scan (`conf = 0.64`) | `MICRO` / `Mfg (25)` | `ESCALATED_HITL` | `ESCALATED_HITL` | 0.00 | 0.00 | **PASS** (Safe Abstention) |
| **C10** | *Konkan Marine*: QA dispute email thread has no resolution date (`objection_resolved_date=None`) | `SMALL` / `Svc (52)` | `ESCALATED_HITL` | `ESCALATED_HITL` | 0.00 | 0.00 | **PASS** (Safe Abstention) |
| **C11** | *Mehta Ind Solutions*: Dual-NIC Udyam (Pg1 Trading NIC 46, Pg2 Mfg NIC 25); CNC bracket invoice | `SMALL` / `Dual (46/25)` | `EXEMPT_TRADER_OM2021` | `DISALLOWED_43BH` | 0.00 *(Missed 11L)* | 0.00 | **FAIL (False Negative)** |
| **C12** | *Sahyadri Agro*: Handwritten Marathi gate-return note (*"Mal parat pathavla"*) missed on challan | `MICRO` / `Mfg (28)` | `LATE_PAID_IN_FY_INT_ONLY` | `COMPLIANT_ON_TIME` | 0.00 | 10,752.75 *(False)* | **FAIL (False Positive)** |

### Where It Fails Honestly (`C11` & `C12`)
- **System Score**: `10 / 12 (83.3%)` end-to-end accuracy (`100%` arithmetic precision on valid extractions; `2/2` noisy/incomplete packets safely routed to HITL; `2` upstream semantic extraction failures).
- **Failure Mode 1 (`C11` — Dual-NIC Udyam Header Bias)**: When a supplier holds a composite Udyam certificate listing `"Major Activity: Trading"` on Page 1 (`NIC 46`) but manufactures custom CNC components under a secondary `NIC 25` table on Page 2, extracting only the Page-1 summary (`conf = 0.93`) causes a false trader exemption. **Remediation**: Enforce line-item invoice `HSN/SAC` to full Udyam `NIC` array cross-matching inside the Epistemic Gate.
- **Failure Mode 2 (`C12` — Vernacular Handwritten Challan Margin Note)**: When a factory storekeeper writes a vernacular Marathi quality rejection note in pen on the delivery challan margin, English-centric OCR misses the annotation (`objection_raised_date = None`, `conf = 0.89`), resulting in a false Section 23 interest disallowance. **Remediation**: Add a lightweight VLM ink-annotation detector on GRN scan margins to force `ESCALATED_HITL` review.
