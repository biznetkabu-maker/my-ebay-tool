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

# じゃんぱらで「保証あり品」の最安価格を取得
def check_janpara_gold(jan):
    url = f"https://www.janpara.co.jp/sale/search/result/?KEYWORDS={jan}&CHKOUTRE=ON"
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        items = soup.find_all(class_="item_list")

        valid_prices = []
        for item in items:
            text = item.get_text()
            if any(x in text for x in ["保証なし", "ジャンク", "JUNK", "難あり"]):
                continue

            price_tag = item.select_one(".item_price, .price_detail, .price")
            if price_tag:
                price_text = price_tag.get_text(strip=True)
                price_text = price_text.replace("¥", "").replace(",", "").replace("円", "")
                try:
                    price = int(price_text)
                    valid_prices.append(price)
                except:
                    continue

        return min(valid_prices) if valid_prices else None

    except Exception as e:
        print(f"Error for JAN {jan}: {e}")
        return None

# メイン処理
def main():
    client = get_gspread_client()
    sheet = client.open_by_key(os.environ.get("SPREADSHEET_ID")).get_worksheet(0)

    # ★★★ これが無いと絶対に動かない ★★★
    jan_list = sheet.col_values(1)[1:]

    for i, jan in enumerate(jan_list, start=2):
        print(f"行{i}のJANコード: {jan}")
        if not jan:
            continue

        price = check_janpara_gold(jan)
        print(f"JAN: {jan}, price: {price}")

        if price:
            print("書き込み実行")
            sheet.update_cell(i, 2, price)
            sheet.update_cell(i, 3, "じゃんぱら(保証あり)")
            time.sleep(2)

if __name__ == "__main__":
    main()
