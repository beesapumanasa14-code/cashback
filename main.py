"""Streamlit interface for the local Cashback Clarity AI application."""

import json
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import streamlit as st

import database
from model import OfferAnalysisError, analyze_offer, check_ollama, validate_analysis
from ocr_utils import MAX_IMAGE_BYTES, OCRUnavailableError, extract_text, validate_image
from tools import calculate_cashback, check_eligibility, parse_offer_date, to_decimal

DISCLAIMER = (
    "Cashback shown is an estimate based on the information provided. Actual eligibility and "
    "payment depend on the complete offer terms and the payment provider's confirmation."
)
INVESTIGATION_STATUSES = (
    "Waiting for cashback", "Investigation started", "Resolved", "Rejected by provider",
)

st.set_page_config(page_title="Cashback Clarity AI", page_icon="💸", layout="wide")
st.markdown(
    """
    <style>
    .stApp { background: #f6f8f6; }
    [data-testid="stSidebar"] { background: #edf3ee; }
    .hero { padding: 1.25rem 0 .4rem; }
    .hero h1 { color: #145c3d; letter-spacing: -.035em; }
    .subtle { color: #596b61; }
    [data-testid="stMetric"] { background: white; padding: 1rem; border: 1px solid #e1e9e2; border-radius: .7rem; }
    .disclaimer { padding: 1rem; border-left: 4px solid #d39322; background: #fff9e9; border-radius: .35rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

try:
    database.initialize_database()
except (OSError, database.sqlite3.Error) as exception:
    st.error(f"Local database could not be opened. Check the application folder permissions. Details: {exception}")
    st.stop()


def render_header() -> None:
    st.markdown(
        '<div class="hero"><h1>Cashback Clarity AI</h1>'
        '<p class="subtle">Understand the offer. Know the conditions. Estimate your cashback.</p></div>',
        unsafe_allow_html=True,
    )


def render_offer_source(prefix: str) -> tuple[str, str]:
    title = st.text_input("Offer title", key=f"{prefix}_title", placeholder="e.g. Weekend bank cashback")
    uploaded = st.file_uploader(
        "Optional screenshot (PNG/JPG, up to 5 MB)",
        type=["png", "jpg", "jpeg"],
        key=f"{prefix}_image",
    )
    if uploaded is not None:
        image_bytes = uploaded.getvalue()
        try:
            validate_image(image_bytes)
            st.image(image_bytes, caption="Screenshot preview (processed locally)", use_container_width=True)
        except (ValueError, OCRUnavailableError) as exception:
            st.error(str(exception))
        if st.button("Extract screenshot text locally", key=f"{prefix}_ocr"):
            try:
                recognized = extract_text(image_bytes)
                if not recognized:
                    st.warning("No text was detected. You can enter or correct the offer text below.")
                else:
                    st.session_state[f"{prefix}_text"] = recognized
                    st.success("Text extracted locally. Review and correct it before analysis.")
            except (ValueError, OCRUnavailableError) as exception:
                st.warning(f"{exception} Manual text entry is available below.")
    if st.button("Clear offer text", key=f"{prefix}_clear"):
        st.session_state[f"{prefix}_text"] = ""
    text = st.text_area(
        "Paste or review offer terms",
        key=f"{prefix}_text",
        height=170,
        placeholder="Paste the complete cashback terms here. Text and images remain on this computer.",
    )
    return title, text


def render_analysis(prefix: str, offer_text: str) -> dict | None:
    if st.button("Analyze with local Gemma", type="primary", key=f"{prefix}_analyze"):
        with st.spinner("Checking local Ollama and analyzing the offer..."):
            try:
                analysis = analyze_offer(offer_text)
                st.session_state[f"{prefix}_analysis_editor"] = json.dumps(analysis, ensure_ascii=False, indent=2)
                if not st.session_state.get(f"{prefix}_title"):
                    st.session_state[f"{prefix}_title"] = analysis["facts"].get("title") or "Untitled offer"
                st.success("Analysis complete. Review the extracted facts below.")
            except OfferAnalysisError as exception:
                st.error(str(exception))
    initial = st.session_state.get(f"{prefix}_analysis_editor", "")
    edited = st.text_area(
        "Extracted facts (editable JSON)",
        value=initial,
        height=290,
        key=f"{prefix}_analysis_editor",
        help="Correct extraction errors here. Use null for unknown values. Facts and interpretations are separate.",
    )
    if not edited.strip():
        return None
    try:
        return validate_analysis(json.loads(edited), offer_text)
    except (json.JSONDecodeError, OfferAnalysisError) as exception:
        st.error(f"Review the extracted JSON before using it: {exception}")
        return None


def show_offer_facts(analysis: dict) -> None:
    facts = analysis.get("facts", {})
    left, right = st.columns(2)
    with left:
        st.markdown("**Offer conditions**")
        for label, key in (
            ("Cashback type", "cashback_type"),
            ("Cashback percentage", "cashback_percentage"),
            ("Fixed cashback", "fixed_cashback_amount"),
            ("Maximum cashback", "maximum_cashback"),
            ("Minimum transaction", "minimum_transaction"),
            ("Valid from", "start_date"),
            ("Expiry", "expiry_date"),
            ("Crediting time", "crediting_time"),
        ):
            value = facts.get(key)
            if key in ("start_date", "expiry_date") and value and parse_offer_date(value) is None:
                value = f"Could not parse date: {value}"
            st.write(f"**{label}:** {value if value is not None else 'Not specified'}")
    with right:
        for label, key in (
            ("Eligible merchants", "eligible_merchants"),
            ("Excluded merchants", "excluded_merchants"),
            ("Excluded banks", "excluded_banks"),
            ("Eligible banks", "eligible_banks"),
            ("Eligible cards", "eligible_cards"),
            ("Payment methods", "eligible_payment_methods"),
            ("Other restrictions", "other_restrictions"),
        ):
            value = facts.get(key)
            st.write(f"**{label}:** {', '.join(value) if value else 'Not specified'}")
        st.markdown("**Missing conditions**")
        if analysis.get("missing_conditions"):
            for item in analysis["missing_conditions"]:
                st.write(f"- {item}")
        else:
            st.write("None identified by the model; verify the complete terms.")
    if analysis.get("interpretations"):
        st.markdown("**Plain-language interpretation**")
        for item in analysis["interpretations"]:
            st.write(f"- {item}")
    if analysis.get("excerpts"):
        with st.expander("Supporting excerpts from the offer"):
            for excerpt in analysis["excerpts"]:
                st.markdown(f"> {excerpt}")


def save_offer_button(title: str, offer_text: str, analysis: dict, key: str) -> None:
    if st.button("Save this offer locally", key=key):
        try:
            offer_id = database.save_offer(
                title or analysis.get("facts", {}).get("title") or "Untitled offer",
                offer_text,
                analysis,
            )
            st.success(f"Offer saved on this computer (reference {offer_id[:8]}).")
        except (ValueError, database.sqlite3.Error, OSError) as exception:
            st.error(f"Offer could not be saved: {exception}")


def dashboard() -> None:
    st.subheader("Your dashboard")
    try:
        stats = database.get_dashboard_stats()
    except database.sqlite3.Error as exception:
        st.error(f"Could not load dashboard data: {exception}")
        return
    metrics = st.columns(4)
    metrics[0].metric("Saved offers", stats["saved_offers"])
    metrics[1].metric("Marked active", stats["active_offers"])
    metrics[2].metric("Estimated cashback", f"Rs. {stats['estimated_cashback']:.2f}")
    metrics[3].metric("Investigations", stats["investigations"])
    st.caption("Cashback totals are estimates from calculations saved on this device, not cashback received.")
    if not stats["saved_offers"] and not stats["investigations"]:
        st.info("Your local workspace is empty. Analyze an offer or calculate cashback to get started.")
    if stats["recent_activity"]:
        st.markdown("#### Recent activity")
        st.dataframe(stats["recent_activity"], use_container_width=True, hide_index=True)
    st.markdown('<div class="disclaimer">' + DISCLAIMER + "</div>", unsafe_allow_html=True)


def analyze_page() -> None:
    st.subheader("Analyze an offer")
    title, offer_text = render_offer_source("analyze")
    analysis = render_analysis("analyze", offer_text)
    if analysis:
        show_offer_facts(analysis)
        save_offer_button(title, offer_text, analysis, "save_analyzed_offer")


def before_you_pay() -> None:
    st.subheader("Before You Pay")
    st.caption("Review the source, correct extracted facts, then check your transaction against the stated rules.")
    title, offer_text = render_offer_source("before")
    analysis = render_analysis("before", offer_text)
    if not analysis:
        st.info("Analyze an offer above to see its conditions and check your transaction.")
        return
    show_offer_facts(analysis)
    facts = analysis["facts"]
    st.markdown("#### Your transaction")
    fields = st.columns(3)
    amount_text = fields[0].text_input("Transaction amount (Rs.)", key="before_amount", placeholder="e.g. 600")
    merchant = fields[1].text_input("Merchant", key="before_merchant")
    bank = fields[2].text_input("Bank", key="before_bank")
    fields = st.columns(3)
    card = fields[0].text_input("Card or card type", key="before_card")
    payment_method = fields[1].text_input("Payment method", key="before_payment")
    new_customer = fields[2].selectbox("Customer status", ["Not specified", "New customer", "Existing customer"])
    fields = st.columns(2)
    coupon_applied = fields[0].selectbox("Required coupon applied?", ["Not specified", "Yes", "No"])
    offer_activated = fields[1].selectbox("Offer activated?", ["Not specified", "Yes", "No"])
    signature = json.dumps(
        {
            "facts": facts,
            "amount": amount_text,
            "merchant": merchant,
            "bank": bank,
            "card": card,
            "payment_method": payment_method,
            "new_customer": new_customer,
            "coupon_applied": coupon_applied,
            "offer_activated": offer_activated,
        },
        sort_keys=True,
    )
    if st.button("Check eligibility and estimate cashback", type="primary", key="before_check"):
        try:
            amount = to_decimal(amount_text, "Transaction amount")
            details = {
                "transaction_amount": amount,
                "merchant": merchant or None,
                "bank": bank or None,
                "card": card or None,
                "payment_method": payment_method or None,
                "is_new_user": {"Not specified": None, "New customer": True, "Existing customer": False}[new_customer],
                "coupon_applied": {"Not specified": None, "Yes": True, "No": False}[coupon_applied],
                "offer_activated": {"Not specified": None, "Yes": True, "No": False}[offer_activated],
            }
            eligibility = check_eligibility(facts, details)
            cashback = calculate_cashback(
                amount,
                facts.get("cashback_percentage"),
                facts.get("maximum_cashback"),
                facts.get("minimum_transaction"),
                facts.get("fixed_cashback_amount"),
            )
            st.session_state["before_result"] = {
                "eligibility": eligibility, "cashback": cashback, "signature": signature,
            }
            st.session_state["before_amount_value"] = amount
        except ValueError as exception:
            st.error(f"Check the transaction details: {exception}")
    result = st.session_state.get("before_result")
    if result and result["signature"] != signature:
        st.info("Transaction details or offer conditions changed. Run the assessment again.")
    elif result:
        eligibility, cashback = result["eligibility"], result["cashback"]
        st.markdown("#### Assessment")
        st.info(f"**{eligibility['status']}** — {eligibility['disclaimer']}")
        outcome_columns = st.columns(3)
        outcome_columns[0].metric(
            "Estimated cashback",
            f"Rs. {cashback.cashback:.2f}" if cashback.cashback is not None else "Cannot calculate",
        )
        outcome_columns[1].metric(
            "Effective cost",
            f"Rs. {cashback.final_amount:.2f}" if cashback.final_amount is not None else "Not available",
        )
        outcome_columns[2].metric(
            "Completeness",
            "Information appears complete"
            if eligibility["status"] == "ELIGIBLE_BASED_ON_PROVIDED_RULES"
            else "Some conditions remain unclear"
            if eligibility["status"] == "NEEDS_MORE_INFORMATION"
            else "Insufficient information to assess eligibility",
        )
        if cashback.missing_information:
            st.warning("Cashback calculation needs: " + ", ".join(cashback.missing_information))
        if eligibility["satisfied"]:
            st.markdown("**Conditions satisfied**")
            for item in eligibility["satisfied"]:
                st.write(f"- {item}")
        if eligibility["failed"]:
            st.markdown("**Conditions not satisfied**")
            for item in eligibility["failed"]:
                st.write(f"- {item}")
        if eligibility["missing"]:
            st.markdown("**Missing information**")
            for item in eligibility["missing"]:
                st.write(f"- {item}")
        if facts.get("start_date") or facts.get("expiry_date"):
            st.write(f"**Offer validity:** {facts.get('start_date') or 'Start date not specified'} to {facts.get('expiry_date') or 'Expiry not specified'}")
        st.caption("Before paying, verify the complete terms, eligible merchant/bank/card, activation and coupon rules, expiry, and crediting time with the official offer source.")
        if st.button("Save this estimate locally", key="before_save_calculation"):
            try:
                database.save_calculation(
                    st.session_state["before_amount_value"],
                    cashback.cashback,
                )
                st.success("Estimate saved. It is not a record of cashback received.")
            except (database.sqlite3.Error, OSError) as exception:
                st.error(f"Estimate could not be saved: {exception}")
    st.markdown('<div class="disclaimer">' + DISCLAIMER + "</div>", unsafe_allow_html=True)
    save_offer_button(title, offer_text, analysis, "save_before_offer")


def calculator_page() -> None:
    st.subheader("Cashback calculator")
    st.caption("Calculations use Decimal-based arithmetic. Leave unknown offer terms blank; no cap or rate is invented.")
    with st.form("calculator_form"):
        columns = st.columns(2)
        amount = columns[0].text_input("Transaction amount (Rs.)", placeholder="600")
        percent = columns[1].text_input("Cashback percentage (optional)", placeholder="10")
        columns = st.columns(2)
        fixed = columns[0].text_input("Fixed cashback amount (optional)", placeholder="Leave blank if percentage offer")
        cap = columns[1].text_input("Maximum cashback (optional)", placeholder="100")
        minimum = st.text_input("Minimum transaction (optional)", placeholder="500")
        submitted = st.form_submit_button("Calculate estimate", type="primary")
    if submitted:
        try:
            result = calculate_cashback(amount, percent, cap, minimum, fixed)
            st.session_state["calculator_result"] = result
            st.session_state["calculator_amount"] = to_decimal(amount, "Transaction amount")
        except ValueError as exception:
            st.error(str(exception))
    result = st.session_state.get("calculator_result")
    if result:
        if result.cashback is None:
            st.warning(result.message)
            st.write("Missing information: " + ", ".join(result.missing_information))
        elif not result.eligible:
            st.warning(result.message)
        else:
            cards = st.columns(3)
            cards[0].metric("Calculated cashback before cap", f"Rs. {result.calculated_cashback:.2f}")
            cards[1].metric("Estimated cashback", f"Rs. {result.cashback:.2f}")
            cards[2].metric("Effective cost after estimate", f"Rs. {result.final_amount:.2f}")
            st.caption(result.message)
        if st.button("Save estimate locally", key="calculator_save"):
            try:
                database.save_calculation(st.session_state["calculator_amount"], result.cashback)
                st.success("Estimate saved locally.")
            except (database.sqlite3.Error, OSError) as exception:
                st.error(f"Estimate could not be saved: {exception}")
    st.markdown('<div class="disclaimer">' + DISCLAIMER + "</div>", unsafe_allow_html=True)


def saved_offers_page() -> None:
    st.subheader("Saved offers")
    try:
        offers = database.list_offers()
    except (database.sqlite3.Error, json.JSONDecodeError) as exception:
        st.error(f"Saved offers could not be loaded: {exception}")
        return
    if not offers:
        st.info("No saved offers yet. Analyze an offer and choose Save this offer locally.")
        return
    query = st.text_input("Search by title or offer text")
    status_filter = st.selectbox("Filter by status", ["All", "Unknown", "Active", "Expired"])
    filtered = [
        offer for offer in offers
        if query.casefold() in (offer["title"] + " " + offer["offer_text"]).casefold()
        and (status_filter == "All" or offer["status"] == status_filter)
    ]
    if not filtered:
        st.info("No offers match those filters.")
        return
    selected_id = st.selectbox("Choose an offer", [item["id"] for item in filtered], format_func=lambda item_id: next(
        f"{item['title']} — {item['status']}" for item in filtered if item["id"] == item_id
    ))
    offer = next(item for item in filtered if item["id"] == selected_id)
    st.markdown(f"#### {offer['title']}")
    st.caption(f"Updated {offer['updated_at']}; status is user-managed.")
    st.text_area("Offer text", value=offer["offer_text"], key="saved_offer_text")
    edited_json = st.text_area(
        "Extracted information (editable JSON)",
        value=json.dumps(offer["analysis"], ensure_ascii=False, indent=2),
        height=250,
        key="saved_offer_analysis",
    )
    new_status = st.selectbox(
        "Offer status (set only when confirmed from the offer or by you)",
        ["Unknown", "Active", "Expired"],
        index=["Unknown", "Active", "Expired"].index(offer["status"]),
        key="saved_offer_status",
    )
    controls = st.columns(3)
    if controls[0].button("Save changes", key="saved_offer_update"):
        try:
            analysis = validate_analysis(json.loads(edited_json), st.session_state["saved_offer_text"])
            database.save_offer(
                offer["title"], st.session_state["saved_offer_text"], analysis,
                status=new_status, offer_id=offer["id"],
            )
            st.success("Offer updated.")
            st.rerun()
        except (ValueError, json.JSONDecodeError, OfferAnalysisError, database.sqlite3.Error) as exception:
            st.error(f"Offer could not be updated: {exception}")
    if controls[1].button("Reanalyze with local Gemma", key="saved_offer_reanalyze"):
        try:
            analysis = analyze_offer(st.session_state["saved_offer_text"])
            database.save_offer(
                offer["title"], st.session_state["saved_offer_text"], analysis,
                status=new_status, offer_id=offer["id"],
            )
            st.success("Offer reanalyzed and updated.")
            st.rerun()
        except (OfferAnalysisError, database.sqlite3.Error, ValueError) as exception:
            st.error(str(exception))
    if controls[2].button("Delete offer", key="saved_offer_delete"):
        try:
            database.delete_offer(offer["id"])
            st.success("Offer deleted.")
            st.rerun()
        except database.sqlite3.Error as exception:
            st.error(f"Offer could not be deleted: {exception}")
    with st.expander("Offer details"):
        show_offer_facts(offer["analysis"])


def _store_evidence(uploaded) -> str | None:
    if uploaded is None:
        return None
    data = uploaded.getvalue()
    image_format = validate_image(data)
    database.EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    suffix = ".png" if image_format == "PNG" else ".jpg"
    evidence_path = database.EVIDENCE_DIR / f"{uuid.uuid4()}{suffix}"
    evidence_path.write_bytes(data)
    return str(evidence_path)


def investigations_page() -> None:
    st.subheader("Missing cashback tracker")
    st.caption("Investigation statuses and records are managed by you; the app does not contact a provider.")
    try:
        investigations = database.list_investigations()
    except database.sqlite3.Error as exception:
        st.error(f"Investigations could not be loaded: {exception}")
        return
    with st.expander("Create an investigation", expanded=not investigations):
        with st.form("new_investigation"):
            description = st.text_input("Offer description")
            merchant = st.text_input("Merchant")
            transaction_date = st.date_input("Transaction date", value=date.today())
            values = st.columns(2)
            amount = values[0].text_input("Transaction amount (Rs.)")
            expected = values[1].text_input("Expected cashback (Rs.)")
            actual = st.text_input("Actual cashback received (if known)")
            reference = st.text_input("Optional transaction reference")
            notes = st.text_area("Investigation notes")
            evidence = st.file_uploader(
                "Optional evidence screenshot (PNG/JPG, up to 5 MB)",
                type=["png", "jpg", "jpeg"],
                key="new_investigation_evidence",
            )
            submitted = st.form_submit_button("Create investigation")
        if submitted:
            stored = None
            try:
                to_decimal(amount, "Transaction amount")
                to_decimal(expected, "Expected cashback")
                if actual.strip():
                    to_decimal(actual, "Actual cashback")
                stored = _store_evidence(evidence)
                database.save_investigation({
                    "offer_description": description, "merchant": merchant,
                    "transaction_date": transaction_date.isoformat(),
                    "transaction_amount": amount, "expected_cashback": expected,
                    "actual_cashback": actual, "transaction_reference": reference,
                    "notes": notes, "evidence_path": stored,
                })
                st.success("Investigation saved on this device.")
                st.rerun()
            except (ValueError, OCRUnavailableError, database.sqlite3.Error, OSError) as exception:
                if stored and Path(stored).is_file():
                    Path(stored).unlink()
                st.error(f"Investigation could not be saved: {exception}")
    if not investigations:
        st.info("No investigations recorded.")
        return
    selected_id = st.selectbox(
        "Choose an investigation",
        [item["id"] for item in investigations],
        format_func=lambda identifier: next(
            f"{item['merchant']} — {item['transaction_date']} ({item['status']})"
            for item in investigations if item["id"] == identifier
        ),
    )
    item = next(record for record in investigations if record["id"] == selected_id)
    with st.form("edit_investigation"):
        description = st.text_input("Offer description", value=item["offer_description"])
        merchant = st.text_input("Merchant", value=item["merchant"])
        transaction_date = st.text_input("Transaction date (YYYY-MM-DD)", value=item["transaction_date"])
        fields = st.columns(2)
        amount = fields[0].text_input("Transaction amount (Rs.)", value=item["transaction_amount"])
        expected = fields[1].text_input("Expected cashback (Rs.)", value=item["expected_cashback"])
        actual = st.text_input("Actual cashback received", value=item["actual_cashback"] or "")
        reference = st.text_input("Transaction reference", value=item["transaction_reference"] or "")
        notes = st.text_area("Investigation notes", value=item["notes"])
        status = st.selectbox("User-managed status", INVESTIGATION_STATUSES, index=INVESTIGATION_STATUSES.index(item["status"]))
        evidence = st.file_uploader(
            "Replace evidence screenshot (optional)",
            type=["png", "jpg", "jpeg"],
            key=f"edit_evidence_{item['id']}",
        )
        controls = st.columns(2)
        save_clicked = controls[0].form_submit_button("Update investigation")
        delete_clicked = controls[1].form_submit_button("Delete investigation")
    if save_clicked:
        stored = None
        try:
            to_decimal(amount, "Transaction amount")
            to_decimal(expected, "Expected cashback")
            date.fromisoformat(transaction_date)
            if actual.strip():
                to_decimal(actual, "Actual cashback")
            stored = _store_evidence(evidence)
            database.save_investigation({
                "offer_description": description, "merchant": merchant,
                "transaction_date": transaction_date, "transaction_amount": amount,
                "expected_cashback": expected, "actual_cashback": actual,
                "transaction_reference": reference, "notes": notes, "status": status,
                "evidence_path": stored or item["evidence_path"],
            }, investigation_id=item["id"])
            if stored and item["evidence_path"]:
                database.delete_evidence_file(item["evidence_path"])
            st.success("Investigation updated.")
            st.rerun()
        except (ValueError, OCRUnavailableError, database.sqlite3.Error, OSError) as exception:
            if stored and Path(stored).is_file():
                Path(stored).unlink()
            st.error(f"Investigation could not be updated: {exception}")
    if delete_clicked:
        try:
            database.delete_investigation(item["id"])
            st.success("Investigation and its local evidence were deleted.")
            st.rerun()
        except (database.sqlite3.Error, OSError) as exception:
            st.error(f"Investigation could not be deleted: {exception}")
    message = (
        f"Subject: Cashback follow-up for {item['merchant']}\n\n"
        f"Hello,\n\nI am following up about cashback for a transaction at {item['merchant']} "
        f"on {item['transaction_date']}.\n"
        f"Offer: {item['offer_description']}\n"
        f"Transaction amount: Rs. {item['transaction_amount']}\n"
        f"Expected cashback: Rs. {item['expected_cashback']}\n"
        f"Actual cashback received: {item['actual_cashback'] or 'Not known'}\n"
        f"Transaction reference: {item['transaction_reference'] or 'Not provided'}\n"
        f"Issue/notes: {item['notes'] or 'Cashback has not been received.'}\n\n"
        "Please review the complete offer terms and transaction. This message is a draft; "
        "the app has not sent it or confirmed cashback approval."
    )
    st.markdown("#### Support message draft")
    st.code(message, language=None)
    if item["evidence_path"]:
        path = Path(item["evidence_path"])
        if path.is_file():
            st.image(str(path), caption="Evidence stored locally")


def settings_page() -> None:
    st.subheader("Settings and privacy")
    st.write(f"**Database file:** `{database.DB_PATH}`")
    st.write(f"**Evidence folder:** `{database.EVIDENCE_DIR}`")
    st.write("Offer text, images, investigation records, and calculations are processed or stored locally.")
    st.warning(
        "Local SQLite files and evidence are not encrypted by this application. Protect your Windows account "
        "and device. Do not enter passwords, PINs, OTPs, CVVs, or full card numbers."
    )
    if st.button("Check local Ollama connection"):
        with st.spinner("Checking Ollama on this computer..."):
            status = check_ollama()
        if status["reachable"] and status["model_available"]:
            st.success(status["message"])
        else:
            st.warning(status["message"])
    st.caption("No payment is initiated and no bank or payment provider is contacted.")


render_header()
with st.sidebar:
    st.markdown("### Cashback Clarity AI")
    section = st.radio(
        "Navigate",
        (
            "Dashboard", "Analyze an Offer", "Before You Pay", "Cashback Calculator",
            "Saved Offers", "Missing Cashback Tracker", "Settings and Privacy",
        ),
        key="navigation",
    )

try:
    if section == "Dashboard":
        dashboard()
    elif section == "Analyze an Offer":
        analyze_page()
    elif section == "Before You Pay":
        before_you_pay()
    elif section == "Cashback Calculator":
        calculator_page()
    elif section == "Saved Offers":
        saved_offers_page()
    elif section == "Missing Cashback Tracker":
        investigations_page()
    else:
        settings_page()
except database.sqlite3.Error as exception:
    st.error(f"A local database operation failed: {exception}")
