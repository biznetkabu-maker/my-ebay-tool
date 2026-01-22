import os
import json
import requests
from bs4 import BeautifulSoup
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time

# 鍵を読み込む設定
def get_gspread_client():
    json_creds = os.environ.get("GSPREAD_SERVICE_ACCOUNT")
    creds_dict = json.loads(json_creds)
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# じゃんぱらで安い「保証あり品」を探す命令
def check_janpara_gold(jan):
    # CHKOUTRE=ON で通販在庫ありに限定
    url = f"https://www.janpara.co.jp/sale/search/result/?KEYWORDS={jan}&CHKOUTRE=ON"
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        items = soup.find_all(class_="item_list")
        
        valid_prices = []
        for item in items:
            text = item.get_text()
            # 保証なし・ジャンク品を排除
            if any(x in text for x in ["保証なし", "ジャンク", "JUNK", "難あり"]):
                continue
            price_tag = item.find(class_="price")
            if price_tag:
                price = int(price_tag.get_text(strip=True).replace("￥", "").replace(",", ""))
                valid_prices.append(price)
        return min(valid_prices) if valid_prices else None
    except:
        return None

# メインの実行処理
def main():
    client = get_gspread_client()
    # スプレッドシートを開く
    sheet = client.open_by_key(os.environ.get("SPREADSHEET_ID")).get_worksheet(0)
    # A列のJANコードを取得
    jan_list = sheet.col_values(1)[1:] 
    
def main():
    client = get_gspread_client()
    sheet = client.open_by_key(os.environ.get("SPREADSHEET_ID")).get_worksheet(0)

    # ✅ JANコード一覧を取得（A列、1行目はヘッダーなので除外）
    jan_list = sheet.col_values(1)[1:]

    for i, jan in enumerate(jan_list, start=2):
        if not jan: continue
        price = check_janpara_gold(jan)
        print(f"JAN: {jan}, price: {price}")  # ログ出力で確認
        if price:
            sheet.update_cell(i, 2, price)
            sheet.update_cell(i, 3, "じゃんぱら(保証あり)")
            time.sleep(2)# サイトへの負荷を抑えるための休憩
print(f"JAN: {jan}, price: {price}")
