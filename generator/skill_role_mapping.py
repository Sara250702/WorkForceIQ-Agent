"""Role-department applicability rules for realistic skill assignment."""


CATEGORY_DEPARTMENTS = {
    "Programming": {"Engineering", "Data & AI", "IT Operations"},
    "AI and Machine Learning": {"Data & AI"},
    "Data Analytics": {"Data & AI", "Management", "Human Resources"},
    "Database": {"Engineering", "Data & AI", "IT Operations"},
    "Cloud and DevOps": {"Engineering", "IT Operations"},
    "Web Development": {"Engineering", "Data & AI"},
    "Project Management": {"Management", "Human Resources"},
    "Design": {"Design"},
    "Cybersecurity": {"IT Operations", "Engineering"},
    "Data Engineering": {"Data & AI", "IT Operations"},
    "Business and Finance": {"Management", "Human Resources"},
    "Enterprise Platforms": {"IT Operations", "Human Resources", "Management"},
    "HR and Workforce": {"Human Resources"},
    "Operations and Supply Chain": {"Management", "IT Operations"},
    "Quality Assurance and Testing": {"Quality Assurance", "Engineering"},
    "Product Management": {"Management", "Data & AI", "Engineering"},
}


def categories_for_department(department, categories):
    """Return applicable catalog categories in their stable catalog order."""
    return [
        category
        for category in categories
        if department in CATEGORY_DEPARTMENTS.get(category, set())
    ]

