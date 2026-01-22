import os
import json
import requests
from bs4 import BeautifulSoup
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time

# Google Sheets 認証
def get_gspread_client():
    json_creds = os.environ.get("GSPREAD_SERVICE_ACCOUNT")
    creds_dict = json.loads(json_creds)
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# じゃんぱらで価格を取得
def check_janpara_gold(jan):
    # URLを最新の検索仕様に変更
    url = f"https://www.janpara.co.jp/sale/search/result/?KEYWORDS={jan}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 商品リストを取得
        items = soup.find_all(class_="item_list")
        
        valid_prices = []
        for item in items:
            # 除外設定を一旦外して、確実に数字を拾うようにします
            price_tag = item.select_one(".item_price, .price_detail, .price")
            
            if price_tag:
                price_text = price_tag.get_text(strip=True)
                # 記号を除去して数字だけにする
                price_text = price_text.replace("￥", "").replace(",", "").replace("円", "")
                try:
                    price = int(price_text)
                    valid_prices.append(price)
                except:
                    continue
        
        # 見つかった中から最安値を返す
        return min(valid_prices) if valid_prices else None

    except Exception as e:
        print(f"Error for JAN {jan}: {e}")
        return None

# メイン処理
def main():
    client = get_gspread_client()
    sheet = client.open_by_key(os.environ.get("SPREADSHEET_ID")).get_worksheet(0)
    
    # 2列目（B列）からJANコードを取得
    jan_list = sheet.col_values(1)[1:]
    
    for i, jan in enumerate(jan_list, start=2):
        print(f"行{i}のJANコード: {jan}")
        if not jan:
            continue
            
        price = check_janpara_gold(jan)
        print(f"JAN: {jan}, price: {price}")
        
        if price:
            print("書き込み実行")
            # B列に価格、C列にサイト名を書き込み
            sheet.update_cell(i, 2, price)
            sheet.update_cell(i, 3, "じゃんぱら")
        
        time.sleep(2) # サイトへの負荷軽減

if __name__ == "__main__":
    main()
