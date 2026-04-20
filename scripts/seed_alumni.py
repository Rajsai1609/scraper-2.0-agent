"""
Seed alumni data into Supabase alumni table.
Usage: python scripts/seed_alumni.py
Requires SUPABASE_URL and SUPABASE_SERVICE_KEY in .env
"""

from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

ALUMNI_DATA = [
    # Google
    {"full_name": "Priya Sharma",    "linkedin_url": "https://linkedin.com/in/priyasharma",   "current_company": "Google",      "current_title": "Software Engineer",       "university": "Campbellsville University", "graduation_year": 2022, "major": "Computer Science",      "visa_status": "H1B",        "location": "Mountain View, CA", "willing_to_refer": True},
    {"full_name": "Rahul Kumar",     "linkedin_url": "https://linkedin.com/in/rahulkumar",    "current_company": "Google",      "current_title": "Data Engineer",           "university": "Northeastern University",   "graduation_year": 2021, "major": "Data Science",          "visa_status": "Green Card", "location": "Sunnyvale, CA",     "willing_to_refer": True},
    {"full_name": "Anita Desai",     "linkedin_url": "https://linkedin.com/in/anitadesai",    "current_company": "Google",      "current_title": "Product Manager",         "university": "University of Houston",     "graduation_year": 2020, "major": "MBA",                   "visa_status": "H1B",        "location": "Seattle, WA",       "willing_to_refer": True},
    {"full_name": "Srinivas Rao",    "linkedin_url": "https://linkedin.com/in/srinivasrao",   "current_company": "Google",      "current_title": "Staff SWE",               "university": "Campbellsville University", "graduation_year": 2019, "major": "Computer Science",      "visa_status": "Green Card", "location": "Mountain View, CA", "willing_to_refer": False},

    # Microsoft
    {"full_name": "Vikram Patel",    "linkedin_url": "https://linkedin.com/in/vikrampatel",   "current_company": "Microsoft",   "current_title": "Senior Software Engineer","university": "Campbellsville University", "graduation_year": 2021, "major": "CS",                    "visa_status": "H1B",        "location": "Redmond, WA",       "willing_to_refer": True},
    {"full_name": "Neha Gupta",      "linkedin_url": "https://linkedin.com/in/nehagupta",     "current_company": "Microsoft",   "current_title": "Cloud Architect",         "university": "Northeastern University",   "graduation_year": 2020, "major": "Cloud Computing",       "visa_status": "Green Card", "location": "Bellevue, WA",      "willing_to_refer": True},
    {"full_name": "Suresh Babu",     "linkedin_url": "https://linkedin.com/in/sureshbabu-ms", "current_company": "Microsoft",   "current_title": "Program Manager",         "university": "University of Houston",     "graduation_year": 2021, "major": "Information Systems",   "visa_status": "H1B",        "location": "Redmond, WA",       "willing_to_refer": True},
    {"full_name": "Lakshmi Rajan",   "linkedin_url": "https://linkedin.com/in/lakshmirajan",  "current_company": "Microsoft",   "current_title": "Data Scientist",          "university": "Campbellsville University", "graduation_year": 2023, "major": "Data Science",          "visa_status": "OPT",        "location": "Redmond, WA",       "willing_to_refer": True},

    # Amazon
    {"full_name": "Arjun Singh",     "linkedin_url": "https://linkedin.com/in/arjunsingh",    "current_company": "Amazon",      "current_title": "SDE II",                  "university": "Campbellsville University", "graduation_year": 2022, "major": "CS",                    "visa_status": "H1B",        "location": "Seattle, WA",       "willing_to_refer": True},
    {"full_name": "Meera Iyer",      "linkedin_url": "https://linkedin.com/in/meeraiyer",     "current_company": "Amazon",      "current_title": "Data Scientist",          "university": "University of Houston",     "graduation_year": 2021, "major": "Data Science",          "visa_status": "H1B",        "location": "Austin, TX",        "willing_to_refer": True},
    {"full_name": "Deepak Rao",      "linkedin_url": "https://linkedin.com/in/deepakrao-amz", "current_company": "Amazon",      "current_title": "Business Analyst",        "university": "Northeastern University",   "graduation_year": 2022, "major": "Business Analytics",   "visa_status": "OPT",        "location": "Seattle, WA",       "willing_to_refer": True},
    {"full_name": "Preethi Nair",    "linkedin_url": "https://linkedin.com/in/preethinair",   "current_company": "Amazon",      "current_title": "Product Manager",         "university": "University of Houston",     "graduation_year": 2020, "major": "MBA",                   "visa_status": "H1B",        "location": "Nashville, TN",     "willing_to_refer": False},

    # Meta
    {"full_name": "Karan Mehta",     "linkedin_url": "https://linkedin.com/in/karanmehta",    "current_company": "Meta",        "current_title": "ML Engineer",             "university": "Campbellsville University", "graduation_year": 2021, "major": "AI/ML",                 "visa_status": "H1B",        "location": "Menlo Park, CA",    "willing_to_refer": True},
    {"full_name": "Pooja Reddy",     "linkedin_url": "https://linkedin.com/in/poojareddy",    "current_company": "Meta",        "current_title": "Software Engineer",       "university": "Northeastern University",   "graduation_year": 2022, "major": "CS",                    "visa_status": "OPT",        "location": "New York, NY",      "willing_to_refer": True},
    {"full_name": "Naveen Krishnan", "linkedin_url": "https://linkedin.com/in/naveenkrishnan","current_company": "Meta",        "current_title": "Data Engineer",           "university": "University of Houston",     "graduation_year": 2021, "major": "Data Engineering",      "visa_status": "H1B",        "location": "Menlo Park, CA",    "willing_to_refer": True},

    # Databricks
    {"full_name": "Sid Reddy",       "linkedin_url": "https://linkedin.com/in/sidreddy",      "current_company": "Databricks",  "current_title": "Data Engineer",           "university": "Campbellsville University", "graduation_year": 2023, "major": "Data Engineering",      "visa_status": "OPT",        "location": "San Francisco, CA", "willing_to_refer": True},
    {"full_name": "Divya Kumar",     "linkedin_url": "https://linkedin.com/in/divyakumar",    "current_company": "Databricks",  "current_title": "Solutions Architect",     "university": "University of Houston",     "graduation_year": 2020, "major": "Data Science",          "visa_status": "H1B",        "location": "Seattle, WA",       "willing_to_refer": True},
    {"full_name": "Aditya Menon",    "linkedin_url": "https://linkedin.com/in/adityamenon-db","current_company": "Databricks",  "current_title": "Software Engineer",       "university": "Northeastern University",   "graduation_year": 2022, "major": "Computer Science",      "visa_status": "H1B",        "location": "San Francisco, CA", "willing_to_refer": True},

    # Stripe
    {"full_name": "Rohan Gupta",     "linkedin_url": "https://linkedin.com/in/rohangupta",    "current_company": "Stripe",      "current_title": "Software Engineer",       "university": "Northeastern University",   "graduation_year": 2022, "major": "CS",                    "visa_status": "H1B",        "location": "San Francisco, CA", "willing_to_refer": True},
    {"full_name": "Varsha Pillai",   "linkedin_url": "https://linkedin.com/in/varshapillai",  "current_company": "Stripe",      "current_title": "Data Analyst",            "university": "Campbellsville University", "graduation_year": 2022, "major": "Data Analytics",        "visa_status": "OPT",        "location": "New York, NY",      "willing_to_refer": True},

    # Deloitte
    {"full_name": "Shreya Nair",     "linkedin_url": "https://linkedin.com/in/shreyanair",    "current_company": "Deloitte",    "current_title": "Senior Consultant",       "university": "Campbellsville University", "graduation_year": 2021, "major": "MBA",                   "visa_status": "H1B",        "location": "New York, NY",      "willing_to_refer": True},
    {"full_name": "Amit Sharma",     "linkedin_url": "https://linkedin.com/in/amitsharma",    "current_company": "Deloitte",    "current_title": "SAP Consultant",          "university": "University of Houston",     "graduation_year": 2020, "major": "Business Analytics",   "visa_status": "H1B",        "location": "Chicago, IL",       "willing_to_refer": True},
    {"full_name": "Padmaja Rao",     "linkedin_url": "https://linkedin.com/in/padmajarao",    "current_company": "Deloitte",    "current_title": "Business Analyst",        "university": "Northeastern University",   "graduation_year": 2022, "major": "Information Systems",   "visa_status": "H1B",        "location": "McLean, VA",        "willing_to_refer": True},

    # Accenture
    {"full_name": "Kavita Joshi",    "linkedin_url": "https://linkedin.com/in/kavitajoshi",   "current_company": "Accenture",   "current_title": "Business Analyst",        "university": "Campbellsville University", "graduation_year": 2022, "major": "MBA",                   "visa_status": "OPT",        "location": "Dallas, TX",        "willing_to_refer": True},
    {"full_name": "Siddharth Roy",   "linkedin_url": "https://linkedin.com/in/siddharthroy",  "current_company": "Accenture",   "current_title": "Cloud Engineer",          "university": "University of Houston",     "graduation_year": 2021, "major": "Cloud Computing",       "visa_status": "H1B",        "location": "Houston, TX",       "willing_to_refer": True},

    # Infosys
    {"full_name": "Rajesh Verma",    "linkedin_url": "https://linkedin.com/in/rajeshverma",   "current_company": "Infosys",     "current_title": "Senior Developer",        "university": "Campbellsville University", "graduation_year": 2019, "major": "CS",                    "visa_status": "H1B",        "location": "Houston, TX",       "willing_to_refer": True},
    {"full_name": "Tanuja Reddy",    "linkedin_url": "https://linkedin.com/in/tanujareddy",   "current_company": "Infosys",     "current_title": "Systems Analyst",         "university": "Northeastern University",   "graduation_year": 2020, "major": "Information Technology","visa_status": "H1B",        "location": "Indianapolis, IN",  "willing_to_refer": True},

    # Apple
    {"full_name": "Nisha Patel",     "linkedin_url": "https://linkedin.com/in/nishapatel",    "current_company": "Apple",       "current_title": "iOS Engineer",            "university": "Northeastern University",   "graduation_year": 2021, "major": "CS",                    "visa_status": "H1B",        "location": "Cupertino, CA",     "willing_to_refer": True},
    {"full_name": "Mohan Suresh",    "linkedin_url": "https://linkedin.com/in/mohansuresh",   "current_company": "Apple",       "current_title": "ML Engineer",             "university": "University of Houston",     "graduation_year": 2020, "major": "AI/ML",                 "visa_status": "H1B",        "location": "Cupertino, CA",     "willing_to_refer": False},

    # Netflix
    {"full_name": "Arun Menon",      "linkedin_url": "https://linkedin.com/in/arunmenon",     "current_company": "Netflix",     "current_title": "Data Engineer",           "university": "University of Houston",     "graduation_year": 2020, "major": "Data Science",          "visa_status": "Green Card", "location": "Los Gatos, CA",     "willing_to_refer": True},

    # Salesforce
    {"full_name": "Swati Agarwal",   "linkedin_url": "https://linkedin.com/in/swatiagarwal",  "current_company": "Salesforce",  "current_title": "MTS",                     "university": "Campbellsville University", "graduation_year": 2021, "major": "CS",                    "visa_status": "H1B",        "location": "San Francisco, CA", "willing_to_refer": True},
    {"full_name": "Harsha Teja",     "linkedin_url": "https://linkedin.com/in/harshateja",    "current_company": "Salesforce",  "current_title": "Business Analyst",        "university": "University of Houston",     "graduation_year": 2022, "major": "Business Analytics",   "visa_status": "OPT",        "location": "Dallas, TX",        "willing_to_refer": True},

    # Snowflake
    {"full_name": "Vivek Iyer",      "linkedin_url": "https://linkedin.com/in/vivekiyer",     "current_company": "Snowflake",   "current_title": "Data Engineer",           "university": "Northeastern University",   "graduation_year": 2022, "major": "Data Engineering",      "visa_status": "OPT",        "location": "San Mateo, CA",     "willing_to_refer": True},
    {"full_name": "Rekha Srinivas",  "linkedin_url": "https://linkedin.com/in/rekhasrinivas", "current_company": "Snowflake",   "current_title": "Solutions Engineer",      "university": "Campbellsville University", "graduation_year": 2021, "major": "CS",                    "visa_status": "H1B",        "location": "San Mateo, CA",     "willing_to_refer": True},

    # Cognizant
    {"full_name": "Naresh Balasubramanian", "linkedin_url": "https://linkedin.com/in/nareshb","current_company": "Cognizant",   "current_title": "Senior Analyst",         "university": "University of Houston",     "graduation_year": 2020, "major": "Information Systems",   "visa_status": "H1B",        "location": "Teaneck, NJ",       "willing_to_refer": True},
    {"full_name": "Usha Chandran",   "linkedin_url": "https://linkedin.com/in/ushachandran",  "current_company": "Cognizant",   "current_title": "QA Lead",                 "university": "Campbellsville University", "graduation_year": 2019, "major": "CS",                    "visa_status": "H1B",        "location": "Phoenix, AZ",       "willing_to_refer": True},

    # TCS
    {"full_name": "Ganesh Muthukumar","linkedin_url": "https://linkedin.com/in/ganeshmk",     "current_company": "TCS",         "current_title": "Technology Analyst",      "university": "Northeastern University",   "graduation_year": 2021, "major": "Computer Engineering",  "visa_status": "H1B",        "location": "New York, NY",      "willing_to_refer": True},

    # Wipro
    {"full_name": "Anand Krishnaswamy","linkedin_url": "https://linkedin.com/in/anandkswamy", "current_company": "Wipro",       "current_title": "Senior Developer",        "university": "University of Houston",     "graduation_year": 2020, "major": "CS",                    "visa_status": "H1B",        "location": "Atlanta, GA",       "willing_to_refer": True},

    # Oracle
    {"full_name": "Sunitha Venkat",  "linkedin_url": "https://linkedin.com/in/sunithavenkat", "current_company": "Oracle",      "current_title": "Database Developer",      "university": "Campbellsville University", "graduation_year": 2021, "major": "Database Systems",      "visa_status": "H1B",        "location": "Austin, TX",        "willing_to_refer": True},

    # Cisco
    {"full_name": "Prasad Rajan",    "linkedin_url": "https://linkedin.com/in/prasadrajan",   "current_company": "Cisco",       "current_title": "Network Engineer",        "university": "Northeastern University",   "graduation_year": 2021, "major": "Network Engineering",   "visa_status": "H1B",        "location": "San Jose, CA",      "willing_to_refer": True},

    # Adobe
    {"full_name": "Mythili Kumar",   "linkedin_url": "https://linkedin.com/in/mythilikumar",  "current_company": "Adobe",       "current_title": "Software Engineer",       "university": "University of Houston",     "graduation_year": 2022, "major": "CS",                    "visa_status": "OPT",        "location": "San Jose, CA",      "willing_to_refer": True},

    # Uber
    {"full_name": "Ashwin Natarajan","linkedin_url": "https://linkedin.com/in/ashwinnatarajan","current_company": "Uber",        "current_title": "Backend Engineer",        "university": "Campbellsville University", "graduation_year": 2022, "major": "CS",                    "visa_status": "OPT",        "location": "San Francisco, CA", "willing_to_refer": True},
    {"full_name": "Ranjani Subramaniam","linkedin_url": "https://linkedin.com/in/ranjanisubr","current_company": "Uber",        "current_title": "Data Scientist",          "university": "Northeastern University",   "graduation_year": 2021, "major": "Data Science",          "visa_status": "H1B",        "location": "Seattle, WA",       "willing_to_refer": True},

    # JPMorgan
    {"full_name": "Shankar Iyer",    "linkedin_url": "https://linkedin.com/in/shankariyer",   "current_company": "JPMorgan",    "current_title": "Software Engineer",       "university": "University of Houston",     "graduation_year": 2021, "major": "CS",                    "visa_status": "H1B",        "location": "New York, NY",      "willing_to_refer": True},
    {"full_name": "Divyanka Rao",    "linkedin_url": "https://linkedin.com/in/divyankarao",   "current_company": "JPMorgan",    "current_title": "Business Analyst",        "university": "Campbellsville University", "graduation_year": 2022, "major": "Finance",               "visa_status": "OPT",        "location": "New York, NY",      "willing_to_refer": True},

    # ServiceNow
    {"full_name": "Balaji Sundaram", "linkedin_url": "https://linkedin.com/in/balajisundaram","current_company": "ServiceNow",  "current_title": "Platform Developer",      "university": "Northeastern University",   "graduation_year": 2022, "major": "CS",                    "visa_status": "H1B",        "location": "Santa Clara, CA",   "willing_to_refer": True},

    # Nvidia
    {"full_name": "Madhavan Krishnan","linkedin_url": "https://linkedin.com/in/madhavank",    "current_company": "Nvidia",      "current_title": "GPU Engineer",            "university": "University of Houston",     "graduation_year": 2021, "major": "Computer Engineering",  "visa_status": "H1B",        "location": "Santa Clara, CA",   "willing_to_refer": True},
]


def run():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")

    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY in .env")

    client = create_client(url, key)

    print(f"Seeding {len(ALUMNI_DATA)} alumni...")

    for alumni in ALUMNI_DATA:
        result = client.table("alumni").upsert(
            alumni,
            on_conflict="linkedin_url",
        ).execute()
        print(f"  ✅ {alumni['full_name']} → {alumni['current_company']}")

    print(f"\nDone! {len(ALUMNI_DATA)} alumni seeded.")


if __name__ == "__main__":
    run()
