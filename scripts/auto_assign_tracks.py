from supabase import create_client
from dotenv import load_dotenv
import json
import os

load_dotenv()

# Ordered from most specific → least specific.
# First track with a keyword hit wins.
PRIORITY_KEYWORDS: list[tuple[str, list[str]]] = [
    ('sap_consultant',        ['sap', 'sap fico', 'sap mm', 'sap sd', 's/4hana', 'abap']),
    ('clinical_data_manager', ['clinical trials', 'cdisc', 'medidata', 'edc', 'sdtm', 'gcp']),
    ('healthcare_analyst',    ['epic', 'cerner', 'hl7', 'fhir', 'icd-10', 'hipaa', 'emr', 'ehr']),
    ('bi_developer',          ['power bi', 'tableau', 'qlik', 'ssrs', 'dax', 'mdx', 'business intelligence']),
    ('product_manager',       ['product manager', 'product management', 'roadmap', 'go-to-market', 'apm']),
    ('devops_cloud',          ['kubernetes', 'docker', 'terraform', 'ansible', 'jenkins', 'ci/cd', 'devops']),
    ('data_engineer',         ['spark', 'kafka', 'airflow', 'dbt', 'snowflake', 'databricks', 'data pipeline', 'etl']),
    ('software_engineer',     ['react', 'angular', 'node.js', 'spring boot', 'microservices', 'rest api']),
    ('business_analyst',      ['business analyst', 'requirements', 'stakeholder', 'process improvement', 'visio']),
    ('data_analyst',          ['sql', 'python', 'excel', 'data analysis', 'visualization']),
]


def detect_track(skills: list[str]) -> str:
    if not skills:
        return 'general'

    skills_text = ' '.join(s.lower() for s in skills)

    for track_name, keywords in PRIORITY_KEYWORDS:
        if any(kw in skills_text for kw in keywords):
            return track_name

    return 'general'


def run() -> None:
    client = create_client(
        os.environ['SUPABASE_URL'],
        os.environ['SUPABASE_SERVICE_KEY'],
    )

    students = client.table('students').select('id, name, skills').execute().data

    print(f"Auto-assigning tracks for {len(students)} students...")

    for student in students:
        skills = student.get('skills', [])
        if isinstance(skills, str):
            skills = json.loads(skills)

        track = detect_track(skills)

        payload = {'role_track': track, 'role_tracks': [track] if track != 'general' else []}
        client.table('students').update(payload).eq('id', student['id']).execute()

        print(f"  {student['name']} -> {track}")

    print(f"\nDone! {len(students)} students assigned tracks.")


if __name__ == "__main__":
    run()
