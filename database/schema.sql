
-- ==========================================
-- WorkforceIQ Database Schema
-- ==========================================

-- 1. Roles
CREATE TABLE IF NOT EXISTS roles (
    role_id TEXT PRIMARY KEY,
    role_name TEXT NOT NULL,
    department TEXT NOT NULL,
    description TEXT
);

-- 2. Employees
CREATE TABLE IF NOT EXISTS employees (
    employee_id TEXT PRIMARY KEY,
    employee_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    role_id TEXT,
    employment_type TEXT NOT NULL,
    joining_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    FOREIGN KEY (role_id) REFERENCES roles(role_id)
);

-- 3. Skills
CREATE TABLE IF NOT EXISTS skills (
    skill_id TEXT PRIMARY KEY,
    skill_name TEXT UNIQUE NOT NULL,
    skill_category TEXT
);

-- 4. Employee Skills
CREATE TABLE IF NOT EXISTS employee_skills (
    employee_skill_id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    skill_id TEXT NOT NULL,
    proficiency_level INTEGER NOT NULL,
    last_verified_date DATE,
    expiry_date DATE,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
    FOREIGN KEY (skill_id) REFERENCES skills(skill_id),
    UNIQUE(employee_id, skill_id),
    CHECK (proficiency_level BETWEEN 1 AND 5)
);


-- 5. Projects
CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    project_name TEXT NOT NULL,
    department TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    project_status TEXT NOT NULL,
    approval_probability REAL DEFAULT 1.0,
    CHECK (approval_probability BETWEEN 0 AND 1),
    CHECK (end_date >= start_date)
);

-- 6. Demand Plans
CREATE TABLE IF NOT EXISTS demand_plans (
    demand_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    skill_id TEXT NOT NULL,
    demand_week DATE NOT NULL,
    required_employees INTEGER NOT NULL,
    required_hours REAL NOT NULL,
    demand_type TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    FOREIGN KEY (role_id) REFERENCES roles(role_id),
    FOREIGN KEY (skill_id) REFERENCES skills(skill_id),
    CHECK (required_employees >= 0),
    CHECK (required_hours >= 0)
);

-- 7. Allocations
CREATE TABLE IF NOT EXISTS allocations (
    allocation_id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    allocation_start DATE NOT NULL,
    allocation_end DATE NOT NULL,
    allocated_hours REAL NOT NULL,
    allocation_status TEXT NOT NULL,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    CHECK (allocated_hours >= 0),
    CHECK (allocation_end >= allocation_start)
);

-- 8. Availability
CREATE TABLE IF NOT EXISTS availability (
    availability_id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    availability_date DATE NOT NULL,
    standard_hours REAL NOT NULL,
    leave_hours REAL DEFAULT 0,
    available_hours REAL NOT NULL,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
    CHECK (standard_hours >= 0),
    CHECK (leave_hours >= 0),
    CHECK (leave_hours <= standard_hours),
    CHECK (available_hours >= 0),
    CHECK (available_hours = standard_hours - leave_hours)
);

-- 9. Training
CREATE TABLE IF NOT EXISTS training (
    training_id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    skill_id TEXT NOT NULL,
    training_start_date DATE NOT NULL,
    training_end_date DATE NOT NULL,
    training_hours REAL NOT NULL,
    training_status TEXT NOT NULL,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
    FOREIGN KEY (skill_id) REFERENCES skills(skill_id),
    CHECK (training_end_date >= training_start_date),
    CHECK (training_hours >= 0),
    CHECK (training_status IN ('planned', 'in_progress', 'completed'))
);
-- 10. Skill Gap Analysis
CREATE TABLE IF NOT EXISTS gap_analysis (
    gap_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    skill_id TEXT NOT NULL,
    required_hours REAL NOT NULL,
    available_hours REAL NOT NULL,
    gap_hours REAL NOT NULL,
    gap_status TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    FOREIGN KEY (skill_id) REFERENCES skills(skill_id),
    CHECK (required_hours >= 0),
    CHECK (available_hours >= 0),
    CHECK (gap_hours >= 0),
    CHECK (gap_hours = MAX(required_hours - available_hours, 0)),
    CHECK (gap_status IN ('covered', 'shortage'))
);

 --Exception tracking & Audit history


-- 11. Exceptions
CREATE TABLE IF NOT EXISTS exceptions (
    exception_id TEXT PRIMARY KEY,
    issue_type TEXT NOT NULL,
    affected_entity_id TEXT NOT NULL,
    detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    severity TEXT NOT NULL,
    expected_value TEXT,
    actual_value TEXT,
    resolution_status TEXT DEFAULT 'open',
    resolution_notes TEXT
);

-- 12. Audit Logs
CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    changed_by TEXT
);

