import os
import json
import requests
from bs4 import BeautifulSoup
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import urllib.parse

def get_gspread_client():
    json_creds = os.environ.get("GSPREAD_SERVICE_ACCOUNT")
    creds_dict = json.loads(json_creds)
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# 1. JANから商品名を取得
def get_product_name_by_jan(jan):
    app_id = os.environ.get("RAKUTEN_APP_ID")
    url = f"https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601?format=json&keyword={jan}&applicationId={app_id}"
    try:
        res = requests.get(url, timeout=10)
        data = res.json()
        if data.get("Items"):
            full_name = data["Items"][0]["Item"]["itemName"]
            # 不要な記号を消す
            clean = full_name.replace("【", " ").replace("】", " ").replace("中古", "").replace("★", "").replace("(", " ").replace(")", " ")
            words = clean.split()
            # 最初の2〜3単語を使用
            return " ".join(words[:3]) if len(words) >= 3 else " ".join(words)
    except:
        return None

# 2. じゃんぱら検索（再試行ロジック付き）
def check_janpara_with_retry(name):
    if not name: return None
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    
    # 検索ワードを少しずつ短くしながら最大2回トライする
    search_words = name.split()
    attempts = [
        " ".join(search_words),      # 1回目: そのまま (例: Nintendo Switch Joy-Con)
        " ".join(search_words[:2])   # 2回目: 短くする (例: Nintendo Switch)
    ]
    
    for term in attempts:
        # スペースを + に変換してURL作成 (CHKOUTRE=ONで在庫ありに絞り込み)
        encoded_term = urllib.parse.quote_plus(term)
        url = f"https://www.janpara.co.jp/sale/search/result/?KEYWORDS={encoded_term}&CHKOUTRE=ON"
        
        try:
            res = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            items = soup.select(".item_list")
            
            valid_prices = []
            for item in items:
                if "品切れ" in item.get_text() or "SOLD" in item.get_text().upper():
                    continue
                price_tag = item.select_one(".item_price, .price_detail, .price")
                if price_tag:
                    price_num = "".join(filter(str.isdigit, price_tag.get_text()))
                    if price_num:
                        valid_prices.append(int(price_num))
            
            if valid_prices:
                return min(valid_prices) # 見つかったら即座に返す
        except:
            continue
        time.sleep(1) # 再試行前の待機
    return None

def main():
    client = get_gspread_client()
    sheet = client.open_by_key(os.environ.get("SPREADSHEET_ID")).get_worksheet(0)
    jan_list = sheet.col_values(1)[1:] 
    
    for i, jan in enumerate(jan_list, start=2):
        print(f"--- 行{i} 処理開始 ---")
        if not jan or len(str(jan)) < 10: continue
            
        name = get_product_name_by_jan(jan)
        print(f"検索ワード案: {name}")
        
        price = check_janpara_with_retry(name)
        print(f"最終取得価格: {price}")
        
        if price:
            sheet.update_cell(i, 2, price)
            sheet.update_cell(i, 3, f"じゃんぱら({name})")
        
        time.sleep(3)

if __name__ == "__main__":
    main()
