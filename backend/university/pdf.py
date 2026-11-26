"""Transcript PDF, built on the shared branded document."""
from reportlab.lib.units import mm

from reports.pdf import BrandedDocument


def transcript_pdf(student, summary, *, official):
    tenant = student.tenant
    standing = getattr(student, "academic_standing", None)
    title = "Official Academic Transcript" if official else "Unofficial Academic Transcript"
    doc = BrandedDocument(title, tenant.name, reference=student.student_no,
                          subtitle="Issued by the Office of the Registrar" if official
                          else "Student copy – not valid for official use")
    doc.key_values([
        ("Name", student.person.full_name),
        ("Student number", student.student_no),
        ("Program", standing.program.name if standing else student.current_level or "—"),
        ("Status", student.status.title()),
        ("Date of birth", f"{student.person.date_of_birth:%d %b %Y}" if student.person.date_of_birth else "—"),
        ("Matriculated", f"{standing.matriculated_on:%d %b %Y}" if standing else "—"),
    ])
    if not summary["semesters"]:
        doc.paragraph("No approved grades have been recorded yet.")
    for sem in summary["semesters"]:
        doc.heading(sem["semester"])
        rows = []
        for e in sem["entries"]:
            note = "" if e.id in summary["counted_ids"] else " (not counted – repeated)"
            if e.supersedes_id:
                note += " (amended)"
            rows.append([e.course_code, e.course_title[:46] + note, str(e.credit_hours), e.letter,
                         f"{e.grade_points:.2f}"])
        doc.table(["Code", "Course", "Credits", "Grade", "Points"], rows,
                  col_widths=[24 * mm, 96 * mm, 18 * mm, 18 * mm, 24 * mm], align_right=(2, 4))
        doc.paragraph(f"Semester GPA <b>{sem['gpa'] if sem['gpa'] is not None else '—'}</b> · "
                      f"Credits {sem['credits']} · CGPA to date <b>"
                      f"{sem['cgpa_to_date'] if sem['cgpa_to_date'] is not None else '—'}</b>", size=9)
    doc.total_box("Cumulative GPA (CGPA)", f"{summary['cgpa'] if summary['cgpa'] is not None else '—'}")
    doc.key_values([("Credits attempted", str(summary["credits_attempted"])),
                    ("Credits earned", str(summary["credits_earned"])),
                    ("Academic standing", standing.get_standing_display() if standing else "—"),
                    ("Repeat policy", str(tenant.policy("repeat_policy")).replace("_", " "))])
    doc.paragraph("Grading scale: " + ", ".join(f"{b['grade']} = {b['points']}" for b in tenant.grading_scale),
                  size=8, leading=11)
    if official:
        doc.stamp("OFFICIAL – REGISTRAR VERIFIED")
        doc.signature("University Registrar")
    else:
        doc.paragraph("<i>This unofficial copy is for the student's information only.</i>", size=9)
    return doc.render()
