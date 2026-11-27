# University module – business rules and API

The university module (`backend/university/`) adds programs, courses, semesters, course registration,
grading, GPA/CGPA, transcripts, degree audits and graduation clearance. It reuses the shared identity,
students, admissions, fees, documents and notifications, and keeps its own course/credit/semester logic
separate from the K-12 class/term logic.

## Configurable policies

Stored per institution in `Tenant.policies` (defaults in `core/models.py` and `university/services.py`):

| Policy | Default | Meaning |
|---|---|---|
| `min_credits` | 12 | Minimum semester load (shown as a warning, not enforced) |
| `max_credits` | 21 | Maximum semester load |
| `overload_max_credits` | 24 | Maximum load for students with a high CGPA |
| `overload_min_cgpa` | 3.5 | CGPA needed for the overload limit |
| `probation_cgpa` | 2.0 | CGPA below this puts a student on academic probation |
| `graduation_min_cgpa` | 2.0 | CGPA needed to graduate |
| `pass_grade_points` | 1.0 | Grade points needed to pass a course (D or better) |
| `repeat_policy` | `latest_attempt` | Which attempt counts for CGPA: `latest_attempt`, `highest_attempt` or `all_attempts` |
| `max_course_attempts` | 3 | Maximum attempts at one course |
| `registration_requires_approval` | true | Student self-registrations wait for adviser/registrar approval |

Grades use the institution's grading scale (default A=4.0 … F=0.0, see `UNIVERSITY_GRADING_SCALE`).

## Registration rules (enforced server-side in `services.check_registration`)

A registration is rejected with a structured error code when:

| Code | Rule |
|---|---|
| `registration_closed` | Today is outside the semester's registration/add-drop window |
| `section_not_open` | The section is closed or cancelled |
| `duplicate_registration` | The student already has this course (any section) this semester |
| `course_already_passed` | The course was passed before (repeats are only for failed courses) |
| `max_attempts_reached` | The student has used all allowed attempts |
| `prerequisite_not_met` | A prerequisite has not been passed with the required grade points |
| `section_full` | All seats are taken (checked with a row lock, and again at approval) |
| `timetable_conflict` | A class meeting overlaps one of the student's other courses |
| `credit_limit_exceeded` | The new load would exceed the student's credit limit |
| `not_matriculated` / `student_not_active` | The student has no program or is not active |

Drops are allowed only until the add/drop deadline (`add_drop_closed`), and never after grades are submitted.
Students register themselves (pending), and their adviser or the registrar approves or rejects. Registrations
made by an adviser or registrar are approved immediately. Advisers can only act for their own advisees.

Creating or editing a section rejects a lecturer teaching two classes at once (`lecturer_schedule_conflict`)
and two classes in the same room at once (`room_conflict`). Prerequisite cycles are rejected.

## Grading workflow

1. The assigned lecturer defines assessments for the section (weights may not exceed 100%).
2. The lecturer enters scores. Only the assigned lecturer can enter scores (`not_assigned_lecturer`).
3. The lecturer submits grades. Weights must total exactly 100% and every student needs every score.
   The final mark is the weighted total, mapped to a letter and grade points.
4. Moderation: the registrar (any course), the dean (own faculty) or the department head (own department)
   approves the section or returns it with a reason. Lecturers cannot approve their own grades.
5. On approval, an immutable **transcript entry** is written per student, CGPA and standing are recalculated,
   and students are notified. Students never see grades before approval.

After submission, scores are locked (`grades_locked`). An approved grade can only be changed by the registrar
through an **amendment** with a reason. The amendment adds a new transcript entry that supersedes the old one,
so the full history is kept, and it is written to the grade-approval history and the audit log. Transcript
entries and grade-approval history cannot be edited or deleted.

## Class attendance

Lecturers record attendance for each class meeting of their own sections (*Class attendance* page,
`GET/POST /api/universities/offerings/{id}/attendance/?date=`): present, late, absent or excused, with a note.
Only approved registrations appear; dates must be inside the semester and not in the future; saving a day again
updates it. Absent students get an in-app notification. The attendance rate is (present + late) ÷ (classes
recorded − excused); students see it per course on *My courses & marks*. The registrar can view and correct
any section.

## GPA, CGPA and standing

* Semester GPA = Σ(grade points × credits) ÷ Σ credits for that semester's entries.
* CGPA uses the same formula over all courses, applying the repeat policy (by default only the latest
  attempt of a repeated course counts).
* Credits earned = credits of counted courses passed with at least `pass_grade_points`.
* A CGPA below `probation_cgpa` puts the student on academic probation; they are notified when this changes.

## Degree audit and graduation clearance

The degree audit compares the student's record with their program's current curriculum: all core courses
passed, enough elective credits (passed courses outside the curriculum count as free electives), the
program's total credits, and the minimum graduation CGPA. A student (or the registrar) can request
clearance only when every check is met. The registrar clears the request only if the student is still
eligible and has no outstanding fees (`fees_outstanding`). Clearing marks the student and their enrollment
as graduated.

## API (all under `/api/universities/`)

| Endpoint | Purpose |
|---|---|
| `faculties/`, `departments/`, `programs/`, `courses/`, `prerequisites/`, `curricula/`, `curriculum-courses/` | Catalogue (read: any university user; write: `uni.programs.manage`) |
| `semesters/`, `semesters/current/` | Semester registration windows |
| `offerings/` (+ `mine/`, `{id}/roster/`, `{id}/gradebook/`, `{id}/scores/`, `{id}/submit-grades/`, `{id}/approve-grades/`, `{id}/return-grades/`) | Sections, timetable meetings and the grading workflow |
| `registrations/` (+ `{id}/approve/`, `{id}/reject/`, `{id}/drop/`, `summary/`) | Course registration and add/drop |
| `assessments/`, `grades/` (+ `{id}/amend/`), `grade-approvals/` | Assessments, final grades, approval queue and history |
| `transcripts/{student or "me"}/`, `transcripts/{student or "me"}/pdf/` | Transcript (JSON) and PDF. The registrar gets the official copy; students get an unofficial copy |
| `degree-audit/{student or "me"}/`, `clearances/` (+ `{id}/clear/`, `{id}/reject/`) | Degree audit and graduation clearance |
| `timetable/`, `standings/`, `catalog-stats/` | Weekly timetable, academic standing and catalogue counts |

Admissions: an application can name a program (`target_id`). When an accepted offer is enrolled, the student
is matriculated into the program with its current curriculum (and an optional adviser).
