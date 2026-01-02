import streamlit as st
import pandas as pd
import gspread
import json
import io
import csv

# 1. 建立連線 (直接讀取 JSON 字串，絕對成功)
try:
    creds_dict = json.loads(st.secrets["JSON_STR"])
    gc = gspread.service_account_from_dict(creds_dict)
    sh = gc.open_by_url("https://docs.google.com/spreadsheets/d/1H56f4EjtInhv7InEbO2mR76XkHMyCMSEQNI6B84HG3M/edit#gid=0")
    worksheet = sh.get_worksheet(0)
except Exception as e:
    st.error(f"連線失敗：{e}")
    st.stop()

# 2. 讀取現有資料
data = worksheet.get_all_records()
history_df = pd.DataFrame(data) if data else pd.DataFrame(columns=["日期", "付款人", "總金額", "分攤細節"])

# --- 計算邏輯 ---
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

# --- UI 介面 ---
st.sidebar.header("👥 成員設定")
member_input = st.sidebar.text_input("成員名稱", "weiche, Michael, Ivy, Wendy, Ben, Xuan, Kaiwen, Daniel")
members = [n.strip() for n in member_input.replace("，", ",").split(",") if n.strip()]
total_paid, total_spent, balances = calculate_all_stats(history_df, members)

st.title("💰 雲端進階記帳系統")

with st.expander("➕ 新增支出 (即時同步雲端)"):
    with st.form("expense_form", clear_on_submit=True):
        payer = st.selectbox("誰付的錢？", members)
        total_amt = st.number_input("支出總金額", min_value=0.0)
        submitted = st.form_submit_button("確認提交")
        
        if submitted:
            # 準備一行資料
            share_each = total_amt / len(members)
            new_row = [
                pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                payer,
                total_amt,
                json.dumps({m: share_each for m in members})
            ]
            # 核心動作：直接新增一行到雲端
            worksheet.append_row(new_row)
            st.success("✅ 資料已同步！")
            st.rerun()

# 顯示報表
st.subheader("📊 目前收支狀態")
st.table(pd.DataFrame([{ "成員": m, "狀態": f"欠 ${balances[m]:.2f}" if balances[m] > 0.01 else f"應收 ${abs(balances[m]):.2f}" if balances[m] < -0.01 else "已清平" } for m in members]))

with st.expander("📜 歷史明細與下載"):
    st.dataframe(history_df)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["日期", "付款人", "金額"])
    for _, r in history_df.iterrows():
        writer.writerow([r["日期"], r["付款人"], r["總金額"]])
    st.download_button("📥 下載報表", output.getvalue().encode('utf-8-sig'), "report.csv")