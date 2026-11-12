
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(BASE_DIR))
from generator.config import data_root

OUTPUT_DIR = data_root(BASE_DIR) / "raw"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

skill_categories = {
    "Programming": [
        "Python", "Java", "JavaScript", "C++", "C#", "SQL",
        "TypeScript", "R", "Go", "PHP", "Ruby", "Kotlin",
        "Swift", "Scala", "Rust", "Bash", "PowerShell"
    ],

    "AI and Machine Learning": [
        "Machine Learning", "Deep Learning", "NLP",
        "Computer Vision", "Generative AI", "LLMs",
        "Prompt Engineering", "RAG", "LangChain",
        "LangGraph", "TensorFlow", "PyTorch",
        "Scikit-learn", "Hugging Face", "MLOps"
    ],

    "Data Analytics": [
        "Pandas", "NumPy", "Matplotlib", "Power BI",
        "Tableau", "Excel", "Statistics", "Data Visualization",
        "Data Cleaning", "Data Mining"
    ],

    "Database": [
        "MySQL", "PostgreSQL", "SQLite", "MongoDB",
        "Redis", "Database Design", "Data Modeling",
        "Database Administration"
    ],

    "Cloud and DevOps": [
        "AWS", "Azure", "Google Cloud", "Docker",
        "Kubernetes", "Git", "GitHub Actions",
        "CI/CD", "Linux", "Jenkins"
    ],

    "Web Development": [
        "HTML", "CSS", "React", "Node.js", "Flask",
        "Django", "Streamlit", "REST APIs",
        "Software Testing", "FastAPI"
    ],

    "Project Management": [
        "Agile", "Scrum", "Project Planning",
        "Risk Management", "Team Leadership",
        "Resource Planning", "Jira", "Communication"
    ],

    "Design": [
        "UI Design", "UX Research", "Figma",
        "Wireframing", "Prototyping", "Design Thinking"
    ]
}

# Additions preserve the existing 84 IDs, names, and category assignments.
additional_skill_categories = {
    "Programming": [
        "C", "MATLAB", "Julia", "Objective-C", "Dart", "Elixir",
        "Clojure", "Perl", "Groovy", "Lua", "Haskell",
        "Assembly Language", "Functional Programming",
    ],
    "AI and Machine Learning": [
        "Supervised Learning", "Unsupervised Learning", "Reinforcement Learning",
        "Feature Engineering", "Model Evaluation", "Time Series Modeling",
        "Recommender Systems", "LLM Fine-tuning", "Vector Search",
        "AI Ethics", "Model Deployment", "Explainable AI",
        "Speech Recognition", "Multimodal AI", "AI Agents",
    ],
    "Data Analytics": [
        "Advanced SQL Analytics", "Data Storytelling", "Looker", "Qlik Sense",
        "SAS Analytics", "SPSS", "A/B Testing", "Demand Forecasting",
        "Data Governance", "Data Quality Management", "KPI Design",
        "Experiment Design",
    ],
    "Database": [
        "Oracle Database", "Microsoft SQL Server", "Apache Cassandra",
        "Amazon DynamoDB", "Elasticsearch", "Database Performance Tuning",
        "Query Optimization", "Schema Migration", "Database Security",
        "High Availability Databases",
    ],
    "Cloud and DevOps": [
        "Terraform", "Ansible", "Helm", "Argo CD", "Prometheus", "Grafana",
        "AWS Lambda", "Azure Functions", "Serverless Architecture",
        "Infrastructure as Code", "Cloud Observability", "CI/CD Pipeline Design",
        "Container Security", "Cloud Cost Optimization",
    ],
    "Web Development": [
        "Vue.js", "Angular", "Svelte", "Next.js", "Express.js", "Spring Boot",
        "ASP.NET Core", "GraphQL APIs", "Web Accessibility", "Responsive Web Design",
        "Web Performance Optimization", "OAuth 2.0 and OpenID Connect",
        "WebSockets", "Progressive Web Apps",
    ],
    "Project Management": [
        "Stakeholder Management", "Project Budgeting", "Change Management",
        "Portfolio Management", "Sprint Planning", "Vendor Management",
        "Project Governance", "Project Risk Assessment",
    ],
    "Design": [
        "Interaction Design", "Design Systems", "Visual Design",
        "Accessibility Design", "Usability Testing", "Information Architecture",
    ],
    "Cybersecurity": [
        "Threat Modeling", "Incident Response", "Security Operations Center",
        "Identity and Access Management", "Cloud Security", "Application Security",
        "Penetration Testing", "Vulnerability Management", "Security Auditing",
        "Zero Trust Architecture", "Digital Forensics", "Security Information and Event Management",
        "Endpoint Detection and Response", "Data Loss Prevention",
        "Network Security", "Cryptography", "Secure Software Development",
        "Privacy Engineering", "Phishing Awareness", "Business Continuity Security",
    ],
    "Data Engineering": [
        "ETL Pipeline Development", "ELT Pipeline Development", "Apache Spark",
        "Apache Kafka", "Apache Airflow", "dbt", "Data Lake Architecture",
        "Lakehouse Architecture", "Data Warehouse Design", "Data Modeling for Analytics",
        "Data Pipeline Monitoring", "Batch Processing", "Stream Processing",
        "Change Data Capture", "Data Cataloging", "Master Data Management",
        "Data Lineage", "BigQuery", "Amazon Redshift", "Azure Data Factory",
    ],
    "Business and Finance": [
        "Financial Planning and Analysis", "Financial Modeling", "Budget Forecasting",
        "Management Accounting", "Financial Reporting", "Accounts Payable",
        "Accounts Receivable", "Payroll Accounting", "Revenue Analysis",
        "Cost Accounting", "Cash Flow Management", "Procurement Finance",
        "Business Process Analysis", "Business Case Development",
        "Regulatory Reporting", "Financial Risk Analysis",
    ],
    "Enterprise Platforms": [
        "SAP S/4HANA", "Salesforce Administration", "Microsoft Dynamics 365",
        "ServiceNow Administration", "Workday Administration", "Oracle ERP Cloud",
        "SharePoint Administration", "Microsoft Power Platform", "Salesforce CRM Analytics",
        "ERP Configuration", "CRM Configuration", "Enterprise Integration",
        "Master Data Configuration", "Enterprise Platform Security",
        "Identity Federation", "Enterprise Workflow Automation",
    ],
    "HR and Workforce": [
        "Workforce Planning", "Talent Acquisition", "Interview Design",
        "Employee Relations", "Compensation Analysis", "Benefits Administration",
        "Learning and Development", "Performance Management", "HR Analytics",
        "Job Architecture", "Succession Planning", "People Operations",
        "Diversity and Inclusion Programs", "Employment Policy Administration",
    ],
    "Operations and Supply Chain": [
        "Supply Chain Planning", "Inventory Management", "Demand Planning",
        "Logistics Management", "Warehouse Operations", "Supplier Management",
        "Process Improvement", "Lean Operations", "Six Sigma", "Quality Management Systems",
        "Production Planning", "Service Operations", "Business Continuity Planning",
        "Operational Risk Management",
    ],
    "Quality Assurance and Testing": [
        "Test Automation", "API Testing", "Performance Testing", "Load Testing",
        "Security Testing", "Mobile Application Testing", "Regression Testing",
        "Test Planning", "Test Case Design", "Continuous Testing",
        "Accessibility Testing", "Defect Management",
    ],
    "Product Management": [
        "Product Strategy", "Product Roadmapping", "Product Discovery",
        "Product Analytics", "User Story Mapping", "Backlog Management",
        "Product Lifecycle Management", "Market Research", "Go-to-Market Planning",
        "Product Requirements", "Customer Journey Mapping", "Pricing Strategy",
    ],
}

data = []
skill_number = 1

for category, skills in skill_categories.items():
    for skill in skills:
        data.append({
            "skill_id": f"SKL-{skill_number:06d}",
            "skill_name": skill,
            "skill_category": category
        })
        skill_number += 1

# Append additions after the complete original catalog so the original 84
# skill IDs and names remain byte-for-byte in their existing order.
for category, skills in additional_skill_categories.items():
    for skill in skills:
        data.append({
            "skill_id": f"SKL-{skill_number:06d}",
            "skill_name": skill,
            "skill_category": category,
        })
        skill_number += 1

df = pd.DataFrame(data)

output_file = OUTPUT_DIR / "skills.csv"
df.to_csv(output_file, index=False)

print(f"Successfully generated {len(df)} skills!")
print(f"Saved at: {output_file}")
print("\nSkills by category:")
print(df.groupby("skill_category").size())
print("\nFirst five skills:")
print(df.head())
