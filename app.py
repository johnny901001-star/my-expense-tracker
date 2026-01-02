import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# 設定網頁標題
st.set_page_config(page_title="進階揪團記帳系統", layout="centered")

st.title("💰 進階揪團記帳結算系統")

# --- 1. 連接 Google Sheets ---
# 在 Streamlit Cloud 上，我們需要設定 secrets
conn = st.connection("gsheets", type=GSheetsConnection)

# 讀取現有資料 (假設工作表名稱為 'Log')
try:
    df = conn.read(worksheet="Log", ttl="0")
except:
    # 如果是第一次運行，建立空資料表
    df = pd.DataFrame(columns=["付款人", "總金額", "分攤明細"])

# --- 2. 初始化成員 ---
if 'members' not in st.session_state:
    st.session_state.members = ["weiche", "Michael", "Ivy", "Wendy", "Ben", "Xuan", "Kaiwen", "Daniel"]

with st.expander("👥 成員設定"):
    member_str = st.text_input("輸入成員名稱 (以逗號隔開)", value=", ".join(st.session_state.members))
    if st.button("更新成員"):
        st.session_state.members = [m.strip() for m in member_str.split(",") if m.strip()]
        st.rerun()

members = st.session_state.members

# --- 3. 新增支出功能 ---
st.subheader("➕ 新增支出")
with st.form("expense_form", clear_on_submit=True):
    payer = st.selectbox("付款人", members)
    total_amount = st.number_input("支出總金額", min_value=0.0, step=10.0)
    
    st.write("每人分攤金額 (留空代表平分)")
    shares = {}
    cols = st.columns(2)
    for i, m in enumerate(members):
        shares[m] = cols[i % 2].text_input(f"{m} 的金額", key=f"share_{m}")
    
    submit = st.form_submit_button("送出紀錄")
    
    if submit:
        # 處理分攤邏輯
        processed_shares = {}
        manual_sum = 0
        has_manual = any(s.strip() for s in shares.values())
        
        if not has_manual:
            avg = total_amount / len(members)
            processed_shares = {m: avg for m in members}
        else:
            for m in members:
                val = float(shares[m]) if shares[m].strip() else 0
                processed_shares[m] = val
                manual_sum += val
            
            if abs(manual_sum - total_amount) > 0.1:
                st.warning(f"注意：分攤總和 ${manual_sum} 與總金額 ${total_amount} 不符")

        # 寫入 Google Sheets
        new_row = pd.DataFrame([{
            "付款人": payer,
            "總金額": total_amount,
            "分攤明細": str(processed_shares)
        }])
        
        updated_df = pd.concat([df, new_row], ignore_index=True)
        conn.update(worksheet="Log", data=updated_df)
        st.success("紀錄已成功同步至 Google Sheets！")
        st.rerun()

# --- 4. 計算結算與統計 ---
st.divider()
st.subheader("📊 結算報告")

if not df.empty:
    # 初始化統計字典
    total_paid = {m: 0.0 for m in members}
    total_spent = {m: 0.0 for m in members}
    
    for _, row in df.iterrows():
        p = row["付款人"]
        amt = row["總金額"]
        # 安全解析字典字串
        try:
            s_dict = eval(row["分攤明細"])
            if p in total_paid: total_paid[p] += amt
            for m, s in s_dict.items():
                if m in total_spent: total_spent[m] += s
        except:
            continue

    # 顯示表格
    status_data = []
    for m in members:
        balance = total_spent[m] - total_paid[m] # 正數代表欠錢，負數代表應收
        status_data.append({
            "成員": m,
            "總代墊": total_paid[m],
            "個人花費": total_spent[m],
            "結餘 (負數為應收)": round(balance, 2)
        })
    
    st.table(pd.DataFrame(status_data))

    # 簡易結算邏輯 (轉帳建議)
    if st.button("生成轉帳建議"):
        balances = {m: total_spent[m] - total_paid[m] for m in members}
        debtors = sorted([[n, b] for n, b in balances.items() if b > 0.1], key=lambda x: x[1], reverse=True)
        creditors = sorted([[n, abs(b)] for n, b in balances.items() if b < -0.1], key=lambda x: x[1], reverse=True)
        
        i, j = 0, 0
        while i < len(debtors) and j < len(creditors):
            amt = min(debtors[i][1], creditors[j][1])
            st.info(f"💸 **{debtors[i][0]}** ➜ **{creditors[j][0]}** : `${amt:.2f}`")
            debtors[i][1] -= amt
            creditors[j][1] -= amt
            if debtors[i][1] < 0.1: i += 1
            if creditors[j][1] < 0.1: j += 1
else:
    st.info("目前尚無資料")