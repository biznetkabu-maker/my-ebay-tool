import os
import json
import requests
from bs4 import BeautifulSoup
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import re
import urllib.parse

def get_gspread_client():
    json_creds = os.environ.get("GSPREAD_SERVICE_ACCOUNT")
    creds_dict = json.loads(json_creds)
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# 1. 楽天APIで商品名を取得（これは安定しているのでそのまま）
def get_product_name_by_jan(jan):
    app_id = os.environ.get("RAKUTEN_APP_ID")
    url = f"https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601?format=json&keyword={jan}&applicationId={app_id}"
    try:
        res = requests.get(url, timeout=10)
        data = res.json()
        if data.get("Items"):
            name = data["Items"][0]["Item"]["itemName"]
            return re.sub(r'[【】★（）()]', ' ', name).split()[0:3] # 最初の3単語をリストで返す
    except:
        return None

# 2. じゃんぱら攻略ロジック（JAN + キーワードの波状攻撃）
def fetch_janpara_price(jan, name_words):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    
    # 検索パターンの作成（1. JANコード, 2. 商品名, 3. JAN末尾数桁など）
    search_queries = [jan]
    if name_words:
        search_queries.append(" ".join(name_words))
    
    for query in search_queries:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.janpara.co.jp/sale/search/result/?KEYWORDS={encoded}&CHKOUTRE=ON"
        
        try:
            res = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            items = soup.select(".item_list")
            
            prices = []
            for item in items:
                if any(x in item.get_text() for x in ["品切れ", "SOLD OUT"]): continue
                p_tag = item.select_one(".item_price, .price_detail, .price")
                if p_tag:
                    num = "".join(re.findall(r'\d+', p_tag.get_text()))
                    if num: prices.append(int(num))
            
            if prices: return min(prices)
        except:
            continue
        time.sleep(1)
    return None

def main():
    client = get_gspread_client()
    sheet = client.open_by_key(os.environ.get("SPREADSHEET_ID")).get_worksheet(0)
    jan_list = sheet.col_values(1)[1:] 
    
    for i, jan in enumerate(jan_list, start=2):
        print(f"--- 行{i} 処理: {jan} ---")
        if not jan: continue
            
        name_words = get_product_name_by_jan(jan)
        print(f"商品名推測: {' '.join(name_words) if name_words else 'NG'}")
        
        price = fetch_janpara_price(jan, name_words)
        print(f"最終価格: {price}")
        
        if price:
            sheet.update_cell(i, 2, price)
            sheet.update_cell(i, 3, f"じゃんぱら取得成功")
        else:
            sheet.update_cell(i, 3, "じゃんぱら在庫なし")
        
        time.sleep(3)

if __name__ == "__main__":
    main()
