"""
School (K-12) business rules. Views stay thin so the same rules apply to the API, seed data and tests.

Policies come from Tenant.policies (defaults in core.models.SCHOOL_POLICIES):
  pass_mark, promotion_min_average, attendance_alert_absences.
"""
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from admissions.models import AcademicPeriod, Enrollment
from comms.services import notify
from core.audit import log_event
from core.exceptions import BusinessRuleViolation
from core.models import User

from .models import (
    ClassAssignment,
    ClassPlacement,
    ClassSection,
    PromotionDecision,
    PupilAttendance,
    SchoolAssessment,
    SchoolMark,
    SchoolTimetable,
    TermResult,
)

TWO = Decimal("0.01")


def q2(v):
    return Decimal(v).quantize(TWO, rounding=ROUND_HALF_UP)


def policy(tenant, key):
    return Decimal(str(tenant.policy(key)))


def current_year(tenant):
    return AcademicPeriod.objects.filter(tenant=tenant, kind="academic_year", is_current=True).first()


def current_term(tenant):
    return AcademicPeriod.objects.filter(tenant=tenant, kind="term", is_current=True).first()


def term_for_date(section, day):
    return section.academic_year.children.filter(kind="term", start_date__lte=day, end_date__gte=day).first()


def is_school_manager(user):
    return user.has_perm_code("school.classes.manage")


def guardians_of(student):
    return [link.guardian.user for link in student.guardian_links.select_related("guardian__user")
            if link.receives_notifications and link.guardian.user_id]


def family_of(student):
    users = guardians_of(student)
    if student.user_id:
        users.append(student.user)
    return users


# =========================================================================== class placement
def active_placement(student, year=None):
    qs = ClassPlacement.objects.filter(student=student, status="active").select_related(
        "section__grade_level", "section__academic_year", "section__homeroom_teacher")
    if year is not None:
        qs = qs.filter(section__academic_year=year)
    return qs.first()


def pupils_in(section):
    from people.models import Student

    return (Student.objects.filter(class_placements__section=section, class_placements__status="active",
                                   status="active")
            .select_related("person").order_by("person__last_name", "person__first_name"))


@transaction.atomic
def place_student(student, section, *, user=None, request=None, on=None):
    """Put a pupil in a class (or move them to another class in the same year)."""
    on = on or timezone.localdate()
    section = ClassSection.objects.select_for_update().select_related("grade_level", "academic_year").get(
        pk=section.pk)
    if student.tenant_id != section.tenant_id:
        raise BusinessRuleViolation("Class not found.", code="not_found")
    if student.status != "active":
        raise BusinessRuleViolation("Only active pupils can be placed in a class.", code="student_not_active")
    current = active_placement(student, section.academic_year)
    if current and current.section_id == section.id:
        raise BusinessRuleViolation(f"{student.person.full_name} is already in {section.label}.",
                                    code="already_placed")
    if TermResult.objects.filter(student=student, section__academic_year=section.academic_year,
                                 term__end_date__gte=on).exclude(section=section).exists():
        raise BusinessRuleViolation("This term's results are already finalized in the pupil's current class.",
                                    code="results_finalized")
    if pupils_in(section).count() >= section.capacity:
        raise BusinessRuleViolation(f"{section.label} is full ({section.capacity} pupils).", code="class_full")
    if current:
        current.status, current.end_date = "moved", on
        current.save(update_fields=["status", "end_date", "updated_at"])
    placement = ClassPlacement.objects.create(tenant=student.tenant, student=student, section=section, start_date=on,
                                              placed_by=user)
    student.current_level, student.current_section = section.grade_level.name, section.name
    student.save(update_fields=["current_level", "current_section"])
    Enrollment.objects.filter(student=student, status="active").update(level_label=section.grade_level.name,
                                                                       section_label=section.name)
    log_event("class.placed", request=request, actor=user, target=student,
              changes={"section": section.label, "moved_from": current.section.label if current else None})
    return placement


# =========================================================================== timetable
def check_timetable(assignment, day, start, end, room="", exclude_id=None):
    """A class can't have two lessons at once; a teacher can't teach two classes at once; rooms can't clash."""
    if end <= start:
        raise BusinessRuleViolation("A lesson must end after it starts.", code="invalid_lesson_time")
    section = assignment.section
    same_year = (SchoolTimetable.objects.filter(assignment__section__academic_year=section.academic_year, day=day,
                                                start_time__lt=end, end_time__gt=start)
                 .select_related("assignment__section__grade_level", "assignment__subject"))
    if exclude_id:
        same_year = same_year.exclude(pk=exclude_id)
    for other in same_year:
        if other.assignment.section_id == section.id:
            raise BusinessRuleViolation(f"{section.label} already has {other.assignment.subject} at that time.",
                                        code="class_timetable_conflict")
        if assignment.teacher_id and other.assignment.teacher_id == assignment.teacher_id:
            raise BusinessRuleViolation(
                f"The teacher already teaches {other.assignment.section.label} {other.assignment.subject} then.",
                code="teacher_timetable_conflict")
        if room and other.room and other.room.lower() == room.lower():
            raise BusinessRuleViolation(f"Room {room} is already used by {other.assignment.section.label}.",
                                        code="room_conflict")


def teaches(user, section, subject=None):
    qs = ClassAssignment.objects.filter(section=section, teacher=user)
    if subject is not None:
        qs = qs.filter(subject=subject)
    return qs.exists()


# =========================================================================== attendance
def can_record_attendance(user, section, lesson=None):
    if not user.has_perm_code("school.attendance.record"):
        return False
    if is_school_manager(user) or section.homeroom_teacher_id == user.id:
        return True
    return lesson is not None and lesson.assignment.teacher_id == user.id


@transaction.atomic
def record_attendance(section, *, day, rows, user, lesson=None, request=None):
    """rows: [{"student": id, "status": "present|absent|late|excused", "reason": ""}]"""
    today = timezone.localdate()
    if not can_record_attendance(user, section, lesson):
        raise BusinessRuleViolation(
            "Only the class teacher (daily register) or the lesson's teacher can record this attendance.",
            code="not_your_class")
    if day > today:
        raise BusinessRuleViolation("Attendance can't be recorded for a future date.", code="future_date")
    if day.weekday() >= 5:
        raise BusinessRuleViolation("Attendance is only taken on school days (Monday to Friday).",
                                    code="not_a_school_day")
    term = term_for_date(section, day)
    if term is None:
        raise BusinessRuleViolation("That date is not inside a term of this class's academic year.",
                                    code="outside_term")
    if lesson is not None:
        if lesson.assignment.section_id != section.id:
            raise BusinessRuleViolation("That lesson belongs to another class.", code="wrong_lesson")
        if lesson.day != day.weekday():
            raise BusinessRuleViolation(f"That lesson is on {lesson.get_day_display()}, not {day:%A}.",
                                        code="wrong_lesson_day")
    members = {s.id: s for s in pupils_in(section)}
    errors = {}
    for i, row in enumerate(rows):
        if row.get("student") not in members:
            errors[str(i)] = ["This pupil is not in the class."]
        elif row.get("status") not in PupilAttendance.Status.values:
            errors[str(i)] = ["Choose present, absent, late or excused."]
        elif row["status"] == "excused" and not (row.get("reason") or "").strip():
            errors[str(i)] = ["Give a reason for an excused absence."]
    if errors:
        raise BusinessRuleViolation("Some attendance rows are invalid.", code="invalid_attendance", fields=errors)

    saved, newly_absent = [], []
    for row in rows:
        student = members[row["student"]]
        rec, created = PupilAttendance.objects.get_or_create(
            student=student, date=day, lesson=lesson,
            defaults={"tenant": section.tenant, "section": section, "status": row["status"],
                      "reason": row.get("reason", ""), "recorded_by": user})
        was_absent = not created and rec.status in PupilAttendance.ABSENT_STATUSES
        if not created:
            rec.status, rec.reason, rec.recorded_by = row["status"], row.get("reason", ""), user
            rec.save(update_fields=["status", "reason", "recorded_by", "updated_at"])
        if rec.status == "absent" and not was_absent:
            newly_absent.append(rec)
        saved.append(rec)

    # Parent notification: once per pupil per day, for unexplained absences.
    for rec in newly_absent:
        if PupilAttendance.objects.filter(student=rec.student, date=day, guardian_notified=True).exists():
            continue
        what = f"{lesson.assignment.subject} lesson" if lesson else "school"
        notify(guardians_of(rec.student), f"{rec.student.person.first_name} was absent today",
               f"{rec.student.person.full_name} was marked absent from {what} on {day:%a %d %b}. "
               "Please contact the class teacher if this is unexpected.", kind="attendance", email=True,
               link="/school/children")
        rec.guardian_notified = True
        rec.save(update_fields=["guardian_notified"])
        # Alert staff when unexplained absences in the term reach the policy threshold.
        threshold = int(policy(section.tenant, "attendance_alert_absences"))
        count = PupilAttendance.objects.filter(student=rec.student, lesson__isnull=True, status="absent",
                                               date__range=(term.start_date, term.end_date)).count()
        if lesson is None and count == threshold:
            staff = [u for u in [section.homeroom_teacher] if u] + list(
                User.objects.filter(tenant=section.tenant, role__code="principal", is_active=True))
            notify(staff, f"Attendance alert: {rec.student.person.full_name}",
                   f"{count} unexplained absences this term in {section.label}.", kind="attendance")
    log_event("attendance.recorded", request=request, actor=user, target=section,
              changes={"date": str(day), "lesson": lesson.id if lesson else None, "rows": len(saved),
                       "absent": sum(r.status == "absent" for r in saved)})
    return saved


def attendance_summary(student, start=None, end=None):
    qs = PupilAttendance.objects.filter(student=student, lesson__isnull=True)
    if start:
        qs = qs.filter(date__gte=start)
    if end:
        qs = qs.filter(date__lte=end)
    counts = defaultdict(int)
    for status in qs.values_list("status", flat=True):
        counts[status] += 1
    days = sum(counts.values())
    attended = counts["present"] + counts["late"]
    return {"days_recorded": days, "present": counts["present"], "late": counts["late"],
            "absent": counts["absent"], "excused": counts["excused"],
            "attendance_rate": round(100 * attended / days, 1) if days else None}


# =========================================================================== marks and results
def results_locked(section, term):
    return TermResult.objects.filter(section=section, term=term).exists()


def can_enter_marks(user, section, subject):
    if not user.has_perm_code("school.marks.enter"):
        return False
    return user.has_perm_code("school.results.publish") or teaches(user, section, subject)


def ensure_marks_editable(assessment):
    if results_locked(assessment.section, assessment.term):
        raise BusinessRuleViolation(f"{assessment.term} results for {assessment.section.label} are finalized; "
                                    "marks can no longer be changed.", code="results_finalized")


@transaction.atomic
def save_marks(assessment, rows, *, user, request=None):
    """rows: [{"student": id, "score": n, "remarks": ""}]"""
    if not can_enter_marks(user, assessment.section, assessment.subject):
        raise BusinessRuleViolation("Only the subject teacher for this class can enter these marks.",
                                    code="not_your_subject")
    ensure_marks_editable(assessment)
    members = {s.id for s in pupils_in(assessment.section)}
    errors = {}
    for i, row in enumerate(rows):
        try:
            score = Decimal(str(row.get("score")))
        except Exception:
            score = None
        if row.get("student") not in members:
            errors[str(i)] = ["This pupil is not in the class."]
        elif score is None or score < 0 or score > assessment.max_score:
            errors[str(i)] = [f"Score must be between 0 and {assessment.max_score}."]
    if errors:
        raise BusinessRuleViolation("Some marks are invalid.", code="invalid_marks", fields=errors)
    for row in rows:
        SchoolMark.objects.update_or_create(
            assessment=assessment, student_id=row["student"],
            defaults={"tenant": assessment.tenant, "score": Decimal(str(row["score"])),
                      "remarks": row.get("remarks", ""), "recorded_by": user})
    log_event("marks.recorded", request=request, actor=user, target=assessment, changes={"rows": len(rows)})
    return len(rows)


def compute_results(section, term):
    """Weighted subject averages per pupil. Returns (results, missing) without saving anything."""
    tenant = section.tenant
    pupils = list(pupils_in(section))
    subjects = [a.subject for a in section.assignments.select_related("subject")]
    assessments = list(SchoolAssessment.objects.filter(section=section, term=term, weight__gt=0)
                       .select_related("subject"))
    marks = {(m.assessment_id, m.student_id): m.score
             for m in SchoolMark.objects.filter(assessment__in=assessments)}
    by_subject = defaultdict(list)
    for a in assessments:
        by_subject[a.subject_id].append(a)
    missing = []
    for subj in subjects:
        if not by_subject.get(subj.id):
            missing.append(f"{subj.name}: no graded assessments")
    results = []
    for p in pupils:
        subject_rows = []
        for subj in subjects:
            items = by_subject.get(subj.id, [])
            got = [(a, marks.get((a.id, p.id))) for a in items]
            gaps = [a.name for a, m in got if m is None]
            if gaps:
                missing.append(f"{p.person.full_name} – {subj.name}: {', '.join(gaps)}")
                continue
            if not items:
                continue
            total_w = sum(Decimal(a.weight) for a in items)
            avg = q2(sum(Decimal(m) / Decimal(a.max_score) * Decimal(a.weight) for a, m in got) / total_w * 100)
            band = tenant.grade_for(avg)
            subject_rows.append({"subject_id": subj.id, "code": subj.code, "name": subj.name, "average": str(avg),
                                 "grade": band["grade"], "points": band["points"], "remark": band.get("remark", "")})
        avg = (q2(sum(Decimal(r["average"]) for r in subject_rows) / len(subject_rows)) if subject_rows else None)
        results.append({"student": p, "subjects": subject_rows, "average": avg,
                        "grade": tenant.grade_for(avg)["grade"] if avg is not None else None})
    ranked = sorted([r for r in results if r["average"] is not None], key=lambda r: r["average"], reverse=True)
    position, last = 0, None
    for i, r in enumerate(ranked, start=1):
        if r["average"] != last:
            position, last = i, r["average"]
        r["position"] = position
    return results, missing


def _require(user, code, message):
    if not user.has_perm_code(code):
        raise BusinessRuleViolation(message, code="not_authorised")


@transaction.atomic
def finalize_results(section, term, *, user, request=None):
    _require(user, "school.results.publish", "Only the principal can finalize term results.")
    if term.parent_id != section.academic_year_id:
        raise BusinessRuleViolation("That term is not part of this class's academic year.", code="wrong_term")
    if results_locked(section, term):
        raise BusinessRuleViolation(f"{term} results for {section.label} are already finalized.",
                                    code="already_finalized")
    results, missing = compute_results(section, term)
    if missing:
        raise BusinessRuleViolation(f"Marks are incomplete ({len(missing)} gaps). First: {missing[0]}.",
                                    code="marks_incomplete", fields={"missing": missing[:50]})
    if not results:
        raise BusinessRuleViolation("There are no pupils in this class.", code="no_pupils")
    now = timezone.localtime()
    created = []
    for r in results:
        att = attendance_summary(r["student"], term.start_date, term.end_date)
        created.append(TermResult(
            tenant=section.tenant, student=r["student"], section=section, term=term, subjects=r["subjects"],
            average=r["average"], grade=r["grade"], position=r.get("position"), class_size=len(results),
            days_present=att["present"] + att["late"], days_absent=att["absent"] + att["excused"],
            finalized_by=user, finalized_at=now))
    TermResult.objects.bulk_create(created)
    log_event("results.finalized", request=request, actor=user, target=section,
              changes={"term": term.name, "pupils": len(created)})
    return created


@transaction.atomic
def reopen_results(section, term, *, user, request=None):
    _require(user, "school.results.publish", "Only the principal can reopen term results.")
    qs = TermResult.objects.filter(section=section, term=term)
    if not qs.exists():
        raise BusinessRuleViolation("These results are not finalized.", code="not_finalized")
    if qs.filter(status="published").exists():
        raise BusinessRuleViolation("Published report cards can't be reopened.", code="already_published")
    if PromotionDecision.objects.filter(section=section).exists():
        raise BusinessRuleViolation("Promotion decisions have been made for this class.", code="decisions_made")
    n = qs.count()
    qs.delete()
    log_event("results.reopened", request=request, actor=user, target=section, changes={"term": term.name})
    return n


@transaction.atomic
def publish_results(section, term, *, user, request=None):
    _require(user, "school.results.publish", "Only the principal can publish report cards.")
    qs = TermResult.objects.filter(section=section, term=term).select_related("student__person")
    if not qs.exists():
        raise BusinessRuleViolation("Finalize the results before publishing report cards.", code="not_finalized")
    if not qs.filter(status="finalized").exists():
        raise BusinessRuleViolation("These report cards are already published.", code="already_published")
    now = timezone.now()
    results = list(qs)
    qs.update(status="published", published_at=now)
    for r in results:
        notify(family_of(r.student), f"{term} report card available",
               f"{r.student.person.first_name}'s report card for {term} has been published.", kind="results",
               link="/school/report-cards")
    log_event("results.published", request=request, actor=user, target=section,
              changes={"term": term.name, "pupils": len(results)})
    return len(results)


# =========================================================================== promotion
def year_record(student, section):
    """Finalized term results for the class's year, the year average and the recommendation."""
    terms = list(section.terms())
    results = {r.term_id: r for r in TermResult.objects.filter(student=student, section__academic_year=
                                                               section.academic_year)}
    missing = [t.name for t in terms if t.id not in results]
    avg = q2(sum(Decimal(r.average) for r in results.values()) / len(results)) if results else None
    min_avg = policy(section.tenant, "promotion_min_average")
    if avg is None:
        rec = None
    elif avg >= min_avg:
        rec = "complete" if section.grade_level.is_final else "promote"
    else:
        rec = "repeat"
    return {"terms": [{"term": t.name, "average": results[t.id].average if t.id in results else None,
                       "status": results[t.id].status if t.id in results else "not_finalized"} for t in terms],
            "missing": missing, "average": avg, "recommended": rec, "min_average": min_avg}


def _next_year(year):
    return (AcademicPeriod.objects.filter(tenant=year.tenant, kind="academic_year", start_date__gt=year.end_date)
            .order_by("start_date").first())


@transaction.atomic
def decide_promotion(student, section, decision, *, user, reason="", request=None):
    _require(user, "school.promotion.decide", "Only the principal or administrator can decide promotions.")
    if student.tenant_id != section.tenant_id:
        raise BusinessRuleViolation("Pupil not found.", code="not_found")
    placement = ClassPlacement.objects.filter(student=student, section=section).exclude(status="moved").first()
    if placement is None:
        raise BusinessRuleViolation(f"{student.person.full_name} is not in {section.label}.", code="not_in_class")
    if PromotionDecision.objects.filter(student=student, academic_year=section.academic_year).exists():
        raise BusinessRuleViolation("A decision has already been recorded for this pupil this year.",
                                    code="already_decided")
    record = year_record(student, section)
    if record["missing"]:
        raise BusinessRuleViolation(
            f"Results are not finalized for: {', '.join(record['missing'])}. Finalize all terms first.",
            code="results_not_finalized", fields={"missing_terms": record["missing"]})
    level = section.grade_level
    if decision == "complete" and not level.is_final:
        raise BusinessRuleViolation(f"Only pupils in the final grade can complete school ({level} is not final).",
                                    code="invalid_decision")
    if decision == "promote" and (level.is_final or level.next_level() is None):
        raise BusinessRuleViolation(f"{level} is the final grade; record completion instead.",
                                    code="invalid_decision")
    if decision not in ("promote", "repeat", "complete"):
        raise BusinessRuleViolation("Choose promote, repeat or complete.", code="invalid_decision")
    if decision != record["recommended"] and not reason.strip():
        raise BusinessRuleViolation(
            f"The recommendation is to {record['recommended']} (year average {record['average']}). "
            "Give a reason to decide otherwise.", code="reason_required", fields={"reason": ["Required."]})
    to_level = level.next_level() if decision == "promote" else (level if decision == "repeat" else None)
    d = PromotionDecision.objects.create(
        tenant=student.tenant, student=student, section=section, academic_year=section.academic_year,
        decision=decision, from_level=level, to_level=to_level, year_average=record["average"],
        recommended=record["recommended"], reason=reason, decided_by=user)

    today = timezone.localdate()
    end = min(today, section.academic_year.end_date) if today >= section.academic_year.start_date else today
    placement.status, placement.end_date = "ended", end
    placement.save(update_fields=["status", "end_date", "updated_at"])
    status_map = {"promote": "promoted", "repeat": "repeated", "complete": "completed"}
    Enrollment.objects.filter(student=student, status="active").update(
        status=status_map[decision], end_date=end, reason=f"{d.get_decision_display()} – year average {d.year_average}")
    if decision == "complete":
        student.status = "completed"
        student.save(update_fields=["status"])
        msg = f"{student.person.first_name} has completed {level} and finished school. Congratulations!"
    else:
        nxt = _next_year(section.academic_year)
        Enrollment.objects.create(
            tenant=student.tenant, student=student, period=nxt, level_label=to_level.name, section_label="",
            start_date=nxt.start_date if nxt else today, recorded_by=user,
            reason=(f"Promoted from {level}" if decision == "promote" else f"Repeating {level}"))
        student.current_level, student.current_section = to_level.name, ""
        student.save(update_fields=["current_level", "current_section"])
        msg = (f"{student.person.first_name} is promoted to {to_level} for "
               f"{nxt.name if nxt else 'next year'}." if decision == "promote"
               else f"{student.person.first_name} will repeat {level} next year.")
    notify(family_of(student), "End-of-year decision", msg, kind="results")
    log_event(f"promotion.{decision}", request=request, actor=user, target=student,
              changes={"from": level.name, "to": to_level.name if to_level else None,
                       "average": str(record["average"]), "recommended": record["recommended"], "reason": reason})
    return d


def end_placements(student, on=None):
    """Used when a pupil is withdrawn or transferred out through the shared enrollment workflow."""
    ClassPlacement.objects.filter(student=student, status="active").update(
        status="ended", end_date=on or timezone.localdate())


def weekly_attendance(tenant, weeks=8):
    """Attendance % per school week (daily registers), most recent `weeks` weeks."""
    today = timezone.localdate()
    since = today - timezone.timedelta(weeks=weeks)
    rows = PupilAttendance.objects.filter(tenant=tenant, lesson__isnull=True, date__gte=since, date__lte=today) \
        .values_list("date", "status")
    buckets = defaultdict(lambda: [0, 0])
    for d, s in rows:
        monday = d - timezone.timedelta(days=d.weekday())
        buckets[monday][1] += 1
        if s in ("present", "late"):
            buckets[monday][0] += 1
    return [{"label": f"{m:%d %b}", "value": round(100 * a / n, 1)} for m, (a, n) in sorted(buckets.items()) if n]


def pass_rate(results, pass_mark):
    results = list(results)
    if not results:
        return None
    return round(100 * sum(Decimal(r.average) >= pass_mark for r in results) / len(results), 1)


def visible_results(user):
    """Term results a user may see: families only see published report cards."""
    from people.scoping import visible_students

    qs = TermResult.objects.filter(student__in=visible_students(user)).select_related(
        "student__person", "section__grade_level", "term")
    if not user.has_perm_code("students.view", "school.marks.enter", "school.results.publish"):
        qs = qs.filter(status="published")
    return qs


def lessons_for(section):
    return SchoolTimetable.objects.filter(assignment__section=section).select_related(
        "assignment__subject", "assignment__teacher")


def teacher_lessons(user, year):
    return SchoolTimetable.objects.filter(assignment__teacher=user, assignment__section__academic_year=year) \
        .select_related("assignment__subject", "assignment__section__grade_level")


def school_days_between(start, end):
    d, out = start, []
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timezone.timedelta(days=1)
    return out

