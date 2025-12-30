import jobspy
import gspread
from openai import OpenAI
import os
import json

# --- CONFIGURATION ---
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
GSHEET_SECRET = os.getenv("GSHEET_JSON")
SHEET_NAME = "Biotech Job Scraper" 

RESUME_CONTEXT = """
Ph.D. in Chemical Engineering from Northwestern (Leonard Lab). 
Expertise: Synthetic biology, mammalian cell programming (HEK, iPSCs), epigenetic regulation, 
viral delivery (Lentivirus, AAV), and high-throughput robotic workflows. 
"""

def run_job_search():
    try:
        secret_dict = json.loads(GSHEET_SECRET)
        gc = gspread.service_account_from_dict(secret_dict)
        sh = gc.open(SHEET_NAME).worksheet("Main")
    except Exception as e:
        print(f"Connection Error: {e}")
        return

    # RELAXED PARAMETERS: 30 days (720 hours) and broader search
    print("Searching for jobs from the last 30 days...")
    jobs = jobspy.scrape_jobs(
        site_name=["linkedin", "indeed", "google"],
        search_term='Scientist "cell therapy" OR "synthetic biology"',
        location="New York, NY",
        results_wanted=50,
        hours_old=720, 
    )

    ai_client = OpenAI(api_key=OPENAI_KEY)
    existing_urls = sh.col_values(8)

    for _, row in jobs.iterrows():
        url = row['job_url']
        if url in existing_urls:
            continue 

        prompt = f"Role: {row['title']} at {row['company']}. JD: {row['description'][:2000]}. Return JSON: {{'score': 0-100, 'loc': 'neighborhood', 'cell_therapy': bool, 'summary': '1 sentence'}}"
        
        try:
            response = ai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            data = json.loads(response.choices[0].message.content)

            # RELAXED FILTER: Score > 0 and no location restriction for the test
            if data['score'] >= 0:
                sh.append_row([
                    "Test-Run", 
                    data['score'], 
                    row['title'], 
                    row['company'], 
                    data['neighborhood'], 
                    "Yes" if data['cell_therapy'] else "No", 
                    str(row['date_posted']), 
                    url,
                    data['summary']
                ])
                print(f"Added: {row['title']}")
        except Exception as e:
            print(f"AI Error: {e}")

if __name__ == "__main__":
    run_job_search()