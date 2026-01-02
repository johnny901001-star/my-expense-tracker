import streamlit as st
import pandas as pd
import gspread
import json
import io
import csv

# 0. 網頁基本設定
st.set_page_config(page_title="雲端進階記帳系統", page_icon="💰", layout="wide")

# 1. 建立連線 (跳過 st.connection 的複雜設定)
try:
    # 直接讀取 Secrets 裡的單一字串變數
    secret_json = json.loads(st.secrets["GOOGLE_JSON_KEY"])
    gc = gspread.service_account_from_dict(secret_json)
    
    # 連結您的試算表 (請確認您的試算表名稱是 Expense_Data)
    sh = gc.open_by_url("https://docs.google.com/spreadsheets/d/1H56f4EjtInhv7InEbO2mR76XkHMyCMSEQNI6B84HG3M/edit#gid=0")
    worksheet = sh.get_worksheet(0) # 取得第一個工作表
except Exception as e:
    st.error(f"連線失敗，請確認 Secrets 是否正確貼上：{e}")
    st.stop()

# 2. 讀取與計算邏輯 (保持您原本的邏輯)
data = worksheet.get_all_records()
history_df = pd.DataFrame(data) if data else pd.DataFrame(columns=["日期", "付款人", "總金額", "分攤細節"])

def calculate_all_stats(df, members):
    balances = {m: 0.0 for m in members}
    total_paid = {m: 0.0 for m in members}
    total_spent = {m: 0.0 for m in members}
    for _, row in df.iterrows():
        try:
            payer = str(row['付款人']).strip()
            total = float(row['總金額'])
            shares = json.loads(row['分攤細節'])
            if payer in total_paid:
                total_paid[payer] += total
                balances[payer] -= total
            for m, s in shares.items():
                if m in total_spent:
                    total_spent[m] += float(s)
                    balances[m] += float(s)
        except: continue
    return total_paid, total_spent, balances

# --- 側邊欄與 UI ---
st.sidebar.header("👥 成員設定")
member_input = st.sidebar.text_input("輸入成員名稱", "weiche, Michael, Ivy, Wendy, Ben, Xuan, Kaiwen, Daniel")
members = [n.strip() for n in member_input.replace("，", ",").split(",") if n.strip()]
total_paid, total_spent, balances = calculate_all_stats(history_df, members)

st.title("💰 雲端進階記帳結算系統")

if members:
    # 區塊 A：新增支出 (寫入功能)
    with st.expander("➕ 新增支出"):
        with st.form("expense_form", clear_on_submit=True):
            payer = st.selectbox("誰付的錢？", members)
            total_amt = st.number_input("支出總金額", min_value=0.0)
            submitted = st.form_submit_button("確認提交")
            
            if submitted:
                # 預設平分邏輯
                share_each = total_amt / len(members)
                final_shares = {m: share_each for m in members}
                
                # 直接寫入最後一行
                new_row = [
                    pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                    payer,
                    total_amt,
                    json.dumps(final_shares)
                ]
                worksheet.append_row(new_row)
                st.success("✅ 紀錄已成功存入 Google Sheets！")
                st.rerun()

    # 區塊 B：報表與下載 (修復版)
    st.subheader("📊 目前收支狀態")
    st.table(pd.DataFrame([{ "成員": m, "狀態": f"欠 ${balances[m]:.2f}" if balances[m]>0 else f"應收 ${abs(balances[m]):.2f}" } for m in members]))

    with st.expander("📜 歷史明細"):
        st.dataframe(history_df)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["成員統計"])
        for m in members: writer.writerow([m, balances[m]])
        st.download_button("📥 下載結算報表", output.getvalue().encode('utf-8-sig'), "report.csv")