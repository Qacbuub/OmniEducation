"""
University business rules. Views stay thin; every rule lives here so it is enforced the same way
from the API, the admin, the seed script and the tests.

Policies come from Tenant.policies (defaults in core.models.UNIVERSITY_POLICIES):
  min_credits / max_credits / overload_max_credits / overload_min_cgpa, probation_cgpa,
  graduation_min_cgpa, pass_grade_points, repeat_policy, max_course_attempts,
  registration_requires_approval.
"""
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from comms.services import notify
from core.audit import log_event
from core.exceptions import BusinessRuleViolation

from .models import (
    AcademicStanding,
    AssessmentScore,
    CoursePrerequisite,
    CourseOffering,
    CourseRegistration,
    GradeApproval,
    OfferingMeeting,
    TranscriptEntry,
    UniversityGrade,
)

EXTRA_DEFAULTS = {"max_course_attempts": 3, "registration_requires_approval": True}
TWO = Decimal("0.01")


def policy(tenant, key):
    value = tenant.policy(key)
    return EXTRA_DEFAULTS.get(key) if value is None else value


def q2(value):
    return Decimal(value).quantize(TWO, rounding=ROUND_HALF_UP)


# =========================================================================== GPA / CGPA
def current_entries(student):
    """Transcript entries that have not been superseded by an amendment."""
    return (TranscriptEntry.objects.filter(student=student, superseded_by__isnull=True)
            .select_related("semester__period").order_by("semester__period__start_date", "id"))


def counted_entries(student, entries=None):
    """Apply the repeat-course policy: which attempts count toward CGPA and earned credits."""
    entries = list(entries if entries is not None else current_entries(student))
    rule = policy(student.tenant, "repeat_policy")
    if rule == "all_attempts":
        return entries
    by_course = defaultdict(list)
    for e in entries:
        by_course[e.course_id].append(e)
    chosen = []
    for attempts in by_course.values():
        if rule == "highest_attempt":
            chosen.append(max(attempts, key=lambda e: (e.grade_points, e.attempt_no)))
        else:  # latest_attempt (default)
            chosen.append(max(attempts, key=lambda e: (e.attempt_no, e.id)))
    return sorted(chosen, key=lambda e: (e.semester.period.start_date, e.id))


def gpa(entries):
    credits = sum(e.credit_hours for e in entries)
    if not credits:
        return None
    points = sum(Decimal(e.grade_points) * e.credit_hours for e in entries)
    return q2(points / credits)


def academic_summary(student):
    tenant = student.tenant
    entries = list(current_entries(student))
    counted = counted_entries(student, entries)
    counted_ids = {e.id for e in counted}
    pass_points = Decimal(str(policy(tenant, "pass_grade_points")))
    semesters = []
    by_sem = defaultdict(list)
    for e in entries:
        by_sem[e.semester_id].append(e)
    running = []
    for sem_entries in by_sem.values():
        sem = sem_entries[0].semester
        running.extend(e for e in sem_entries if e.id in counted_ids)
        semesters.append({
            "semester_id": sem.id, "semester": sem.period.name,
            "credits": sum(e.credit_hours for e in sem_entries), "gpa": gpa(sem_entries),
            "cgpa_to_date": gpa(counted_entries(student, [x for x in entries if x.semester.period.start_date
                                                          <= sem.period.start_date])),
            "entries": sem_entries,
        })
    cgpa = gpa(counted)
    return {
        "entries": entries, "counted_ids": counted_ids, "semesters": semesters, "cgpa": cgpa,
        "credits_attempted": sum(e.credit_hours for e in counted),
        "credits_earned": sum(e.credit_hours for e in counted if Decimal(e.grade_points) >= pass_points),
    }


def recompute_standing(student):
    standing = AcademicStanding.objects.filter(student=student).first()
    if standing is None:
        return None
    s = academic_summary(student)
    standing.cgpa = s["cgpa"]
    standing.credits_attempted = s["credits_attempted"]
    standing.credits_earned = s["credits_earned"]
    probation_at = Decimal(str(policy(student.tenant, "probation_cgpa")))
    old = standing.standing
    standing.standing = (AcademicStanding.Standing.PROBATION if s["cgpa"] is not None and s["cgpa"] < probation_at
                         else AcademicStanding.Standing.GOOD)
    standing.save(update_fields=["cgpa", "credits_attempted", "credits_earned", "standing", "updated_at"])
    if old != standing.standing and student.user_id:
        if standing.standing == "probation":
            notify([student.user], "Academic probation",
                   f"Your CGPA is {s['cgpa']}, below {probation_at}. Please meet your academic adviser.",
                   kind="grade", link="/university/transcript")
        else:
            notify([student.user], "Back in good standing", f"Your CGPA is now {s['cgpa']}.", kind="grade")
    return standing


def passed_course(student, course):
    pass_points = Decimal(str(policy(student.tenant, "pass_grade_points")))
    return any(Decimal(e.grade_points) >= pass_points for e in current_entries(student).filter(course=course))


# =========================================================================== registration
def _active_regs(student, semester):
    return (CourseRegistration.objects.filter(student=student, offering__semester=semester,
                                              status__in=CourseRegistration.ACTIVE)
            .select_related("offering__course"))


def credit_limit(student):
    tenant = student.tenant
    standing = getattr(student, "academic_standing", None)
    limit = int(policy(tenant, "max_credits"))
    if standing and standing.cgpa is not None and standing.cgpa >= Decimal(str(policy(tenant, "overload_min_cgpa"))):
        limit = int(policy(tenant, "overload_max_credits"))
    return limit


def find_time_conflict(meetings, other_meetings):
    for m in meetings:
        for o in other_meetings:
            if m.overlaps(o):
                return m, o
    return None


def check_registration(student, offering, today=None):
    """Raise BusinessRuleViolation if the student may not register for this section. Returns attempt number."""
    today = today or timezone.localdate()
    course, semester = offering.course, offering.semester
    if student.tenant_id != offering.tenant_id:
        raise BusinessRuleViolation("Section not found.", code="not_found")
    if student.status != "active":
        raise BusinessRuleViolation("Only active students can register for courses.", code="student_not_active")
    if not hasattr(student, "academic_standing"):
        raise BusinessRuleViolation("The student has not been matriculated into a program.", code="not_matriculated")
    if offering.status != CourseOffering.Status.OPEN:
        raise BusinessRuleViolation(f"{course.code}-{offering.section} is not open for registration.",
                                    code="section_not_open")
    if not semester.window_open(today):
        raise BusinessRuleViolation(
            f"Registration for {semester} is open from {semester.registration_start:%d %b} to "
            f"{semester.add_drop_end:%d %b %Y}.", code="registration_closed")

    active = list(_active_regs(student, semester))
    if any(r.offering.course_id == course.id for r in active):
        raise BusinessRuleViolation(f"You are already registered for {course.code} this semester.",
                                    code="duplicate_registration")

    # Repeat-course policy
    previous_attempts = current_entries(student).filter(course=course).count()
    if passed_course(student, course):
        raise BusinessRuleViolation(f"{course.code} has already been passed and cannot be repeated.",
                                    code="course_already_passed")
    max_attempts = int(policy(student.tenant, "max_course_attempts"))
    if previous_attempts >= max_attempts:
        raise BusinessRuleViolation(f"{course.code} may be attempted at most {max_attempts} times.",
                                    code="max_attempts_reached")

    # Prerequisites
    missing = []
    for link in CoursePrerequisite.objects.filter(course=course).select_related("prerequisite"):
        best = max((Decimal(e.grade_points) for e in current_entries(student).filter(course=link.prerequisite)),
                   default=None)
        if best is None or best < link.min_grade_points:
            missing.append(link.prerequisite.code)
    if missing:
        raise BusinessRuleViolation(f"Prerequisites not met for {course.code}: {', '.join(missing)}.",
                                    code="prerequisite_not_met", fields={"missing_prerequisites": missing})

    # Seat capacity
    taken = offering.registrations.filter(status__in=CourseRegistration.ACTIVE).count()
    if taken >= offering.capacity:
        raise BusinessRuleViolation(f"{course.code}-{offering.section} is full ({offering.capacity} seats).",
                                    code="section_full")

    # Timetable conflicts
    new_meetings = list(offering.meetings.all())
    other_meetings = list(OfferingMeeting.objects.filter(offering__in=[r.offering for r in active])
                          .select_related("offering__course"))
    clash = find_time_conflict(new_meetings, other_meetings)
    if clash:
        mine, other = clash
        raise BusinessRuleViolation(
            f"{course.code} ({mine}) clashes with {other.offering.course.code} ({other}).", code="timetable_conflict")

    # Credit limit
    load = sum(r.offering.course.credit_hours for r in active) + course.credit_hours
    limit = credit_limit(student)
    if load > limit:
        raise BusinessRuleViolation(f"This would bring you to {load} credits; the limit is {limit}.",
                                    code="credit_limit_exceeded")
    return previous_attempts + 1


@transaction.atomic
def register(student, offering, *, user, request=None):
    offering = CourseOffering.objects.select_for_update().select_related("course", "semester__period").get(
        pk=offering.pk)  # serialises seat counting for this section
    attempt = check_registration(student, offering)
    needs_approval = bool(policy(student.tenant, "registration_requires_approval"))
    staff_approver = user.has_perm_code("uni.registration.approve") and student.user_id != user.id
    reg = CourseRegistration.objects.create(
        tenant=student.tenant, student=student, offering=offering, attempt_no=attempt, requested_by=user,
        status="approved" if (staff_approver or not needs_approval) else "pending",
        decided_by=user if staff_approver else None, decided_at=timezone.now() if staff_approver else None)
    log_event("registration.created", request=request, actor=user, target=reg,
              changes={"course": offering.course.code, "section": offering.section, "status": reg.status,
                       "attempt": attempt})
    if reg.status == "pending":
        standing = student.academic_standing
        if standing.adviser_id:
            notify([standing.adviser], "Course registration to approve",
                   f"{student.person.full_name} requested {offering.course.code}.", kind="registration",
                   link="/university/registration")
    return reg


@transaction.atomic
def decide_registration(reg, *, approve, user, notes="", request=None):
    reg = CourseRegistration.objects.select_for_update().get(pk=reg.pk)
    if reg.status != "pending":
        raise BusinessRuleViolation("Only pending registrations can be approved or rejected.",
                                    code="registration_not_pending")
    if approve:
        offering = CourseOffering.objects.select_for_update().get(pk=reg.offering_id)
        taken = offering.registrations.filter(status="approved").count()
        if taken >= offering.capacity:
            raise BusinessRuleViolation("The section filled up before this request was approved.",
                                        code="section_full")
    reg.status = "approved" if approve else "rejected"
    reg.decided_by, reg.decided_at, reg.decision_notes = user, timezone.now(), notes
    reg.save()
    log_event(f"registration.{reg.status}", request=request, actor=user, target=reg, changes={"notes": notes})
    if reg.student.user_id:
        notify([reg.student.user], f"{reg.offering.course.code} registration {reg.status}", notes,
               kind="registration", link="/university/registration")
    return reg


@transaction.atomic
def drop_registration(reg, *, user, reason="", request=None, today=None):
    today = today or timezone.localdate()
    reg = CourseRegistration.objects.select_for_update().select_related("offering__semester").get(pk=reg.pk)
    if reg.status not in CourseRegistration.ACTIVE:
        raise BusinessRuleViolation("This registration is not active.", code="registration_not_active")
    if today > reg.offering.semester.add_drop_end:
        raise BusinessRuleViolation(f"The add/drop window closed on {reg.offering.semester.add_drop_end:%d %b %Y}.",
                                    code="add_drop_closed")
    if hasattr(reg, "grade") and reg.grade.status in ("submitted", "approved"):
        raise BusinessRuleViolation("A course with submitted grades cannot be dropped.", code="grades_submitted")
    reg.status, reg.dropped_at, reg.decision_notes = "dropped", timezone.now(), reason
    reg.save()
    log_event("registration.dropped", request=request, actor=user, target=reg, changes={"reason": reason})
    return reg


def check_offering_schedule(offering, meetings_data, exclude_offering_id=None):
    """Reject a lecturer double-booking or a room double-booking within the same semester."""
    same_sem = OfferingMeeting.objects.filter(offering__semester=offering.semester).exclude(
        offering__status="cancelled").select_related("offering__course")
    if exclude_offering_id:
        same_sem = same_sem.exclude(offering_id=exclude_offering_id)
    for i, m in enumerate(meetings_data):
        candidate = OfferingMeeting(day=m["day"], start_time=m["start_time"], end_time=m["end_time"])
        if m["end_time"] <= m["start_time"]:
            raise BusinessRuleViolation("A meeting must end after it starts.", code="invalid_meeting_time")
        for j, other in enumerate(meetings_data):
            if j > i and candidate.overlaps(OfferingMeeting(day=other["day"], start_time=other["start_time"],
                                                            end_time=other["end_time"])):
                raise BusinessRuleViolation("Two meetings of this section overlap.", code="timetable_conflict")
        for existing in same_sem:
            if not candidate.overlaps(existing):
                continue
            if offering.lecturer_id and existing.offering.lecturer_id == offering.lecturer_id:
                raise BusinessRuleViolation(
                    f"The lecturer already teaches {existing.offering.course.code} at {existing}.",
                    code="lecturer_schedule_conflict")
            if m.get("room") and existing.room and existing.room.lower() == m["room"].lower():
                raise BusinessRuleViolation(f"Room {existing.room} is booked for {existing.offering.course.code} "
                                            f"at {existing}.", code="room_conflict")


# =========================================================================== grading
def grade_band(tenant, score):
    band = tenant.grade_for(score)
    return band["grade"], q2(band["points"])


def compute_total(registration, assessments):
    scores = {s.assessment_id: s.score for s in registration.scores.all()}
    total = Decimal(0)
    for a in assessments:
        if a.id not in scores:
            return None
        total += Decimal(scores[a.id]) / Decimal(a.max_score) * Decimal(a.weight)
    return q2(total)


def offering_grade_state(offering):
    grades = UniversityGrade.objects.filter(registration__offering=offering)
    statuses = set(grades.values_list("status", flat=True))
    for s in ("approved", "submitted", "returned", "draft"):
        if s in statuses:
            return s
    if AssessmentScore.objects.filter(assessment__offering=offering).exists():
        return "in_progress"
    return "not_started"


def ensure_scores_editable(offering):
    state = offering_grade_state(offering)
    if state in ("submitted", "approved"):
        raise BusinessRuleViolation(
            "Grades for this section have been submitted" + (" and approved" if state == "approved" else "") +
            ". Scores can no longer be changed.", code="grades_locked")


def can_teach(user, offering):
    return offering.lecturer_id == user.id


@transaction.atomic
def submit_grades(offering, *, user, request=None):
    if not can_teach(user, offering):
        raise BusinessRuleViolation("Only the assigned lecturer can submit grades for this section.",
                                    code="not_assigned_lecturer")
    ensure_scores_editable(offering)
    assessments = list(offering.assessments.all())
    weight = sum(Decimal(a.weight) for a in assessments)
    if weight != 100:
        raise BusinessRuleViolation(f"Assessment weights must add up to 100% (currently {weight}%).",
                                    code="weights_incomplete")
    regs = list(offering.registrations.filter(status="approved").select_related("student__person")
                .prefetch_related("scores"))
    if not regs:
        raise BusinessRuleViolation("There are no registered students to grade.", code="no_students")
    missing = [r.student.person.full_name for r in regs if compute_total(r, assessments) is None]
    if missing:
        raise BusinessRuleViolation(f"Missing scores for: {', '.join(missing[:5])}"
                                    f"{' and others' if len(missing) > 5 else ''}.", code="scores_incomplete")
    now = timezone.now()
    for r in regs:
        total = compute_total(r, assessments)
        letter, points = grade_band(offering.tenant, total)
        UniversityGrade.objects.update_or_create(
            registration=r, defaults={"tenant": offering.tenant, "total_score": total, "letter": letter,
                                      "grade_points": points, "status": "submitted", "submitted_by": user,
                                      "submitted_at": now})
    GradeApproval.objects.create(tenant=offering.tenant, offering=offering, action="submitted", actor=user,
                                 details={"students": len(regs)})
    log_event("grades.submitted", request=request, actor=user, target=offering, changes={"students": len(regs)})
    from comms.services import notify_permission_holders
    notify_permission_holders(offering.tenant, "uni.grades.approve", f"Grades submitted: {offering.course.code}",
                              f"{user.get_full_name()} submitted grades for {offering}.", kind="grade",
                              link="/university/grade-approvals")
    return regs


def can_approve(user, offering):
    """Registrar: any section. Dean: own faculty. Department head: own department."""
    if not user.has_perm_code("uni.grades.approve"):
        return False
    dept = offering.course.department
    if user.role_code == "dept_head":
        return dept.head_id == user.id
    if user.role_code == "dean":
        return dept.faculty.dean_id == user.id
    return True


@transaction.atomic
def moderate_grades(offering, *, user, approve, notes="", request=None):
    if not can_approve(user, offering):
        raise BusinessRuleViolation("You can only approve grades for courses in your own department or faculty.",
                                    code="not_authorised_to_approve")
    if offering.lecturer_id == user.id:
        raise BusinessRuleViolation("Lecturers cannot approve their own grades.", code="self_approval")
    grades = list(UniversityGrade.objects.select_for_update().filter(registration__offering=offering,
                                                                     status="submitted")
                  .select_related("registration__student__person", "registration__offering__course"))
    if not grades:
        raise BusinessRuleViolation("There are no submitted grades waiting for approval.", code="nothing_to_approve")
    if not approve and not notes:
        raise BusinessRuleViolation("Give a reason when returning grades.", code="reason_required",
                                    fields={"notes": ["Required when returning grades."]})
    now = timezone.now()
    action = "approved" if approve else "returned"
    for g in grades:
        g.status = action
        if approve:
            g.approved_by, g.approved_at = user, now
        g.save()
        if approve:
            reg = g.registration
            TranscriptEntry.objects.create(
                tenant=offering.tenant, student=reg.student, registration=reg, course=offering.course,
                semester=offering.semester, course_code=offering.course.code, course_title=offering.course.title,
                credit_hours=offering.course.credit_hours, total_score=g.total_score, letter=g.letter,
                grade_points=g.grade_points, attempt_no=reg.attempt_no, approved_by=user)
    GradeApproval.objects.create(tenant=offering.tenant, offering=offering, action=action, actor=user, notes=notes,
                                 details={"students": len(grades)})
    log_event(f"grades.{action}", request=request, actor=user, target=offering,
              changes={"students": len(grades), "notes": notes})
    if approve:
        for g in grades:
            student = g.registration.student
            recompute_standing(student)
            if student.user_id:
                notify([student.user], f"Final grade released: {offering.course.code}",
                       f"Your grade is {g.letter}.", kind="grade", link="/university/transcript")
    elif offering.lecturer_id:
        notify([offering.lecturer], f"Grades returned: {offering.course.code}", notes, kind="grade",
               link="/university/gradebook")
    return grades


@transaction.atomic
def amend_grade(grade, *, user, total_score, reason, request=None):
    """Change an approved grade. Only holders of uni.transcripts.issue (registrar); always audited."""
    if not user.has_perm_code("uni.transcripts.issue"):
        raise BusinessRuleViolation("Approved grades can only be changed by the registrar through an amendment.",
                                    code="unauthorised_grade_change")
    if grade.status != "approved":
        raise BusinessRuleViolation("Only approved grades can be amended.", code="grade_not_approved")
    if not reason:
        raise BusinessRuleViolation("A reason is required for a grade amendment.", code="reason_required",
                                    fields={"reason": ["Required."]})
    total_score = q2(total_score)
    if not (0 <= total_score <= 100):
        raise BusinessRuleViolation("The total score must be between 0 and 100.", code="invalid_score",
                                    fields={"total_score": ["Must be between 0 and 100."]})
    reg = grade.registration
    previous = TranscriptEntry.objects.filter(registration=reg, superseded_by__isnull=True).first()
    old = {"total_score": str(grade.total_score), "letter": grade.letter}
    letter, points = grade_band(grade.tenant, total_score)
    grade.total_score, grade.letter, grade.grade_points = total_score, letter, points
    grade.save()
    offering = reg.offering
    TranscriptEntry.objects.create(
        tenant=grade.tenant, student=reg.student, registration=reg, course=offering.course, semester=offering.semester,
        course_code=offering.course.code, course_title=offering.course.title, credit_hours=offering.course.credit_hours,
        total_score=total_score, letter=letter, grade_points=points, attempt_no=reg.attempt_no, approved_by=user,
        supersedes=previous, reason=reason)
    GradeApproval.objects.create(tenant=grade.tenant, offering=offering, grade=grade, action="amended", actor=user,
                                 notes=reason, details={"from": old, "to": {"total_score": str(total_score),
                                                                           "letter": letter}})
    log_event("grade.amended", request=request, actor=user, target=grade,
              changes={"from": old, "to": {"total_score": str(total_score), "letter": letter}, "reason": reason})
    recompute_standing(reg.student)
    return grade


def save_scores(offering, rows, *, user):
    """rows: [{"assessment": id, "registration": id, "score": n}]"""
    if not can_teach(user, offering):
        raise BusinessRuleViolation("Only the assigned lecturer can enter scores for this section.",
                                    code="not_assigned_lecturer")
    ensure_scores_editable(offering)
    assessments = {a.id: a for a in offering.assessments.all()}
    regs = {r.id: r for r in offering.registrations.filter(status="approved")}
    saved = 0
    errors = {}
    for i, row in enumerate(rows):
        a, r = assessments.get(row.get("assessment")), regs.get(row.get("registration"))
        try:
            score = Decimal(str(row.get("score")))
        except Exception:
            score = None
        if a is None or r is None:
            errors[str(i)] = ["Unknown assessment or student for this section."]
        elif score is None or score < 0 or score > a.max_score:
            errors[str(i)] = [f"Score must be between 0 and {a.max_score}."]
    if errors:
        raise BusinessRuleViolation("Some scores are invalid.", code="invalid_scores", fields=errors)
    with transaction.atomic():
        for row in rows:
            AssessmentScore.objects.update_or_create(
                assessment_id=row["assessment"], registration_id=row["registration"],
                defaults={"tenant": offering.tenant, "score": Decimal(str(row["score"])), "recorded_by": user})
            saved += 1
        # Returned grades go back to draft once the lecturer edits them.
        UniversityGrade.objects.filter(registration__offering=offering, status="returned").update(status="draft")
    return saved


# =========================================================================== degree audit / clearance
def degree_audit(student):
    standing = getattr(student, "academic_standing", None)
    if standing is None:
        raise BusinessRuleViolation("The student has not been matriculated into a program.", code="not_matriculated")
    tenant = student.tenant
    program = standing.program
    curriculum = standing.curriculum or program.current_curriculum()
    summary = academic_summary(student)
    pass_points = Decimal(str(policy(tenant, "pass_grade_points")))
    counted = [e for e in summary["entries"] if e.id in summary["counted_ids"]]
    passed = {e.course_id: e for e in counted if Decimal(e.grade_points) >= pass_points}
    in_progress = set(CourseRegistration.objects.filter(student=student, status__in=["approved", "pending"])
                      .exclude(grade__status="approved").values_list("offering__course_id", flat=True))
    core, electives = [], []
    if curriculum:
        for item in curriculum.items.select_related("course"):
            c = item.course
            entry = passed.get(c.id)
            row = {"course_id": c.id, "code": c.code, "title": c.title, "credits": c.credit_hours,
                   "year": item.recommended_year, "semester": item.recommended_semester,
                   "status": "completed" if entry else ("in_progress" if c.id in in_progress else "missing"),
                   "grade": entry.letter if entry else None}
            (core if item.category == "core" else electives).append(row)
    elective_ids = {r["course_id"] for r in electives}
    elective_credits = sum(r["credits"] for r in electives if r["status"] == "completed")
    # Passed courses outside the curriculum count as free electives.
    core_ids = {r["course_id"] for r in core}
    free_credits = sum(e.credit_hours for cid, e in passed.items() if cid not in core_ids | elective_ids)
    elective_needed = curriculum.elective_credits_required if curriculum else 0
    min_cgpa = Decimal(str(policy(tenant, "graduation_min_cgpa")))
    checks = [
        {"key": "core", "label": "All core courses passed",
         "met": all(r["status"] == "completed" for r in core),
         "detail": f"{sum(r['status'] == 'completed' for r in core)} of {len(core)} core courses"},
        {"key": "electives", "label": f"{elective_needed} elective credits",
         "met": elective_credits + free_credits >= elective_needed,
         "detail": f"{elective_credits + free_credits} of {elective_needed} credits"},
        {"key": "credits", "label": f"{program.total_credits_required} total credits",
         "met": summary["credits_earned"] >= program.total_credits_required,
         "detail": f"{summary['credits_earned']} of {program.total_credits_required} credits earned"},
        {"key": "cgpa", "label": f"CGPA of at least {min_cgpa}",
         "met": summary["cgpa"] is not None and summary["cgpa"] >= min_cgpa,
         "detail": f"CGPA {summary['cgpa'] if summary['cgpa'] is not None else '—'}"},
    ]
    return {
        "student_id": student.id, "student_no": student.student_no, "name": student.person.full_name,
        "program": program.name, "curriculum": curriculum.version if curriculum else None,
        "cgpa": summary["cgpa"], "credits_earned": summary["credits_earned"],
        "credits_required": program.total_credits_required,
        "progress_pct": min(100, round(100 * summary["credits_earned"] / program.total_credits_required)),
        "core": core, "electives": electives, "elective_credits_earned": elective_credits + free_credits,
        "elective_credits_required": elective_needed, "checks": checks, "eligible": all(c["met"] for c in checks),
        "standing": standing.standing,
    }


def outstanding_balance(student):
    from finance.models import Invoice

    return (Invoice.objects.filter(student=student).exclude(status__in=["void", "draft"])
            .aggregate(t=Sum("balance"))["t"] or Decimal(0))
