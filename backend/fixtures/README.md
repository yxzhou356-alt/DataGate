# Customer reviews with PII

Updated 2026-10-18 by explicit human request. Each CSV contains 18 short customer reviews. This revision rewrites every message, including the first 10 rows, as a product/service opinion with PII in its context. All ticket IDs and non-message columns are preserved. The schema remains `ticket_id,customer_name,email,phone,plan_tier,account_value,product_area,message`.

Reviews describe ease of use, product value, billing, customer service, reports, search, sharing and mobile reliability. They express likes/dislikes and the effect on the customer, rather than listing error logs or identifiers alone. Every review includes at least one PII-like detail. Related details are combined where they fit: names/contact channels, DOB/SSN, license/national ID, card/bank account, and device/network/user identifiers. Each message is one CSV record, has no embedded newline, and is at most 86 characters before redaction. Actual displayed line counts depend on viewport and rendering; desktop and 390px review-card checks are recorded below.

## Coverage

| Context | MapleCo | RiverCo | Details in message |
| --- | --- | --- | --- |
| Useful product, slow customer service | MA-1101 | RC-2101 | Name, email, phone |
| Liked features, disappointing invoicing | MA-1102 | RC-2102 | Street, apartment/unit, city, state, ZIP |
| Positive features, frustrating identity checks | MA-1103 | RC-2103 | Date of birth and SSN-shaped value |
| Product value offset by upgrade friction | MA-1104 | RC-2104 | Passport number |
| Usability versus signup experience | MA-1105 | RC-2105 | Driver-license number and national ID |
| Poor refund / billing experience | MA-1106 | RC-2106 | Credit-card number and bank-account number |
| Speed versus upload / sharing reliability | MA-1107 | RC-2107 | IPv4, device ID, user ID |
| Liked desktop/editor, unreliable sync | MA-1108 | RC-2108 | IPv6 and user/device context |

The other 10 rows likewise combine customer opinions with names, contact channels or addresses, including the retained Unicode review. The fixed summarization instruction and message-only outbound format are unchanged; these opinions give a summary actual product strengths and customer pain points to extract.

## Provenance and detector limits

These records were authored for this repository and are not sourced from actual customers. Names, addresses, document/account numbers and dates are invented, not verified issued or payable identifiers. Emails use example domains; phones use 555-01xx numbers; IPs use documentation ranges; cards use sandbox numbers. SSNs use the invalid `900` area. This provenance belongs in project documentation, rather than inside each customer message. Invalid or invented identifiers are not evidence of a detector's accuracy on real issued identifiers.

The seeded policies still require EMAIL and PHONE only. A fresh MapleCo fixture yields 3 EMAIL and 3 PHONE replacements; RiverCo yields 3 EMAIL and 2 PHONE replacements. PERSON remains owner-policy controlled and lexicon based. The added SSN, address, document, card, bank, DOB and network details are not automatically detected by this data change; review and custom text redaction remain necessary. Update (structured-PII layer, Oct 18): an owner can now require SSN, CREDIT_CARD, ADDRESS, IP_ADDRESS and DOB (`demo_control redactions --types ALL`); with all on, MapleCo yields 1 SSN, 1 card, 2 IP, 1 DOB and 2 address replacements. National ID, passport, license, bank-account and device/user identifiers remain undetected.

## Runtime and handoff

Fixtures seed new data directories only. This task also revised the matching messages in the local default runtime sources, preserving record IDs, non-message fields, owner rules, grants and receipts. The earlier MapleCo `add-named-row` remains, with its message also rewritten as a review: current local MapleCo has 19 rows at revision 5, RiverCo 18 rows at revision 4. Old approvals need a new preview.

Refresh the running UI, select an account and click **Prepare preview**. Startup remains the normal two-terminal README workflow; no reset is needed. On another existing checkout, a fresh `DATAGATE_DATA_DIR` seeds the current fixtures without erasing its old store.

Branch/base: `feature` / `418ec0e`; current edits are uncommitted. Files: both CSV fixtures, this file, README/TEAM_WORKFLOW notes and fixture-dependent tests. No API, policy, detector, schema, dependency, UI-style or startup changes. Existing `.claude/` content is unrelated and untouched.

Current revision checks (superseding the earlier 20-row fixture results):

- From `backend`: `.venv/bin/python -m pytest -q` — **176 passed in 2.56s**, isolated test storage. Exact expected preview text in `test_flow.py` was updated; redaction counts, canonical-byte equality, authorization and dispatch assertions remain.
- From `frontend`: `npm run build` — **exit 0**, Vite production build succeeded.
- Chrome previews: MapleCo 19 reviews at revision 5 and RiverCo 18 at revision 4. All messages have review context; no UI Send was performed.
- Read-only DOM measurements of all message bodies in both companies: desktop 1–2 text lines; at 390px, 2–3 lines (redaction markers can make a line slightly taller). Both phone pages had `scrollWidth == innerWidth == 390`. The viewport override was reset afterward. These measurements cover current fonts/layout, not every possible browser or accessibility font size.
