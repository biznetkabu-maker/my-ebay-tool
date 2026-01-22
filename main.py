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

# 1. 楽天API：エラーが出ないようシンプルに改良
def get_product_name_by_jan(jan):
    app_id = os.environ.get("RAKUTEN_APP_ID")
    url = f"https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601?format=json&keyword={jan}&applicationId={app_id}"
    try:
        res = requests.get(url, timeout=10)
        data = res.json()
        if data.get("Items"):
            name = data["Items"][0]["Item"]["itemName"]
            # 検索用の単語を抽出（記号を消して最初の2語）
            clean_name = re.sub(r'[^\w\s]', ' ', name)
            words = clean_name.split()
            return words[:2]
    except:
        pass
    return None

# 2. じゃんぱらで価格取得
def fetch_janpara(jan):
    url = f"https://www.janpara.co.jp/sale/search/result/?KEYWORDS={jan}&CHKOUTRE=ON"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        prices = [int("".join(re.findall(r'\d+', p.text))) for p in soup.select(".item_price") if "品切れ" not in p.parent.text]
        return min(prices) if prices else None
    except:
        return None

# 3. イオシスで価格取得（追加！）
def fetch_iosis(jan):
    url = f"https://iosys.co.jp/items?q={jan}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        # 価格が記載されているクラスを探す
        price_tags = soup.select(".item-list__price")
        prices = [int("".join(re.findall(r'\d+', p.text))) for p in price_tags]
        return min(prices) if prices else None
    except:
        return None

def main():
    client = get_gspread_client()
    sheet = client.open_by_key(os.environ.get("SPREADSHEET_ID")).get_worksheet(0)
    jan_list = sheet.col_values(1)[1:] 
    
    for i, jan in enumerate(jan_list, start=2):
        print(f"--- 行{i} 処理: {jan} ---")
        if not jan: continue
        
        # 複数サイトを回って一番安い価格を探す
        price_janpara = fetch_janpara(jan)
        price_iosis = fetch_iosis(jan)
        
        # 有効な価格の中から最小値を選択
        valid_prices = [p for p in [price_janpara, price_iosis] if p is not None]
        final_price = min(valid_prices) if valid_prices else None
        
        print(f"じゃんぱら: {price_janpara}, イオシス: {price_iosis}")
        
        if final_price:
            source = "じゃんぱら" if final_price == price_janpara else "イオシス"
            sheet.update_cell(i, 2, final_price)
            sheet.update_cell(i, 3, f"{source}から取得")
            print(f"書き込み成功: {final_price}")
        else:
            sheet.update_cell(i, 3, "全サイト在庫なし")
        
        time.sleep(2)

if __name__ == "__main__":
    main()
