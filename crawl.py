import requests
from bs4 import BeautifulSoup
import csv
import os
from datetime import datetime

load_dotenv()
# Lấy bí mật từ GitHub
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_msg(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    try:
        api_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        params = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'HTML'}
        requests.get(api_url, params=params)
    except Exception as e:
        print(f"Lỗi gửi Telegram: {e}")

# Cấu hình
url = "https://2handland.com/muon-mua"
csv_filename = 'danh_sach_san_pham.csv'

# 1. Đọc dữ liệu cũ
seen_links = set()
if os.path.exists(csv_filename):
    with open(csv_filename, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            seen_links.add(row['Link'])

print(f"[{datetime.now()}] Bắt đầu quét. Đã biết {len(seen_links)} sản phẩm cũ.")

session = requests.Session()
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'X-Requested-With': 'XMLHttpRequest', 'Referer': 'https://2handland.com/'
}
try:
    session.get("https://2handland.com", headers=headers)
except: pass

# 2. Quét (Bỏ while True, chỉ chạy quét 1 lượt các trang đầu)
current_start = 0
step = 48
new_items = []

# Quét khoảng 3-5 trang đầu là đủ cho real-time (không cần quét hết 100 trang cũ)
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
            if link in seen_links: continue # Đã biết -> Bỏ qua

            # Tìm thấy món mới!
            name = link_tag.text.strip()
            parent = item_div.find_parent()
            price = parent.find('span', class_='product-detail-price').text.strip() if parent and parent.find('span', class_='product-detail-price') else "Liên hệ"

            item_data = {
                'Tên sản phẩm': name, 'Giá': price, 'Link': link,
                'Thời gian quét': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            new_items.append(item_data)
            seen_links.add(link)
            
            # Gửi tin nhắn ngay
            msg = f"🚨 <b>HÀNG MỚI!</b>\n📦 {name}\n💰 {price}\n🔗 <a href='{link}'>Xem ngay</a>"
            send_telegram_msg(msg)
            print(f"-> New: {name}")

        current_start += step
    except Exception as e:
        print(f"Lỗi: {e}")
        break

# 3. Lưu lại vào file CSV (Quan trọng để lần sau không báo trùng)
if new_items:
    print(f"Đã tìm thấy {len(new_items)} món mới. Đang lưu file...")
    file_exists = os.path.exists(csv_filename)
    with open(csv_filename, 'a', newline='', encoding='utf-8-sig') as f:
        fieldnames = ['Tên sản phẩm', 'Giá', 'Link', 'Thời gian quét']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists: writer.writeheader()
        writer.writerows(new_items)
else:
    print("Không có hàng mới.")