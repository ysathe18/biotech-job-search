import jobspy
import gspread
from openai import OpenAI
import os
import json

# --- CONFIGURATION ---
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
GSHEET_SECRET = os.getenv("GSHEET_JSON")
SHEET_NAME = "Biotech Job Scraper" 

RESUME_CONTEXT = "PhD in Chemical Engineering, Northwestern. Expert in Synthetic Biology and Cell Therapy."

def run_job_search():
    try:
        secret_dict = json.loads(GSHEET_SECRET)
        gc = gspread.service_account_from_dict(secret_dict)
        sh = gc.open(SHEET_NAME).worksheet("Main")
    except Exception as e:
        print(f"Connection Error: {e}")
        return

    print("Searching for jobs...")
    jobs = jobspy.scrape_jobs(
        site_name=["linkedin", "indeed", "google"],
        search_term='Scientist "cell therapy" OR "synthetic biology"',
        location="New York, NY",
        results_wanted=40,
        hours_old=720, 
    )

    ai_client = OpenAI(api_key=OPENAI_KEY)
    existing_urls = sh.col_values(8)

    for _, row in jobs.iterrows():
        url = row['job_url']
        if url in existing_urls:
            continue 

        # FIX 1: Handle missing descriptions (floats)
        description = str(row['description']) if row['description'] else "No description provided"
        
        # FIX 2: Align 'neighborhood' key in prompt and response
        prompt = f"""
        Role: {row['title']} at {row['company']}. JD: {description[:2000]}. 
        Return JSON with EXACTLY these keys:
        {{ "score": 0-100, "neighborhood": "string", "cell_therapy": bool, "summary": "string" }}
        """
        
        try:
            response = ai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            data = json.loads(response.choices[0].message.content)

            # Score > 0 means we catch everything for this test
            if data.get('score', 0) >= 0:
                sh.append_row([
                    "Test-Run", 
                    data.get('score'), 
                    row['title'], 
                    row['company'], 
                    data.get('neighborhood', 'Unknown'), 
                    "Yes" if data.get('cell_therapy') else "No", 
                    str(row['date_posted']), 
                    url,
                    data.get('summary', '')
                ])
                print(f"Added: {row['title']}")
        except Exception as e:
            print(f"AI/Row Error: {e}")

if __name__ == "__main__":
    run_job_search()