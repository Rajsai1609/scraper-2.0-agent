"""Role track configuration for MCT PathAI job scoring."""
from __future__ import annotations

ROLE_TRACKS: dict[str, dict] = {
    "business_analyst": {
        "label": "Business Analyst",
        "icon": "📊",
        "keywords": [
            "business analyst", "BA", "business analysis",
            "requirements gathering", "stakeholder management",
            "process improvement", "JIRA", "Agile", "Scrum",
            "SQL", "Excel", "Power BI", "Tableau", "Visio",
        ],
        "job_titles": [
            "business analyst", "business systems analyst",
            "IT business analyst", "senior business analyst",
            "junior business analyst", "BA/PM",
        ],
        "boost_companies": [
            "deloitte", "accenture", "kpmg", "pwc", "ey",
            "capgemini", "cognizant", "infosys", "wipro", "tcs",
        ],
        "title_boost": 0.20,
        "keyword_boost": 0.15,
        "min_score": 0.25,
    },

    "data_analyst": {
        "label": "Data Analyst",
        "icon": "📈",
        "keywords": [
            "data analyst", "SQL", "Python", "R", "Tableau",
            "Power BI", "Excel", "data visualization",
            "statistical analysis", "ETL", "data modeling",
            "Google Analytics", "Looker", "Snowflake",
        ],
        "job_titles": [
            "data analyst", "senior data analyst",
            "junior data analyst", "analytics engineer",
            "business intelligence analyst", "reporting analyst",
        ],
        "boost_companies": [
            "google", "meta", "amazon", "microsoft", "netflix",
            "airbnb", "uber", "lyft", "stripe", "databricks",
        ],
        "title_boost": 0.20,
        "keyword_boost": 0.15,
        "min_score": 0.25,
    },

    "product_manager": {
        "label": "Product Manager",
        "icon": "🚀",
        "keywords": [
            "product manager", "PM", "product management",
            "roadmap", "product strategy", "user stories",
            "A/B testing", "product analytics", "go-to-market",
            "Agile", "Scrum", "JIRA", "Confluence", "Figma",
        ],
        "job_titles": [
            "product manager", "senior product manager",
            "associate product manager", "APM",
            "technical product manager", "TPM",
            "product owner", "group product manager",
        ],
        "boost_companies": [
            "google", "meta", "apple", "amazon", "microsoft",
            "salesforce", "hubspot", "atlassian", "notion", "figma",
        ],
        "title_boost": 0.25,
        "keyword_boost": 0.15,
        "min_score": 0.25,
    },

    "healthcare_analyst": {
        "label": "Healthcare Analyst",
        "icon": "🏥",
        "keywords": [
            "healthcare analyst", "health data", "EHR", "EMR",
            "Epic", "Cerner", "HL7", "FHIR", "ICD-10", "CPT",
            "claims data", "clinical data", "HIPAA",
            "population health", "healthcare IT", "Tableau",
        ],
        "job_titles": [
            "healthcare analyst", "health data analyst",
            "clinical analyst", "healthcare business analyst",
            "health informatics analyst", "population health analyst",
        ],
        "boost_companies": [
            "unitedhealth", "anthem", "cigna", "aetna", "humana",
            "epic", "cerner", "mckesson", "cardinal health", "cvs",
        ],
        "title_boost": 0.25,
        "keyword_boost": 0.20,
        "min_score": 0.25,
    },

    "clinical_data_manager": {
        "label": "Clinical Data Manager",
        "icon": "🔬",
        "keywords": [
            "clinical data management", "CDM", "clinical trials",
            "EDC", "Medidata Rave", "Veeva Vault", "CDMS",
            "ICH E6", "GCP", "FDA regulations", "SAS", "R",
            "data validation", "CDISC", "SDTM", "ADaM",
        ],
        "job_titles": [
            "clinical data manager", "CDM", "clinical data analyst",
            "data manager", "clinical data coordinator",
            "senior clinical data manager", "lead CDM",
        ],
        "boost_companies": [
            "pfizer", "johnson & johnson", "merck", "abbvie",
            "bristol myers", "roche", "novartis", "eli lilly",
            "iqvia", "covance", "parexel", "icon plc",
        ],
        "title_boost": 0.30,
        "keyword_boost": 0.20,
        "min_score": 0.25,
    },

    "software_engineer": {
        "label": "Software Engineer",
        "icon": "💻",
        "keywords": [
            "software engineer", "SWE", "full stack", "backend",
            "frontend", "Python", "Java", "JavaScript", "React",
            "Node.js", "AWS", "Docker", "Kubernetes", "REST API",
        ],
        "job_titles": [
            "software engineer", "senior software engineer",
            "junior software engineer", "full stack engineer",
            "backend engineer", "frontend engineer", "SWE",
        ],
        "boost_companies": [
            "google", "meta", "amazon", "apple", "microsoft",
            "netflix", "databricks", "stripe", "airbnb", "uber",
        ],
        "title_boost": 0.15,
        "keyword_boost": 0.10,
        "min_score": 0.25,
    },

    "data_engineer": {
        "label": "Data Engineer",
        "icon": "⚙️",
        "keywords": [
            "data engineer", "ETL", "data pipeline", "Spark",
            "Kafka", "Airflow", "dbt", "Snowflake", "Databricks",
            "Python", "SQL", "AWS", "GCP", "Azure", "data lake",
        ],
        "job_titles": [
            "data engineer", "senior data engineer",
            "junior data engineer", "analytics engineer",
            "big data engineer", "data platform engineer",
        ],
        "boost_companies": [
            "databricks", "snowflake", "google", "amazon",
            "microsoft", "netflix", "uber", "airbnb", "stripe",
        ],
        "title_boost": 0.20,
        "keyword_boost": 0.15,
        "min_score": 0.25,
    },

    "devops_cloud": {
        "label": "DevOps / Cloud",
        "icon": "☁️",
        "keywords": [
            "devops", "cloud engineer", "AWS", "GCP", "Azure",
            "Kubernetes", "Docker", "Terraform", "CI/CD",
            "site reliability", "SRE", "platform engineer",
            "infrastructure", "Ansible", "Jenkins",
        ],
        "job_titles": [
            "devops engineer", "cloud engineer", "site reliability engineer",
            "SRE", "platform engineer", "infrastructure engineer",
            "DevSecOps engineer",
        ],
        "boost_companies": [
            "amazon", "google", "microsoft", "hashicorp", "datadog",
            "splunk", "cloudflare", "fastly", "pagerduty",
        ],
        "title_boost": 0.20,
        "keyword_boost": 0.15,
        "min_score": 0.25,
    },

    "sap_consultant": {
        "label": "SAP Consultant",
        "icon": "🏢",
        "keywords": [
            "SAP", "SAP S/4HANA", "SAP FICO", "SAP MM",
            "SAP SD", "SAP HR", "SAP BW", "SAP ABAP",
            "SAP Basis", "SAP CRM", "SAP PM", "SAP QM",
            "SAP implementation", "SAP configuration",
        ],
        "job_titles": [
            "SAP consultant", "SAP FICO consultant",
            "SAP MM consultant", "SAP SD consultant",
            "SAP functional consultant", "SAP technical consultant",
            "SAP analyst", "SAP S/4HANA consultant",
        ],
        "boost_companies": [
            "sap", "deloitte", "accenture", "ibm", "capgemini",
            "infosys", "wipro", "tcs", "cognizant", "hcl",
        ],
        "title_boost": 0.35,
        "keyword_boost": 0.25,
        "min_score": 0.20,
    },

    "bi_developer": {
        "label": "BI Developer",
        "icon": "📊",
        "keywords": [
            "business intelligence", "BI developer", "Power BI",
            "Tableau", "QlikView", "Qlik Sense", "SSRS", "SSAS",
            "SQL", "data warehouse", "ETL", "DAX", "MDX",
            "data modeling", "reporting", "dashboards",
        ],
        "job_titles": [
            "BI developer", "business intelligence developer",
            "Power BI developer", "Tableau developer",
            "BI analyst", "data visualization developer",
            "reporting developer", "BI engineer",
        ],
        "boost_companies": [
            "microsoft", "tableau", "qlik", "tibco",
            "deloitte", "accenture", "kpmg", "pwc",
        ],
        "title_boost": 0.30,
        "keyword_boost": 0.20,
        "min_score": 0.20,
    },
}
