# Data model (ER diagrams)

Generated from the Django models with `python scripts/generate_er.py` (backend folder), so table names, keys and
relationships match the code. Every tenant-owned table also has `tenant_id → core_tenant` (omitted from
the diagrams to keep them readable) plus `created_at` / `updated_at`.

Database table name = `<app>_<model>` in lower case, e.g. `people.Student` → `people_student`.
53 tables in 7 apps. Start with the overview in [architecture.md](architecture.md#data-model-overview).

## Platform, people and accounts

```mermaid
erDiagram
    Tenant {
        int id PK
        string name
        string slug UK
        string type
        string status
        string plan
        string domain
        string contact_email
        string contact_phone
        string address
        string city
        string country
        file logo
        string accent_color
        string currency
        string timezone
        string student_id_prefix
        json grading_scale
        json policies
    }
    Permission {
        int id PK
        string code UK
        string description
    }
    Role {
        int id PK
        string code UK
        string name
        string scope
    }
    User {
        int id PK
        string password
        datetime last_login
        bool is_superuser
        string first_name
        string last_name
        bool is_staff
        bool is_active
        datetime date_joined
        string email UK
        int role_id FK
        string phone
        bool mfa_enabled
        string mfa_secret
    }
    Invitation {
        int id PK
        string email
        string first_name
        string last_name
        int role_id FK
        string token UK
        int invited_by_id FK
        datetime expires_at
        datetime accepted_at
    }
    AuditEvent {
        int id PK
        int actor_id FK
        string actor_email
        string action
        string target_type
        string target_id
        string target_repr
        json changes
        string ip_address
    }
    Person {
        int id PK
        string first_name
        string middle_name
        string last_name
        date date_of_birth
        string national_id
        string gender
        string email
        string phone
        string address
    }
    Student {
        int id PK
        int person_id FK
        int user_id FK
        string student_no
        string status
        date admission_date
        string current_level
        string current_section
        int application_id FK
        file photo
    }
    EmergencyContact {
        int id PK
        int student_id FK
        string name
        string relationship
        string phone
        string email
        bool is_primary
    }
    Guardian {
        int id PK
        int person_id FK
        int user_id FK
        string occupation
    }
    GuardianLink {
        int id PK
        int guardian_id FK
        int student_id FK
        string relationship
        bool is_primary
        bool receives_notifications
    }
    Staff {
        int id PK
        int person_id FK
        int user_id FK
        string staff_no
        string job_title
        string department
        date hire_date
        string status
    }
    AuditEvent }o--o| User : "actor"
    EmergencyContact }o--|| Student : "student"
    Guardian |o--o| Person : "person"
    Guardian |o--o| User : "user"
    GuardianLink }o--|| Guardian : "guardian"
    GuardianLink }o--|| Student : "student"
    Invitation }o--o| User : "invited_by"
    Invitation }o--|| Role : "role"
    Role }o--o{ Permission : "permissions"
    Staff |o--o| Person : "person"
    Staff |o--o| User : "user"
    Student |o--o| Person : "person"
    Student |o--o| User : "user"
    User }o--o| Role : "role"
```

## Admissions, calendar and finance

```mermaid
erDiagram
    AcademicPeriod {
        int id PK
        string name
        string kind
        int parent_id FK
        date start_date
        date end_date
        bool is_current
    }
    Application {
        int id PK
        string application_no
        string reference_code UK
        string status
        string source
        string first_name
        string middle_name
        string last_name
        date date_of_birth
        string national_id
        file photo
        string gender
        string email
        string phone
        string address
        string previous_school
        string requested_level
        int target_id
        int intake_period_id FK
        string guardian_name
        string guardian_relationship
        string guardian_phone
        string guardian_email
        datetime submitted_at
        int reviewed_by_id FK
        datetime reviewed_at
        text decision_notes
    }
    Enrollment {
        int id PK
        int student_id FK
        int period_id FK
        string level_label
        string section_label
        string status
        date start_date
        date end_date
        string reason
        int recorded_by_id FK
    }
    FeePlan {
        int id PK
        string name
        int period_id FK
        string applies_to
        int due_days
        bool is_active
    }
    FeePlanItem {
        int id PK
        int plan_id FK
        string description
        decimal amount
    }
    Invoice {
        int id PK
        string number
        int student_id FK
        int fee_plan_id FK
        int period_id FK
        date issue_date
        date due_date
        string currency
        decimal subtotal
        decimal discount_amount
        string discount_reason
        decimal total
        decimal amount_paid
        decimal balance
        string status
        string notes
        int created_by_id FK
    }
    InvoiceLine {
        int id PK
        int invoice_id FK
        string description
        decimal amount
    }
    Payment {
        int id PK
        string receipt_no
        int invoice_id FK
        int student_id FK
        decimal amount
        string method
        string reference
        datetime paid_at
        int received_by_id FK
        string notes
    }
    AcademicPeriod }o--o| AcademicPeriod : "parent"
    Application }o--o| AcademicPeriod : "intake_period"
    Enrollment }o--o| AcademicPeriod : "period"
    Enrollment }o--|| Student : "student"
    FeePlan }o--o| AcademicPeriod : "period"
    FeePlanItem }o--|| FeePlan : "plan"
    Invoice }o--o| AcademicPeriod : "period"
    Invoice }o--o| FeePlan : "fee_plan"
    Invoice }o--|| Student : "student"
    InvoiceLine }o--|| Invoice : "invoice"
    Payment }o--|| Invoice : "invoice"
    Payment }o--|| Student : "student"
```

## Communication and documents

```mermaid
erDiagram
    Notification {
        int id PK
        int user_id FK
        string title
        text body
        string kind
        string link
        datetime read_at
    }
    Announcement {
        int id PK
        string title
        text body
        json audience_roles
        int author_id FK
        bool pinned
    }
    Document {
        int id PK
        string kind
        string title
        file file
        string original_name
        int size
        int student_id FK
        int application_id FK
        bool generated
        int uploaded_by_id FK
    }
    Announcement }o--o| User : "author"
    Document }o--o| Application : "application"
    Document }o--o| Student : "student"
    Document }o--o| User : "uploaded_by"
    Notification }o--|| User : "user"
```

## School (K-12) module

```mermaid
erDiagram
    GradeLevel {
        int id PK
        string name
        int order
        bool is_final
    }
    Subject {
        int id PK
        string name
        string code
    }
    ClassSection {
        int id PK
        int grade_level_id FK
        int academic_year_id FK
        string name
        int homeroom_teacher_id FK
        int capacity
        string room
    }
    ClassAssignment {
        int id PK
        int section_id FK
        int subject_id FK
        int teacher_id FK
        int weekly_lessons
    }
    ClassPlacement {
        int id PK
        int student_id FK
        int section_id FK
        string status
        date start_date
        date end_date
        int placed_by_id FK
    }
    SchoolTimetable {
        int id PK
        int assignment_id FK
        int day
        int period_no
        time start_time
        time end_time
        string room
    }
    PupilAttendance {
        int id PK
        int student_id FK
        int section_id FK
        date date
        int lesson_id FK
        string status
        string reason
        int recorded_by_id FK
        bool guardian_notified
    }
    SchoolAssessment {
        int id PK
        int section_id FK
        int subject_id FK
        int term_id FK
        string name
        string kind
        text description
        decimal weight
        decimal max_score
        date due_date
        int created_by_id FK
    }
    SchoolMark {
        int id PK
        int assessment_id FK
        int student_id FK
        decimal score
        string remarks
        int recorded_by_id FK
    }
    TermResult {
        int id PK
        int student_id FK
        int section_id FK
        int term_id FK
        json subjects
        decimal average
        string grade
        int position
        int class_size
        int days_present
        int days_absent
        string teacher_remark
        string principal_remark
        string status
        int finalized_by_id FK
        datetime finalized_at
        datetime published_at
    }
    PromotionDecision {
        int id PK
        int student_id FK
        int section_id FK
        int academic_year_id FK
        string decision
        int from_level_id FK
        int to_level_id FK
        decimal year_average
        string recommended
        string reason
        int decided_by_id FK
    }
    ClassAssignment }o--o| User : "teacher"
    ClassAssignment }o--|| ClassSection : "section"
    ClassAssignment }o--|| Subject : "subject"
    ClassPlacement }o--o| User : "placed_by"
    ClassPlacement }o--|| ClassSection : "section"
    ClassPlacement }o--|| Student : "student"
    ClassSection }o--o| User : "homeroom_teacher"
    ClassSection }o--|| AcademicPeriod : "academic_year"
    ClassSection }o--|| GradeLevel : "grade_level"
    PromotionDecision }o--o| GradeLevel : "to_level"
    PromotionDecision }o--o| User : "decided_by"
    PromotionDecision }o--|| AcademicPeriod : "academic_year"
    PromotionDecision }o--|| ClassSection : "section"
    PromotionDecision }o--|| GradeLevel : "from_level"
    PromotionDecision }o--|| Student : "student"
    PupilAttendance }o--o| SchoolTimetable : "lesson"
    PupilAttendance }o--o| User : "recorded_by"
    PupilAttendance }o--|| ClassSection : "section"
    PupilAttendance }o--|| Student : "student"
    SchoolAssessment }o--o| User : "created_by"
    SchoolAssessment }o--|| AcademicPeriod : "term"
    SchoolAssessment }o--|| ClassSection : "section"
    SchoolAssessment }o--|| Subject : "subject"
    SchoolMark }o--o| User : "recorded_by"
    SchoolMark }o--|| SchoolAssessment : "assessment"
    SchoolMark }o--|| Student : "student"
    SchoolTimetable }o--|| ClassAssignment : "assignment"
    TermResult }o--o| User : "finalized_by"
    TermResult }o--|| AcademicPeriod : "term"
    TermResult }o--|| ClassSection : "section"
    TermResult }o--|| Student : "student"
```

## University module

```mermaid
erDiagram
    Faculty {
        int id PK
        string name
        string code
        int dean_id FK
    }
    Department {
        int id PK
        int faculty_id FK
        string name
        string code
        int head_id FK
    }
    Program {
        int id PK
        int department_id FK
        string name
        string code
        string award
        int duration_years
        int total_credits_required
        bool is_active
    }
    Course {
        int id PK
        int department_id FK
        string code
        string title
        int credit_hours
        int level
        text description
        bool is_active
    }
    CoursePrerequisite {
        int id PK
        int course_id FK
        int prerequisite_id FK
        decimal min_grade_points
    }
    Curriculum {
        int id PK
        int program_id FK
        string version
        date effective_from
        int elective_credits_required
        bool is_current
    }
    CurriculumCourse {
        int id PK
        int curriculum_id FK
        int course_id FK
        string category
        int recommended_year
        int recommended_semester
    }
    Semester {
        int id PK
        int period_id FK
        date registration_start
        date registration_end
        date add_drop_end
        date grades_due
    }
    CourseOffering {
        int id PK
        int course_id FK
        int semester_id FK
        string section
        int lecturer_id FK
        int capacity
        string status
    }
    OfferingMeeting {
        int id PK
        int offering_id FK
        int day
        time start_time
        time end_time
        string room
    }
    AcademicStanding {
        int id PK
        int student_id FK
        int program_id FK
        int curriculum_id FK
        int adviser_id FK
        int year_of_study
        date matriculated_on
        decimal cgpa
        int credits_attempted
        int credits_earned
        string standing
    }
    CourseRegistration {
        int id PK
        int student_id FK
        int offering_id FK
        string status
        int attempt_no
        int requested_by_id FK
        int decided_by_id FK
        datetime decided_at
        string decision_notes
        datetime dropped_at
    }
    UniversityAssessment {
        int id PK
        int offering_id FK
        string name
        string kind
        decimal weight
        decimal max_score
        date due_date
    }
    LectureAttendance {
        int id PK
        int offering_id FK
        int registration_id FK
        date date
        string status
        string note
        int recorded_by_id FK
    }
    AssessmentScore {
        int id PK
        int assessment_id FK
        int registration_id FK
        decimal score
        int recorded_by_id FK
    }
    UniversityGrade {
        int id PK
        int registration_id FK
        decimal total_score
        string letter
        decimal grade_points
        string status
        int submitted_by_id FK
        datetime submitted_at
        int approved_by_id FK
        datetime approved_at
    }
    GradeApproval {
        int id PK
        int offering_id FK
        int grade_id FK
        string action
        int actor_id FK
        string notes
        json details
    }
    TranscriptEntry {
        int id PK
        int student_id FK
        int registration_id FK
        int course_id FK
        int semester_id FK
        string course_code
        string course_title
        int credit_hours
        decimal total_score
        string letter
        decimal grade_points
        int attempt_no
        int approved_by_id FK
        int supersedes_id FK
        string reason
    }
    GraduationClearance {
        int id PK
        int student_id FK
        string status
        json audit_snapshot
        decimal finance_balance
        int requested_by_id FK
        int decided_by_id FK
        datetime decided_at
        string notes
    }
    AcademicStanding |o--o| Student : "student"
    AcademicStanding }o--o| Curriculum : "curriculum"
    AcademicStanding }o--o| User : "adviser"
    AcademicStanding }o--|| Program : "program"
    AssessmentScore }o--o| User : "recorded_by"
    AssessmentScore }o--|| CourseRegistration : "registration"
    AssessmentScore }o--|| UniversityAssessment : "assessment"
    Course }o--|| Department : "department"
    CourseOffering }o--o| User : "lecturer"
    CourseOffering }o--|| Course : "course"
    CourseOffering }o--|| Semester : "semester"
    CoursePrerequisite }o--|| Course : "course"
    CoursePrerequisite }o--|| Course : "prerequisite"
    CourseRegistration }o--o| User : "decided_by"
    CourseRegistration }o--o| User : "requested_by"
    CourseRegistration }o--|| CourseOffering : "offering"
    CourseRegistration }o--|| Student : "student"
    Curriculum }o--|| Program : "program"
    CurriculumCourse }o--|| Course : "course"
    CurriculumCourse }o--|| Curriculum : "curriculum"
    Department }o--o| User : "head"
    Department }o--|| Faculty : "faculty"
    Faculty }o--o| User : "dean"
    GradeApproval }o--o| UniversityGrade : "grade"
    GradeApproval }o--o| User : "actor"
    GradeApproval }o--|| CourseOffering : "offering"
    GraduationClearance }o--o| User : "decided_by"
    GraduationClearance }o--o| User : "requested_by"
    GraduationClearance }o--|| Student : "student"
    LectureAttendance }o--o| User : "recorded_by"
    LectureAttendance }o--|| CourseOffering : "offering"
    LectureAttendance }o--|| CourseRegistration : "registration"
    OfferingMeeting }o--|| CourseOffering : "offering"
    Program }o--|| Department : "department"
    Semester |o--o| AcademicPeriod : "period"
    TranscriptEntry |o--o| TranscriptEntry : "supersedes"
    TranscriptEntry }o--o| User : "approved_by"
    TranscriptEntry }o--|| Course : "course"
    TranscriptEntry }o--|| CourseRegistration : "registration"
    TranscriptEntry }o--|| Semester : "semester"
    TranscriptEntry }o--|| Student : "student"
    UniversityAssessment }o--|| CourseOffering : "offering"
    UniversityGrade |o--o| CourseRegistration : "registration"
    UniversityGrade }o--o| User : "approved_by"
    UniversityGrade }o--o| User : "submitted_by"
```

