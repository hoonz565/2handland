import requests
from bs4 import BeautifulSoup
import csv
import os
import time
import re
from datetime import datetime
from dotenv import load_dotenv
from google import genai 

load_dotenv()

# Load secrets
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

client = None
if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"AI Init Error: {e}")

def analyze_and_score(product_name, price):
    """Function to ask AI for scoring and review"""
    if not client:
        return 0, "⚠️ (Missing API Key)"
    
    try:
        prompt = (
            f"You are a strict secondhand item valuation expert. "
            f"Product: '{product_name}'. Price: '{price}'.\n"
            f"Score the 'deal value' on a scale of 1-10:\n"
            f"- 1-6: Overpriced or average, not worth buying.\n"
            f"- 7-8: Fair price, good for personal use.\n"
            f"- 9-10: EXCELLENT DEAL, MUST BUY IMMEDIATELY (Rare).\n\n"
            f"REQUIRED RESPONSE FORMAT (Do not deviate):\n"
            f"SCORE: [Number]\n"
            f"COMMENT: [Short review, under 2 sentences]"
        )
        
        response = client.models.generate_content(
            model='gemini-1.5-flash', 
            contents=prompt
        )
        content = response.text.strip()

        # Parse Score
        score_match = re.search(r"SCORE:\s*(\d+)", content)
        score = int(score_match.group(1)) if score_match else 0
        
        # Parse Comment
        comment = content.split("COMMENT:")[-1].strip() if "COMMENT:" in content else content

        return score, comment

    except Exception as e:
        if "429" in str(e):
            return 0, "⚠️ AI Overloaded"
        return 0, f"AI Error: {str(e)[:20]}..."

def send_telegram_msg(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    try:
        api_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        params = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'HTML'}
        requests.get(api_url, params=params)
    except Exception as e:
        print(f"Telegram send error: {e}")

# --- CONFIGURATION ---
url = "https://2handland.com/ajax/load_product" 
csv_filename = 'product_list.csv' 
MIN_SCORE = 9 

# 1. Read old data
seen_links = set()
if os.path.exists(csv_filename):
    with open(csv_filename, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            seen_links.add(row['Link'])

print(f"[{datetime.now()}] Starting scan. Known {len(seen_links)} old products.")

session = requests.Session()
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'X-Requested-With': 'XMLHttpRequest', 'Referer': 'https://2handland.com/'
}
try:
    session.get("https://2handland.com", headers=headers)
except: pass

# 2. Scanning Loop
current_start = 0
step = 48
new_items = []
MAX_PAGES = 3 

for _ in range(MAX_PAGES): 
    payload = {'start': current_start, 'retailerId': '', 'category': '', 'sort': ''}
    try:
        response = session.post(url, data=payload, headers=headers)
        if response.status_code != 200 or not response.text.strip(): break
        
        soup = BeautifulSoup(response.text, 'html.parser')
        items = soup.find_all('div', class_='product-detail-name')
        if not items: break

        for item_div in items:
            link_tag = item_div.find('a')
            if not link_tag: continue
            link = link_tag.get('href')
            if link and not link.startswith('http'): link = "https://2handland.com" + link
            
            if "san-pham" not in link: continue
            if link in seen_links: continue 

            name = link_tag.text.strip()
            parent = item_div.find_parent()
            price = "Contact"
            if parent and parent.find('span', class_='product-detail-price'):
                price = parent.find('span', class_='product-detail-price').text.strip()

            print(f"-> Analyzing new item: {name} ({price})...")
            score, comment = analyze_and_score(name, price)
            print(f"   => AI Score: {score}/10.")

            if score >= MIN_SCORE:
                icon_hot = "🔥" * (score - 8) 
                msg = (
                    f"{icon_hot} <b>HOT DEAL DETECTED ({score}/10)!</b>\n"
                    f"📦 <b>{name}</b>\n"
                    f"💰 Price: {price}\n"
                    f"🤖 <b>AI Review:</b> <i>{comment}</i>\n"
                    f"🔗 <a href='{link}'>Buy now</a>"
                )
                send_telegram_msg(msg)
            else:
                print("   ❌ Low score, skipped.")

            item_data = {
                'Product Name': name, 'Price': price, 'Link': link, 
                'Scan Time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            new_items.append(item_data)
            seen_links.add(link)
            time.sleep(30)

        current_start += step
    except Exception as e:
        print(f"Loop error: {e}")
        break

# 3. Save to File
if new_items:
    print(f"Processed {len(new_items)} new items. Saving to file...")
    file_exists = os.path.exists(csv_filename)
    with open(csv_filename, 'a', newline='', encoding='utf-8-sig') as f:
        fieldnames = ['Product Name', 'Price', 'Link', 'Scan Time']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists: writer.writeheader()
        writer.writerows(new_items)
else:
    print("No new items found.")