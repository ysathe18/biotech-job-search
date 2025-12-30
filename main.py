import jobspy
import gspread
from openai import OpenAI
import os
import json

# --- CONFIGURATION ---
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
GSHEET_SECRET = os.getenv("GSHEET_JSON")
SHEET_NAME = "Biotech Job Scraper" # Updated to your sheet name

RESUME_CONTEXT = """
Ph.D. in Chemical Engineering from Northwestern (Leonard Lab). 
Expertise: Synthetic biology, mammalian cell programming (HEK, iPSCs), epigenetic regulation, 
viral delivery (Lentivirus, AAV), and high-throughput robotic workflows. 
Experience with state-switching genetic programs and chromatin opening domains.
"""

def run_job_search():
    # 1. Connect to Google Sheets
    try:
        secret_dict = json.loads(GSHEET_SECRET)
        gc = gspread.service_account_from_dict(secret_dict)
        sh = gc.open(SHEET_NAME).worksheet("Main") # Specifically targeting the 'Main' tab
    except Exception as e:
        print(f"Error connecting to Google Sheets: {e}")
        return

    # 2. Scrape Jobs (Wide Net)
    print("Searching for new jobs...")
    jobs = jobspy.scrape_jobs(
        site_name=["linkedin", "indeed", "google"],
        search_term='Scientist I "cell therapy"',
        location="New York, NY",
        results_wanted=40,
        hours_old=24, 
    )

    ai_client = OpenAI(api_key=OPENAI_KEY)
    existing_urls = sh.col_values(8) # Assuming Column 8 has the links

    for _, row in jobs.iterrows():
        url = row['job_url']
        if url in existing_urls:
            continue 

        # 3. AI Analysis customized to your PhD background
        prompt = f"""
        Role: {row['title']} at {row['company']}. 
        Description: {row['description'][:3000]}
        
        Candidate Background: {RESUME_CONTEXT}

        Tasks:
        1. Score 0-100 based on PhD fit (Synthetic biology, wet-lab, mammalian cells).
        2. Identify Neighborhood: (Manhattan, Long Island City, Downtown Brooklyn, Jersey City, Hoboken). 
           If outside these, mark as 'Other'.
        3. Is it Cell/Gene Therapy? (True/False).
        4. Brief Match Summary (1 sentence).

        Return ONLY JSON:
        {{ "score": int, "neighborhood": "string", "cell_therapy": bool, "summary": "string" }}
        """
        
        try:
            response = ai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            data = json.loads(response.choices[0].message.content)

            # 4. Filter and Push
            # We want high-relevance roles in your target pockets
            valid_pockets = ["Manhattan", "Long Island City", "Brooklyn", "Jersey City", "Hoboken"]
            is_right_location = any(p in data['neighborhood'] for p in valid_pockets)

            if data['score'] >= 50 and is_right_location:
                # Appending: [Status, Score, Title, Company, Neighborhood, Cell Therapy, Date, URL, Summary]
                sh.append_row([
                    "New", 
                    data['score'], 
                    row['title'], 
                    row['company'], 
                    data['neighborhood'], 
                    "Yes" if data['cell_therapy'] else "No", 
                    str(row['date_posted']), 
                    url,
                    data['summary']
                ])
                print(f"Found and added: {row['title']} at {row['company']}")
        except Exception as e:
            print(f"Error processing job: {e}")

if __name__ == "__main__":
    run_job_search()