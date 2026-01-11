import requests
from bs4 import BeautifulSoup
import csv
import os
import time
import re  # Thêm thư viện để xử lý số điểm
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Cấu hình AI
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    # Dùng model nào bạn check được ở bước trước (gemini-1.5-flash hoặc gemini-pro)
    model = genai.GenerativeModel('gemini-1.5-flash') 

def phan_tich_va_cham_diem(ten_sp, gia_sp):
    """Hàm nhờ AI chấm điểm và nhận xét"""
    if not GEMINI_API_KEY:
        return 0, "⚠️ (Chưa có API Key)"
    
    try:
        # Prompt được thiết kế để AI trả về đúng định dạng
        prompt = (
            f"Bạn là chuyên gia định giá đồ cũ khắt khe. "
            f"Sản phẩm: '{ten_sp}'. Giá bán: '{gia_sp}'.\n"
            f"Hãy chấm điểm độ 'hời' trên thang 1-10:\n"
            f"- 1-6: Đắt hoặc bình thường, không đáng quan tâm.\n"
            f"- 7-8: Giá ổn, mua dùng được.\n"
            f"- 9-10: CỰC HỜI, KHÔNG MUA LÀ TIẾC (Rất hiếm).\n\n"
            f"YÊU CẦU TRẢ LỜI ĐÚNG ĐỊNH DẠNG SAU (Không thêm bớt):\n"
            f"DIEM: [Điểm số]\n"
            f"NHANXET: [Nhận xét ngắn gọn dưới 2 câu]"
        )
        response = model.generate_content(prompt)
        content = response.text.strip()

        # Xử lý kết quả trả về để tách Điểm và Nhận xét
        # Tìm số điểm trong dòng có chữ "DIEM:"
        diem_match = re.search(r"DIEM:\s*(\d+)", content)
        diem = int(diem_match.group(1)) if diem_match else 0
        
        # Lấy phần nhận xét
        nhan_xet = content.split("NHANXET:")[-1].strip() if "NHANXET:" in content else content

        return diem, nhan_xet

    except Exception as e:
        if "429" in str(e):
            return 0, "⚠️ AI quá tải"
        return 0, f"Lỗi AI: {str(e)[:20]}..."

def send_telegram_msg(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    try:
        api_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        params = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'HTML'}
        requests.get(api_url, params=params)
    except Exception as e:
        print(f"Lỗi gửi Telegram: {e}")

# --- CẤU HÌNH ---
# Lưu ý: URL phải là API load_product để lấy dữ liệu json/html, không phải link trang web
url = "https://2handland.com/ajax/load_product" 
csv_filename = 'danh_sach_san_pham.csv'

# MỨC ĐIỂM SÀN ĐỂ GỬI TIN NHẮN (Bạn có thể chỉnh số này)
# Để 9 nghĩa là chỉ 9 và 10 mới gửi.
DIEM_TOI_THIEU = 9 

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

# 2. Quét
current_start = 0
step = 48
new_items = []
MAX_PAGES = 3 

for _ in range(MAX_PAGES): 
    # Logic payload cho trang 2handland
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
            
            # Chỉ lấy link sản phẩm
            if "san-pham" not in link: continue
            
            # --- QUAN TRỌNG: Bật lại bộ lọc link cũ ---
            if link in seen_links: continue 

            # --- TÌM THẤY HÀNG MỚI ---
            name = link_tag.text.strip()
            parent = item_div.find_parent()
            price = "Liên hệ"
            if parent and parent.find('span', class_='product-detail-price'):
                price = parent.find('span', class_='product-detail-price').text.strip()

            print(f"-> Soi món mới: {name} ({price})...")
            
            # --- GỌI AI CHẤM ĐIỂM ---
            diem, nhan_xet = phan_tich_va_cham_diem(name, price)
            print(f"   => AI chấm: {diem}/10 điểm.")

            # --- QUYẾT ĐỊNH CÓ GỬI TELEGRAM KHÔNG? ---
            if diem >= DIEM_TOI_THIEU:
                icon_hot = "🔥" * (diem - 8) # 9 điểm 1 lửa, 10 điểm 2 lửa
                msg = (
                    f"{icon_hot} <b>PHÁT HIỆN DEAL HỜI ({diem}/10)!</b>\n"
                    f"📦 <b>{name}</b>\n"
                    f"💰 Giá: {price}\n"
                    f"🤖 <b>AI Phán:</b> <i>{nhan_xet}</i>\n"
                    f"🔗 <a href='{link}'>Múc ngay kẻo lỡ</a>"
                )
                send_telegram_msg(msg)
                print("   ✅ Đã gửi tin nhắn Telegram!")
            else:
                print("   ❌ Điểm thấp, không nhắn tin.")

            # Vẫn lưu vào CSV để lần sau không quét lại nữa (dù điểm thấp hay cao)
            item_data = {
                'Tên sản phẩm': name, 'Giá': price, 'Link': link,
                'Thời gian quét': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            new_items.append(item_data)
            seen_links.add(link)
            
            # Nghỉ 20s để tránh lỗi 429 quota
            time.sleep(30)

        current_start += step
    except Exception as e:
        print(f"Lỗi vòng lặp: {e}")
        break

# 3. Lưu file
if new_items:
    print(f"Đã xử lý xong {len(new_items)} món mới.")
    file_exists = os.path.exists(csv_filename)
    with open(csv_filename, 'a', newline='', encoding='utf-8-sig') as f:
        fieldnames = ['Tên sản phẩm', 'Giá', 'Link', 'Thời gian quét']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists: writer.writeheader()
        writer.writerows(new_items)
else:
    print("Không có hàng mới.")