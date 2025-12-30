import jobspy
import gspread
from openai import OpenAI
import os
import json
import time
import pandas as pd

# --- CONFIGURATION ---
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
GSHEET_SECRET = os.getenv("GSHEET_JSON")
SHEET_NAME = "Biotech Job Scraper"
VALID_AREAS = ["Manhattan", "Long Island City", "Downtown Brooklyn", "Jersey City", "Hoboken"]

def run_job_search():
    gc = gspread.service_account_from_dict(json.loads(GSHEET_SECRET))
    sh = gc.open(SHEET_NAME).worksheet("Main")
    ai_client = OpenAI(api_key=OPENAI_KEY)
    
    # 1. EXPANDED SEARCH (PAGINATION)
    all_batches = []
    for offset_val in [0, 25, 50, 75]: # 4 pages = ~100 results per site
        print(f"Fetching page with offset {offset_val}...")
        batch = jobspy.scrape_jobs(
            site_name=["linkedin", "indeed", "google"],
            search_term='Scientist OR "Research Associate" "cell therapy" OR "synthetic biology"',
            location="New York, NY",
            results_wanted=30,
            offset=offset_val,
            hours_old=720, # Last 30 days
        )
        all_batches.append(batch)
        time.sleep(1) # Polite delay
    
    jobs_df = pd.concat(all_batches).drop_duplicates(subset=['job_url'])
    existing_urls = sh.col_values(8)

    for _, row in jobs_df.iterrows():
        if row['job_url'] in existing_urls: continue

        desc = str(row['description']) if row['description'] else "No JD"
        
        # --- STAGE 1: ROUGH CUT (GPT-4o-mini) ---
        # Goal: Weed out non-NYC, non-Biotech, or non-PhD roles cheaply.
        stage1_prompt = f"Role: {row['title']} at {row['company']}. Location: {row['location']}. JD snippet: {desc[:500]}. Is this a Biotech/Life Sciences role in {VALID_AREAS}? Return JSON: {{'pass': bool, 'area': 'string'}}"
        
        s1_res = ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": stage1_prompt}],
            response_format={"type": "json_object"}
        )
        s1_data = json.loads(s1_res.choices[0].message.content)

        if s1_data.get('pass') is True:
            # --- STAGE 2: DEEP ANALYSIS (GPT-4o) ---
            # Goal: High-precision PhD scoring and technical alignment.
            stage2_prompt = f"""
            Analyze for a PhD ChemE (Synthetic Biology, Northwestern).
            Role: {row['title']} at {row['company']}. Full JD: {desc[:3000]}
            
            Strict Scoring:
            - 90+: Direct match (Synthetic bio, mammalian cells, epigenetics).
            - 70-80: Strong wet-lab (Cell therapy, viral vectors, CRISPR).
            - <50: Software, ML, or strictly clinical roles.
            
            Return JSON:
            {{ "score": int, "neighborhood": "{s1_data['area']}", "summary": "string" }}
            """
            
            s2_res = ai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": "You are a PhD Career Mentor."},
                          {"role": "user", "content": stage2_prompt}],
                response_format={"type": "json_object"}
            )
            s2_data = json.loads(s2_res.choices[0].message.content)

            # Final Filter: Only add if GPT-4o confirms it's a quality lead
            if s2_data['score'] > 60:
                sh.append_row([
                    "v2-Gold", s2_data['score'], row['title'], row['company'], 
                    s2_data['neighborhood'], "Confirmed", str(row['date_posted']), 
                    row['job_url'], s2_data['summary']
                ])
                print(f"Added High Quality Role: {row['title']}")

if __name__ == "__main__":
    run_job_search()