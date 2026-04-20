from supabase import create_client
from src.config.role_tracks import ROLE_TRACKS
from dotenv import load_dotenv
import os

load_dotenv()

def detect_track(skills: list) -> str:
    if not skills:
        return 'general'

    skills_lower = [s.lower() for s in skills]
    track_scores = {}

    for track_name, config in ROLE_TRACKS.items():
        keywords = [k.lower() for k in config['keywords']]
        matches = sum(
            1 for skill in skills_lower
            if any(k in skill for k in keywords)
        )
        track_scores[track_name] = matches

    best_track = max(track_scores, key=track_scores.get)
    best_score = track_scores[best_track]

    if best_score >= 2:
        return best_track
    return 'general'

def run():
    client = create_client(
        os.environ['SUPABASE_URL'],
        os.environ['SUPABASE_SERVICE_KEY']
    )

    students = client.table('students')\
        .select('id, name, skills')\
        .execute().data

    print(f"Auto-assigning tracks for {len(students)} students...")

    for student in students:
        skills = student.get('skills', [])
        if isinstance(skills, str):
            import json
            skills = json.loads(skills)

        track = detect_track(skills)

        client.table('students')\
            .update({'role_track': track})\
            .eq('id', student['id'])\
            .execute()

        print(f"✅ {student['name']} → {track}")

    print(f"\nDone! {len(students)} students assigned tracks.")

if __name__ == "__main__":
    run()
