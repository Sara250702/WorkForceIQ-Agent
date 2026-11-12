# WorkForceIQ Data Dictionary

This dictionary documents the ten workforce entities defined in `database/schema.sql` and the matching raw CSV files in the selected dataset's `data/raw/` directory. Column types and constraints below are the SQLite schema declarations. CSV files do not enforce types or nullability themselves.

## Conventions

- `TEXT`, `INTEGER`, `REAL`, and `DATE` are SQLite declared types. Dates are represented in generated CSV data as ISO dates (`YYYY-MM-DD`).
- Required means `NOT NULL` in the schema, or a primary-key field. Optional means the schema permits null, sometimes with a default.
- Foreign keys are enforced when the database connection enables foreign-key enforcement. The offline generation workflow also runs foreign-key checks.
- Hours are numeric hours. No currency or timezone unit is defined for these ten entities.
- Where the schema has no `CHECK` constraint, the field is not an enumerated value at the database-schema level. Generated values may be more specific; that does not make them a formal schema enumeration.

## Entities

### Employee — `employees`

CSV: `raw/employees.csv`  
Primary key: `employee_id`

| Column | Type | Required? | Key / allowed values / units |
|---|---|---:|---|
| `employee_id` | TEXT | Yes | Primary key; generated IDs use the `EMP-` prefix. |
| `employee_name` | TEXT | Yes | Name field. |
| `email` | TEXT | Yes | Unique. |
| `role_id` | TEXT | No | FK to `roles.role_id`. |
| `employment_type` | TEXT | Yes | No schema enumeration. |
| `joining_date` | DATE | Yes | Calendar date. |
| `status` | TEXT | Yes | Default `active`; no schema enumeration. |

### Role — `roles`

CSV: `raw/roles.csv`  
Primary key: `role_id`

| Column | Type | Required? | Key / allowed values / units |
|---|---|---:|---|
| `role_id` | TEXT | Yes | Primary key. |
| `role_name` | TEXT | Yes | — |
| `department` | TEXT | Yes | — |
| `description` | TEXT | No | — |

### Skill — `skills`

CSV: `raw/skills.csv`  
Primary key: `skill_id`

| Column | Type | Required? | Key / allowed values / units |
|---|---|---:|---|
| `skill_id` | TEXT | Yes | Primary key; generated IDs use the `SKL-` prefix. |
| `skill_name` | TEXT | Yes | Unique. |
| `skill_category` | TEXT | No | No schema enumeration. |

### EmployeeSkill — `employee_skills`

CSV: `raw/employee_skills.csv`  
Primary key: `employee_skill_id`; unique pair: (`employee_id`, `skill_id`)

| Column | Type | Required? | Key / allowed values / units |
|---|---|---:|---|
| `employee_skill_id` | TEXT | Yes | Primary key. |
| `employee_id` | TEXT | Yes | FK to `employees.employee_id`. |
| `skill_id` | TEXT | Yes | FK to `skills.skill_id`. |
| `proficiency_level` | INTEGER | Yes | Check constraint: 1 through 5. |
| `last_verified_date` | DATE | No | Calendar date. |
| `expiry_date` | DATE | No | Calendar date. |

### Project — `projects`

CSV: `raw/projects.csv`  
Primary key: `project_id`

| Column | Type | Required? | Key / allowed values / units |
|---|---|---:|---|
| `project_id` | TEXT | Yes | Primary key; generated IDs use the `PRJ-` prefix. |
| `project_name` | TEXT | Yes | — |
| `department` | TEXT | Yes | — |
| `start_date` | DATE | Yes | Calendar date. |
| `end_date` | DATE | Yes | Calendar date; must be on or after `start_date`. |
| `project_status` | TEXT | Yes | No schema enumeration. |
| `approval_probability` | REAL | No | Default `1.0`; constrained to 0 through 1 (probability, not a percentage field). |

### DemandPlan — `demand_plans`

CSV: `raw/demand_plans.csv`  
Primary key: `demand_id`

| Column | Type | Required? | Key / allowed values / units |
|---|---|---:|---|
| `demand_id` | TEXT | Yes | Primary key. |
| `project_id` | TEXT | Yes | FK to `projects.project_id`. |
| `role_id` | TEXT | Yes | FK to `roles.role_id`. |
| `skill_id` | TEXT | Yes | FK to `skills.skill_id`. |
| `demand_week` | DATE | Yes | Date identifying the demand week. |
| `required_employees` | INTEGER | Yes | Nonnegative headcount. |
| `required_hours` | REAL | Yes | Nonnegative hours for the demand record. |
| `demand_type` | TEXT | Yes | No schema enumeration. |

### Allocation — `allocations`

CSV: `raw/allocations.csv`  
Primary key: `allocation_id`

| Column | Type | Required? | Key / allowed values / units |
|---|---|---:|---|
| `allocation_id` | TEXT | Yes | Primary key. |
| `employee_id` | TEXT | Yes | FK to `employees.employee_id`. |
| `project_id` | TEXT | Yes | FK to `projects.project_id`. |
| `allocation_start` | DATE | Yes | Calendar date. |
| `allocation_end` | DATE | Yes | Calendar date; must be on or after `allocation_start`. |
| `allocated_hours` | REAL | Yes | Nonnegative hours. |
| `allocation_status` | TEXT | Yes | No schema enumeration. |

### Availability — `availability`

CSV: `raw/availability.csv`  
Primary key: `availability_id`

| Column | Type | Required? | Key / allowed values / units |
|---|---|---:|---|
| `availability_id` | TEXT | Yes | Primary key. |
| `employee_id` | TEXT | Yes | FK to `employees.employee_id`. |
| `availability_date` | DATE | Yes | Date for the availability period; generated records are weekly. |
| `standard_hours` | REAL | Yes | Nonnegative hours. |
| `leave_hours` | REAL | No | Default `0`; nonnegative and no more than `standard_hours`. |
| `available_hours` | REAL | Yes | Nonnegative hours; constrained to `standard_hours - leave_hours`. |

### Training — `training`

CSV: `raw/training.csv`  
Primary key: `training_id`

| Column | Type | Required? | Key / allowed values / units |
|---|---|---:|---|
| `training_id` | TEXT | Yes | Primary key. |
| `employee_id` | TEXT | Yes | FK to `employees.employee_id`. |
| `skill_id` | TEXT | Yes | FK to `skills.skill_id`. |
| `training_start_date` | DATE | Yes | Calendar date. |
| `training_end_date` | DATE | Yes | Calendar date; must be on or after start. |
| `training_hours` | REAL | Yes | Nonnegative hours. |
| `training_status` | TEXT | Yes | One of `planned`, `in_progress`, `completed`. |

### GapAnalysis — `gap_analysis`

CSV: `raw/gap_analysis.csv`  
Primary key: `gap_id`

| Column | Type | Required? | Key / allowed values / units |
|---|---|---:|---|
| `gap_id` | TEXT | Yes | Primary key. |
| `project_id` | TEXT | Yes | FK to `projects.project_id`. |
| `skill_id` | TEXT | Yes | FK to `skills.skill_id`. |
| `required_hours` | REAL | Yes | Nonnegative hours. |
| `available_hours` | REAL | Yes | Nonnegative hours. |
| `gap_hours` | REAL | Yes | Nonnegative hours; constrained to `MAX(required_hours - available_hours, 0)`. |
| `gap_status` | TEXT | Yes | One of `covered`, `shortage`. |

## Relationship summary

- An employee may reference one role; role is nullable on the employee record.
- `employee_skills` is the employee-to-skill association. The schema prevents duplicate employee/skill pairs and stores proficiency and verification dates on that association.
- A demand record joins a project, role and skill for a demand week.
- Allocations join employees to projects. Availability is recorded per employee and date period.
- Training joins employees to skills. Gap analysis joins a project and skill with required, available and unmet hours.
- The schema does not declare a direct foreign key from a demand record to a project-week allocation, nor a unique business key for demand records. The Run B anomaly workflow deliberately uses duplicate demand business fields to test detection.

## Source and scope

The schema is `database/schema.sql`. The current Run B dataset has matching CSV files in its `data/raw/` directory. This document describes declared schema types and constraints; it does not infer stricter allowed-value lists from sample rows.
