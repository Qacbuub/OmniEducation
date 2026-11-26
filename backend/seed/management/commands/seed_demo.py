"""
python manage.py seed_demo [--reset]

Creates synthetic demo data: a platform admin, one school (Sunrise Academy), one university
(Omni University), a trial school, and one login per role. All names are fictional.
Password for every demo account: Demo@1234
"""
import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from admissions.models import AcademicPeriod, Application, Enrollment
from comms.models import Announcement
from comms.services import notify
from core.models import Role, Tenant, User
from core.rbac import sync_roles
from finance import services as fin
from finance.models import FeePlan, FeePlanItem
from people.models import Guardian, GuardianLink, Person, Staff, Student

from seed import hooks as seed_hooks

PASSWORD = "Demo@1234"
FIRST = ["Amani", "Baraka", "Chloe", "David", "Esther", "Faith", "George", "Hannah", "Ian", "Joy", "Kevin", "Lucy",
         "Moses", "Naomi", "Oscar", "Purity", "Quincy", "Rose", "Samuel", "Tina", "Victor", "Wendy", "Yusuf", "Zawadi",
         "Aaron", "Bella", "Caleb", "Diana", "Elijah", "Fatuma"]
LAST = ["Kariuki", "Odhiambo", "Wambui", "Mutua", "Chebet", "Kiptoo", "Njeri", "Omondi", "Barasa", "Atieno",
        "Smith", "Garcia", "Nguyen", "Patel", "Okafor", "Mensah", "Hassan", "Kim"]
PROGRAMS = ["BSc Computer Science", "BSc Cybersecurity", "BBA Finance", "BEng Electrical Engineering", "BA Economics"]

SCHOOL_USERS = [
    ("admin@sunrise.edu", "Grace", "Wanjiru", "inst_admin", "Administrator"),
    ("principal@sunrise.edu", "Daniel", "Otieno", "principal", "Principal"),
    ("teacher@sunrise.edu", "Mary", "Achieng", "class_teacher", "Class Teacher, Grade 4A"),
    ("subject@sunrise.edu", "Peter", "Kamau", "subject_teacher", "Mathematics Teacher"),
    ("finance@sunrise.edu", "Joseph", "Njoroge", "finance_officer", "Bursar"),
]
UNI_USERS = [
    ("registrar@omniu.edu", "Sarah", "Collins", "registrar", "University Registrar"),
    ("dean@omniu.edu", "Michael", "Hart", "dean", "Dean, Faculty of Computing"),
    ("hod@omniu.edu", "Aisha", "Bello", "dept_head", "Head, Department of Computer Science"),
    ("lecturer@omniu.edu", "James", "Okafor", "lecturer", "Senior Lecturer"),
    ("adviser@omniu.edu", "Linda", "Park", "adviser", "Academic Adviser"),
    ("finance@omniu.edu", "Helen", "Ross", "finance_officer", "Finance Officer"),
]


class Command(BaseCommand):
    help = "Create synthetic demo institutions, users and records."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing demo data first.")

    @transaction.atomic
    def handle(self, *args, reset=False, **opts):
        self.rng = random.Random(2026)
        sync_roles()
        self.roles = {r.code: r for r in Role.objects.all()}
        if reset:
            self._reset()
        if Tenant.objects.filter(slug__in=["sunrise", "omniu"]).exists():
            self.stdout.write(self.style.WARNING("Demo data already exists. Use --reset to recreate it."))
            return

        self._user("superadmin@omniedu.app", "Platform", "Admin", "super_admin", None, is_staff=True, is_superuser=True)
        school = self._school()
        uni = self._university()
        Tenant.objects.create(name="Lakeside Primary", slug="lakeside", type="school", status="trial", city="Kisumu",
                              country="Kenya")
        for hook in seed_hooks.HOOKS:  # school / university modules add their own demo data
            hook(self, school=school, university=uni)
        self.stdout.write(self.style.SUCCESS(f"Demo data created. Password for every account: {PASSWORD}"))

    # ------------------------------------------------------------------ helpers
    def _reset(self):
        from comms.models import Document, Notification
        from core.models import AuditEvent, Invitation
        from finance.models import Invoice, InvoiceLine, Payment

        tenants = Tenant.objects.filter(slug__in=["sunrise", "omniu", "lakeside"])
        for hook in seed_hooks.RESET_HOOKS:
            hook(tenants)
        for model in (Payment, InvoiceLine, Invoice, FeePlanItem, FeePlan, Document, Notification, Announcement,
                      Enrollment, GuardianLink, Guardian, Staff, Student, Application, AcademicPeriod, Invitation):
            model.objects.filter(tenant__in=tenants).delete()
        Person.objects.filter(tenant__in=tenants).delete()
        AuditEvent.objects.filter(tenant__in=tenants).delete()
        User.objects.filter(tenant__in=tenants).delete()
        User.objects.filter(email="superadmin@omniedu.app").delete()
        tenants.delete()
        self.stdout.write("Existing demo data removed.")

    def _user(self, email, first, last, role, tenant, **extra):
        return User.objects.create_user(email=email, password=PASSWORD, first_name=first, last_name=last,
                                        role=self.roles[role], tenant=tenant, **extra)

    def _staff(self, tenant, users):
        for i, (email, first, last, role, title) in enumerate(users, start=1):
            user = self._user(email, first, last, role, tenant)
            person = Person.objects.create(tenant=tenant, first_name=first, last_name=last, email=email)
            Staff.objects.create(tenant=tenant, person=person, user=user, staff_no=f"STF-{i:04d}", job_title=title,
                                 hire_date=date(2020 + i % 5, 1 + i % 12, 1))

    def _name(self):
        return self.rng.choice(FIRST), self.rng.choice(LAST)

    def _student(self, tenant, first, last, level, section, period, dob, email="", user=None):
        person = Person.objects.create(tenant=tenant, first_name=first, last_name=last, date_of_birth=dob,
                                       gender=self.rng.choice(["female", "male"]), email=email,
                                       phone=f"+2547{self.rng.randint(10000000, 99999999)}")
        student = Student.objects.create(tenant=tenant, person=person, user=user, current_level=level,
                                         current_section=section, student_no=Student.next_student_no(tenant),
                                         admission_date=period.start_date)
        Enrollment.objects.create(tenant=tenant, student=student, period=period, level_label=level,
                                  section_label=section, start_date=period.start_date, reason="Admitted")
        return student

    def _guardian(self, tenant, student, first, last, email="", user=None, relationship="mother"):
        person = Person.objects.create(tenant=tenant, first_name=first, last_name=last, email=email,
                                       phone=f"+2547{self.rng.randint(10000000, 99999999)}")
        g = Guardian.objects.create(tenant=tenant, person=person, user=user, occupation="")
        GuardianLink.objects.create(tenant=tenant, guardian=g, student=student, relationship=relationship,
                                    is_primary=True)
        return g

    def _pay_some(self, invoices, finance_user, method="mobile_money"):
        """Leave a realistic mix: paid in full, partially paid and unpaid invoices."""
        for inv in invoices:
            roll = self.rng.random()
            if roll < 0.35:
                fin.record_payment(invoice=inv, amount=inv.balance, method=method, user=finance_user,
                                   reference=f"TXN{self.rng.randint(100000, 999999)}")
            elif roll < 0.75:
                part = (inv.balance * Decimal(self.rng.choice(["0.25", "0.4", "0.5", "0.6"]))).quantize(Decimal("1"))
                fin.record_payment(invoice=inv, amount=part, method=method, user=finance_user,
                                   reference=f"TXN{self.rng.randint(100000, 999999)}")

    # ------------------------------------------------------------------ school
    def _school(self):
        t = Tenant.objects.create(name="Sunrise Academy", slug="sunrise", type="school", status="active",
                                  plan="Standard", city="Nairobi", country="Kenya", currency="KES",
                                  contact_email="info@sunrise.edu", contact_phone="+254 700 000 111",
                                  student_id_prefix="SUN")
        self._staff(t, SCHOOL_USERS)
        year = AcademicPeriod.objects.create(tenant=t, name="2026", kind="academic_year", start_date=date(2026, 1, 5),
                                             end_date=date(2026, 12, 11), is_current=True)
        terms = [
            AcademicPeriod.objects.create(tenant=t, name="Term 1 2026", kind="term", parent=year,
                                          start_date=date(2026, 1, 5), end_date=date(2026, 4, 2)),
            AcademicPeriod.objects.create(tenant=t, name="Term 2 2026", kind="term", parent=year,
                                          start_date=date(2026, 4, 27), end_date=date(2026, 7, 31)),
            AcademicPeriod.objects.create(tenant=t, name="Term 3 2026", kind="term", parent=year,
                                          start_date=date(2026, 8, 31), end_date=date(2026, 12, 11), is_current=True),
        ]
        finance_user = User.objects.get(email="finance@sunrise.edu")

        # The demo family: pupil Brian Mwangi (has a login) and his sister, both linked to parent Ruth Mwangi.
        pupil_user = self._user("pupil@sunrise.edu", "Brian", "Mwangi", "pupil", t)
        parent_user = self._user("parent@sunrise.edu", "Ruth", "Mwangi", "guardian", t)
        brian = self._student(t, "Brian", "Mwangi", "Grade 4", "A", year, date(2016, 3, 14), "pupil@sunrise.edu",
                              pupil_user)
        amina = self._student(t, "Amina", "Mwangi", "Grade 2", "B", year, date(2018, 9, 2))
        ruth = self._guardian(t, brian, "Ruth", "Mwangi", "parent@sunrise.edu", parent_user)
        GuardianLink.objects.create(tenant=t, guardian=ruth, student=amina, relationship="mother", is_primary=True)

        pupils = [brian, amina]
        for grade in range(1, 9):
            for section in ("A", "B"):
                for _ in range(3):
                    first, last = self._name()
                    s = self._student(t, first, last, f"Grade {grade}", section, year,
                                      date(2026 - 6 - grade, self.rng.randint(1, 12), self.rng.randint(1, 28)))
                    self._guardian(t, s, self.rng.choice(FIRST), last, relationship=self.rng.choice(["mother", "father"]))
                    pupils.append(s)

        # Term 3 fees per grade, with a sibling discount for the Mwangi family.
        invoices = []
        for grade in range(1, 9):
            plan = FeePlan.objects.create(tenant=t, name=f"Grade {grade} – Term 3 2026", period=terms[2],
                                          applies_to=f"Grade {grade}", due_days=30)
            tuition = Decimal(22000 + grade * 1000)
            for desc, amt in (("Tuition", tuition), ("Lunch programme", Decimal(6000)), ("Activity fee", Decimal(2500))):
                FeePlanItem.objects.create(tenant=t, plan=plan, description=desc, amount=amt)
            lines = [{"description": i.description, "amount": i.amount} for i in plan.items.all()]
            for s in [p for p in pupils if p.current_level == f"Grade {grade}"]:
                discount = Decimal("3000") if s.person.last_name == "Mwangi" and s.current_level == "Grade 2" else 0
                invoices.append(fin.create_invoice(
                    tenant=t, student=s, lines=lines, fee_plan=plan, period=terms[2],
                    due_date=max(terms[2].start_date + timedelta(days=30), date.today()), discount_amount=discount,
                    discount_reason="Sibling discount" if discount else "", user=finance_user))
        self._pay_some(invoices, finance_user)

        for first, last, level in (("Liam", "Otieno", "Grade 1"), ("Mercy", "Wairimu", "Grade 3"),
                                   ("Noah", "Kiprono", "Grade 6")):
            Application.objects.create(
                tenant=t, first_name=first, last_name=last, date_of_birth=date(2019, 5, 5), email=f"{first.lower()}@example.com",
                requested_level=level, guardian_name=f"Jane {last}", guardian_phone="+254711000000",
                guardian_relationship="mother", intake_period=year, source="online", gender="female" if first == "Mercy"
                else "male", phone="+254711000000", address="Kilimani, Nairobi", national_id=f"BC-{first.upper()}-2019")
        principal = User.objects.get(email="principal@sunrise.edu")
        Announcement.objects.create(tenant=t, title="Mid-term exams start Monday 30 Nov",
                                    body="Exam timetables for Grades 4–8 are on the timetable page.", author=principal,
                                    pinned=True)
        Announcement.objects.create(tenant=t, title="Parents' meeting – Saturday 5 Dec, 10:00",
                                    body="All parents and guardians are welcome in the main hall.",
                                    audience_roles=["guardian"], author=principal)
        notify([parent_user], "Fee reminder", "Term 3 balance for Brian is due.", kind="fee")
        notify(User.objects.filter(tenant=t, role__code__in=["inst_admin", "principal"]), "3 new admission applications",
               "Awaiting review.", kind="admission")
        self.stdout.write(f"  Sunrise Academy: {len(pupils)} pupils, {len(invoices)} invoices")
        return t

    # ------------------------------------------------------------------ university
    def _university(self):
        t = Tenant.objects.create(name="Omni University", slug="omniu", type="university", status="active",
                                  plan="Enterprise", city="Bellevue", country="USA", currency="USD",
                                  contact_email="registrar@omniu.edu", student_id_prefix="OMU",
                                  timezone="America/Los_Angeles")
        self._staff(t, UNI_USERS)
        year = AcademicPeriod.objects.create(tenant=t, name="2026/27", kind="academic_year",
                                             start_date=date(2026, 8, 24), end_date=date(2027, 7, 31), is_current=True)
        sem1 = AcademicPeriod.objects.create(tenant=t, name="Semester 1 2026/27", kind="semester", parent=year,
                                             start_date=date(2026, 8, 24), end_date=date(2026, 12, 18), is_current=True)
        AcademicPeriod.objects.create(tenant=t, name="Semester 2 2026/27", kind="semester", parent=year,
                                      start_date=date(2027, 1, 11), end_date=date(2027, 5, 14))
        finance_user = User.objects.get(email="finance@omniu.edu")

        student_user = self._user("student@omniu.edu", "Kevin", "Mutua", "student", t)
        students = [self._student(t, "Kevin", "Mutua", "BSc Computer Science", "Year 2", sem1, date(2005, 6, 1),
                                  "student@omniu.edu", student_user)]
        for i in range(40):
            first, last = self._name()
            students.append(self._student(t, first, last, PROGRAMS[i % len(PROGRAMS)],
                                          f"Year {1 + self.rng.randint(0, 3)}", sem1,
                                          date(2002 + self.rng.randint(0, 6), self.rng.randint(1, 12), 15)))

        plan = FeePlan.objects.create(tenant=t, name="Undergraduate tuition – Semester 1 2026/27", period=sem1,
                                      due_days=45)
        for desc, amt in (("Tuition (flat rate)", Decimal(6500)), ("Technology fee", Decimal(350)),
                          ("Student services fee", Decimal(250))):
            FeePlanItem.objects.create(tenant=t, plan=plan, description=desc, amount=amt)
        lines = [{"description": i.description, "amount": i.amount} for i in plan.items.all()]
        invoices = []
        for idx, s in enumerate(students):
            scholarship = Decimal("1625") if idx % 7 == 0 else 0
            invoices.append(fin.create_invoice(
                tenant=t, student=s, lines=lines, fee_plan=plan, period=sem1, due_date=max(date(2026, 10, 8), date.today()),
                discount_amount=scholarship, discount_reason="Merit scholarship 25%" if scholarship else "",
                user=finance_user))
        self._pay_some(invoices, finance_user, method="bank_transfer")

        for first, last, program in (("Sofia", "Reyes", PROGRAMS[0]), ("Ethan", "Brooks", PROGRAMS[1]),
                                     ("Zara", "Ali", PROGRAMS[2])):
            Application.objects.create(tenant=t, first_name=first, last_name=last, date_of_birth=date(2007, 2, 2),
                                       email=f"{first.lower()}.{last.lower()}@example.com", requested_level=program,
                                       intake_period=year, source="online", gender="male" if first == "Ethan" else "female",
                                       phone="+255712400100", address="Upanga, Dar es Salaam",
                                       national_id=f"NIDA-{first.upper()}-07", guardian_name=f"Grace {last}",
                                       guardian_relationship="mother", guardian_phone="+255712400200")
        registrar = User.objects.get(email="registrar@omniu.edu")
        Announcement.objects.create(tenant=t, title="Add/drop window closes Friday 28 Nov",
                                    body="Registration changes for Semester 1 end at 23:59.", author=registrar,
                                    pinned=True)
        notify(User.objects.filter(tenant=t, role__code__in=["registrar", "dean"]), "Applications awaiting review",
               "3 undergraduate applications are pending.", kind="admission")
        self.stdout.write(f"  Omni University: {len(students)} students, {len(invoices)} invoices")
        return t
