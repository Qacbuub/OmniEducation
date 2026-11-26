"""Term report card PDF, built on the shared branded document."""
from reportlab.lib.units import mm

from reports.pdf import BrandedDocument


def report_card_pdf(result):
    student, section, term = result.student, result.section, result.term
    tenant = student.tenant
    doc = BrandedDocument("Term Report Card", tenant.name, reference=student.student_no,
                          subtitle=f"{term.name} · {section.label} · {section.academic_year.name}")
    doc.key_values([
        ("Pupil", student.person.full_name),
        ("Admission number", student.student_no),
        ("Class", section.label),
        ("Class teacher", section.homeroom_teacher.get_full_name() if section.homeroom_teacher else "—"),
        ("Position", f"{result.position} of {result.class_size}" if result.position else "—"),
        ("Attendance", f"{result.days_present} days present, {result.days_absent} absent"),
    ])
    rows = [[s["code"], s["name"], s["average"], s["grade"], s.get("remark", "")] for s in result.subjects]
    doc.table(["Code", "Subject", "Score %", "Grade", "Remark"], rows,
              col_widths=[22 * mm, 70 * mm, 24 * mm, 20 * mm, 44 * mm], align_right=(2,))
    doc.total_box("Overall average", f"{result.average}%  ({result.grade})")
    doc.heading("Remarks")
    doc.paragraph(f"<b>Class teacher:</b> {result.teacher_remark or '—'}")
    doc.paragraph(f"<b>Principal:</b> {result.principal_remark or '—'}")
    scale = ", ".join(f"{b['grade']} ≥ {b['min']}%" for b in tenant.grading_scale)
    doc.paragraph(f"Grading scale: {scale}. Pass mark {tenant.policy('pass_mark')}%.", size=8, leading=11)
    if result.status == "published":
        doc.stamp(f"PUBLISHED {result.published_at:%d %b %Y}" if result.published_at else "PUBLISHED")
    else:
        doc.stamp("DRAFT – NOT YET RELEASED")
    doc.signature("Principal")
    return doc.render()
