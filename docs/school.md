# School (K-12) module – business rules and API

The school module (`backend/school/`) adds grade levels, class sections, subject allocation, timetables,
attendance, homework and assessments, weighted term results, report cards and promotion. It reuses the
shared identity, students, guardians, admissions, fees, documents and notifications, and keeps its
class/term/promotion logic separate from the university's course/credit/semester logic.

## Configurable policies

Stored per school in `Tenant.policies` (defaults in `core/models.py`):

| Policy | Default | Meaning |
|---|---|---|
| `pass_mark` | 50 | A term average at or above this counts as a pass (used for pass-rate figures) |
| `promotion_min_average` | 50 | Year average needed for the system to recommend promotion |
| `attendance_alert_absences` | 3 | Unexplained absences in a term that trigger an alert to the class teacher and principal |

Grades use the school's grading scale (default A ≥ 80, B ≥ 70, C ≥ 60, D ≥ 50, E below 50).

## Classes and placement

* A **class section** (e.g. Grade 4A) belongs to one grade level and one academic year, has a homeroom
  (class) teacher, a capacity and a room. Subjects are allocated to the class with a subject teacher.
* A pupil is in **one class per academic year**. Moving class keeps the history (`moved`) and is refused
  once the term's results are finalized in the old class. A full class is refused (`class_full`).
* Admissions: an application can name a grade level (`target_id`). Enrolling an approved applicant places
  them in the chosen class, or the least-full class of that grade in the intake year (`class_required` if none
  has room). Withdrawing or transferring a pupil (shared enrollment workflow) ends their class placement.

## Timetable

Weekly lessons per class allocation (day, period, times, room). The server rejects a class with two lessons
at once (`class_timetable_conflict`), a teacher in two classes at once (`teacher_timetable_conflict`) and two
classes in one room (`room_conflict`).

## Attendance

* **Daily register**: taken by the class's homeroom teacher (or the principal).
  **Per-lesson attendance**: taken by that lesson's subject teacher, only on the lesson's weekday.
* Statuses: present, late, absent, excused (excused needs a reason). Only for pupils in the class, on
  school days (Mon–Fri) inside a term, never in the future.
* An **unexplained absence notifies the pupil's guardians** (in-app and email), once per pupil per day.
  When a pupil reaches `attendance_alert_absences` absences in a term, the class teacher and principal are alerted.
* Summaries per pupil or per class give days present, late, absent, excused and the attendance rate.

## Homework, quizzes, exams and marks

* Assessments (homework, quiz, class test, project, exam) belong to a class, subject and term, with a
  weight and a maximum score. A weight of 0 means ungraded practice homework (shown to families, never
  needed for results). New homework notifies pupils and guardians.
* Only the subject's teacher in that class (or the principal) can create assessments and enter marks
  (`not_your_subject`). Scores must be between 0 and the maximum.
* **Subject term score** = Σ(score ÷ max × weight) ÷ Σ weights × 100. **Term average** = mean of the
  subject scores. Positions rank pupils by average; equal averages share a position.

## Term results and report cards

1. The principal **finalizes** a class's term. Every subject must have a graded assessment and every pupil
   must have every mark (`marks_incomplete` lists the gaps). Results are stored with subject scores,
   grade, position, class size and days present/absent. Marks are then locked (`results_finalized`).
2. The class teacher adds the teacher's remark; the principal adds the principal's remark.
3. The principal **publishes** the report cards. Guardians and pupils are notified, and only then can they see
   the results, the marks and the report-card PDF.
4. Finalized results can be reopened until they are published. Published results are permanent.

## Promotion, repetition and completion

* A decision needs **finalized results for every term of the year** (`results_not_finalized`).
* The system recommends: promote (or complete, in the final grade) if the year average ≥
  `promotion_min_average`, otherwise repeat. The principal or administrator decides. Going against the
  recommendation requires a reason (`reason_required`).
* **Promote** moves the pupil to the next grade level for the next academic year; **repeat** keeps the
  grade; **complete** is only for the final grade and marks the pupil as completed. The class placement and
  enrollment are closed with the outcome, a new enrollment is opened for next year, guardians are
  notified, and the decision is audited. One decision per pupil per year.

## Guardian portal

`/api/schools/children/` gives each linked child's class and class teacher, term attendance and
recent absences, upcoming homework, published results and fee balance. Pupils see the same for
themselves. Guardians never see other children.

## API (all under `/api/schools/`)

| Endpoint | Purpose |
|---|---|
| `grade-levels/`, `subjects/`, `allocations/` | Structure (write: `school.classes.manage`) |
| `classes/` (+ `mine/`, `{id}/roster/`, `{id}/place/`, `{id}/timetable/`, `{id}/results-preview/`) | Class sections, rosters, placement and live results |
| `placements/` | Class placement history |
| `timetable/` (+ `mine/`) | Lessons, with conflict checks |
| `attendance/` (+ `sheet/`, `register/`, `summary/`) | Daily and per-lesson registers, summaries |
| `assessments/` (+ `{id}/marks/`) | Homework, quizzes, tests, exams and marks entry |
| `results/` (+ `finalize/`, `publish/`, `reopen/`, `{id}/report-card/`) | Term results, remarks, report cards |
| `promotions/` (+ `recommendations/`, `decide/`) | End-of-year decisions |
| `children/` | Guardian / pupil portal |
| `dashboard/` | Enrollment by grade, fees, attendance today and weekly trend, pass rate by term |
