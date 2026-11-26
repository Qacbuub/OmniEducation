"""Finance acceptance test: invoices, partial payments and correct outstanding balances."""
from decimal import Decimal

from core.models import AuditEvent
from finance.models import Invoice

LINES = [{"description": "Tuition", "amount": "30000.00"}, {"description": "Lunch", "amount": "6000.00"}]


def _invoice(c, student, **extra):
    r = c.post("/api/fees/invoices/", {"student": student.id, "lines": LINES, **extra}, format="json")
    assert r.status_code == 201, r.data
    return r.data


def _pay(c, invoice_id, amount, method="cash"):
    return c.post("/api/fees/payments/", {"invoice": invoice_id, "amount": amount, "method": method}, format="json")


def test_partial_payments_give_correct_balance(client_for, make_user, make_student, school):
    fin = make_user("fin@s.edu", "finance_officer", school)
    c = client_for(fin)
    inv = _invoice(c, make_student(school))
    assert Decimal(str(inv["total"])) == Decimal("36000.00") and inv["status"] == "issued"

    assert _pay(c, inv["id"], "10000").status_code == 201
    inv1 = c.get(f"/api/fees/invoices/{inv['id']}/").data
    assert Decimal(str(inv1["balance"])) == Decimal("26000.00") and inv1["status"] == "partial"

    assert _pay(c, inv["id"], "26000.00").status_code == 201
    inv2 = c.get(f"/api/fees/invoices/{inv['id']}/").data
    assert Decimal(str(inv2["balance"])) == 0 and inv2["status"] == "paid" and len(inv2["payments"]) == 2
    assert AuditEvent.objects.filter(action="payment.recorded").count() == 2


def test_invalid_payment_amounts_are_rejected(client_for, make_user, make_student, school):
    fin = make_user("fin@s.edu", "finance_officer", school)
    c = client_for(fin)
    inv = _invoice(c, make_student(school))
    for bad in ("0", "-50", "36000.01"):
        r = _pay(c, inv["id"], bad)
        assert r.status_code == 400, bad
    assert _pay(c, inv["id"], "36000.01").data["code"] == "overpayment"
    assert Invoice.objects.get(pk=inv["id"]).amount_paid == 0


def test_scholarship_discount(client_for, make_user, make_student, school):
    fin = make_user("fin@s.edu", "finance_officer", school)
    c = client_for(fin)
    s = make_student(school)
    no_reason = c.post("/api/fees/invoices/", {"student": s.id, "lines": LINES, "discount_amount": "9000"},
                       format="json")
    assert no_reason.status_code == 400 and no_reason.data["code"] == "discount_reason_required"
    too_big = c.post("/api/fees/invoices/", {"student": s.id, "lines": LINES, "discount_amount": "50000",
                                             "discount_reason": "x"}, format="json")
    assert too_big.status_code == 400
    inv = _invoice(c, s, discount_amount="9000", discount_reason="Merit scholarship 25%")
    assert Decimal(str(inv["total"])) == Decimal("27000.00")


def test_void_rules(client_for, make_user, make_student, school):
    fin = make_user("fin@s.edu", "finance_officer", school)
    c = client_for(fin)
    inv = _invoice(c, make_student(school))
    _pay(c, inv["id"], "100")
    r = c.post(f"/api/fees/invoices/{inv['id']}/void/", {"reason": "Issued in error"}, format="json")
    assert r.status_code == 400 and r.data["code"] == "invoice_has_payments"
    inv2 = _invoice(c, make_student(school, "B", "C"))
    assert c.post(f"/api/fees/invoices/{inv2['id']}/void/", {"reason": "Error"}, format="json").status_code == 200
    assert _pay(c, inv2["id"], "100").status_code == 400  # void invoices can't be paid


def test_fee_plan_bulk_issue_skips_already_billed(client_for, make_user, make_student, school):
    fin = make_user("fin@s.edu", "finance_officer", school)
    c = client_for(fin)
    make_student(school, "A", "One", level="Grade 4")
    make_student(school, "B", "Two", level="Grade 4")
    make_student(school, "C", "Three", level="Grade 5")
    plan = c.post("/api/fees/plans/", {"name": "Grade 4 Term 3", "applies_to": "Grade 4",
                                       "items": [{"description": "Tuition", "amount": "25000"}]}, format="json").data
    first = c.post(f"/api/fees/plans/{plan['id']}/issue/", {}, format="json")
    assert first.data["issued"] == 2
    second = c.post(f"/api/fees/plans/{plan['id']}/issue/", {}, format="json")
    assert second.data["issued"] == 0 and second.data["skipped"] == 2


def test_guardian_sees_only_childrens_invoices_and_cannot_record_payments(
        client_for, make_user, make_student, link_guardian, school):
    fin = make_user("fin@s.edu", "finance_officer", school)
    parent = make_user("parent@s.edu", "guardian", school)
    child, other = make_student(school, "Kid", "Mine"), make_student(school, "Kid", "Other")
    link_guardian(child, parent)
    mine, theirs = _invoice(client_for(fin), child), _invoice(client_for(fin), other)
    pc = client_for(parent)
    assert [i["id"] for i in pc.get("/api/fees/invoices/").data["results"]] == [mine["id"]]
    assert pc.get(f"/api/fees/invoices/{theirs['id']}/").status_code == 404
    assert _pay(pc, mine["id"], "100").status_code == 403
    # Mock online payment is allowed for their own child's invoice, and is clearly labelled.
    r = pc.post(f"/api/fees/invoices/{mine['id']}/pay-online/", {"amount": "500"}, format="json")
    assert r.status_code == 201 and r.data["method"] == "mock_online" and "MOCK" in r.data["method_label"]


def test_teacher_cannot_access_fee_ledger(client_for, make_user, make_student, school):
    teacher = make_user("t@s.edu", "class_teacher", school)
    assert client_for(teacher).get("/api/fees/arrears/").status_code == 403
    assert client_for(teacher).post("/api/fees/plans/", {}, format="json").status_code == 403


def test_arrears_report(client_for, make_user, make_student, school):
    fin = make_user("fin@s.edu", "finance_officer", school)
    c = client_for(fin)
    inv = _invoice(c, make_student(school))
    _pay(c, inv["id"], "6000")
    r = c.get("/api/fees/arrears/")
    assert r.status_code == 200
    assert Decimal(str(r.data["totals"]["outstanding"])) == Decimal("30000.00")
    assert Decimal(str(r.data["totals"]["collected"])) == Decimal("6000.00")
    assert r.data["results"][0]["outstanding"] == Decimal("30000.00")
    csv_resp = c.get("/api/fees/arrears/?export=csv")
    assert csv_resp["Content-Type"] == "text/csv" and b"Outstanding" in csv_resp.content
