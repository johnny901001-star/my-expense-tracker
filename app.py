import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import json

# 設定網頁標題
st.set_page_config(page_title="進階雲端記帳系統", page_icon="💰")

# 1. 建立 Google Sheets 連線
conn = st.connection("gsheets", type=GSheetsConnection)

# 2. 定義核心邏輯：從歷史紀錄計算狀態
def calculate_status(history_df, members):
    balances = {m: 0.0 for m in members}
    total_paid = {m: 0.0 for m in members}
    total_spent = {m: 0.0 for m in members}
    
    for _, row in history_df.iterrows():
        payer = row['付款人']
        total = float(row['總金額'])
        # 將存儲的 JSON 字串轉回字典
        shares = json.loads(row['分攤明細'])
        
        total_paid[payer] += total
        balances[payer] -= total
        for m, s in shares.items():
            if m in total_spent:
                total_spent[m] += float(s)
                balances[m] += float(s)
                
    return total_paid, total_spent, balances

# --- 側邊欄：成員設定 ---
st.sidebar.header("👥 成員設定")
default_members = "weiche, Michael, Ivy, Wendy, Ben, Xuan, Kaiwen, Daniel"
member_input = st.sidebar.text_input("輸入成員名稱 (逗號隔開)", default_members)
members = [n.strip() for n in member_input.replace("，", ",").split(",") if n.strip()]

# 3. 讀取雲端資料
try:
    history_df = conn.read()
except:
    # 如果是空的，建立初始格式
    history_df = pd.DataFrame(columns=["日期", "付款人", "總金額", "分攤明細"])

# 計算目前狀態
total_paid, total_spent, balances = calculate_status(history_df, members)

# --- 主畫面 ---
st.title("💰 雲端進階記帳結算系統")

if not members:
    st.info("請在左側選單設定成員")
else:
    # 1. 新增支出區塊 (你原本的完整分攤邏輯)
    with st.expander("➕ 新增一筆支出 (資料將同步至雲端)"):
        with st.form("expense_form"):
            payer = st.selectbox("誰付的錢？", members)
            total_amt = st.number_input("支出總金額", min_value=0.0, step=1.0)
            
            st.write("每人分攤金額 (留空則代表平分):")
            manual_shares_input = {}
            cols = st.columns(2)
            for idx, m in enumerate(members):
                with cols[idx % 2]:
                    val = st.text_input(f"{m} 的分攤", key=f"share_{m}")
                    manual_shares_input[m] = val

            submitted = st.form_submit_button("提交並儲存至雲端")
            
            if submitted:
                processed_shares = {}
                filled_shares = {m: float(v) for m, v in manual_shares_input.items() if v.strip()}
                
                if not filled_shares:
                    share_each = total_amt / len(members)
                    processed_shares = {m: share_each for m in members}
                else:
                    processed_shares = filled_shares
                
                # 建立新資料列 (將分攤明細轉為 JSON 字串存入)
                new_row = pd.DataFrame([{
                    "日期": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "付款人": payer,
                    "總金額": total_amt,
                    "分攤明細": json.dumps(processed_shares)
                }])
                
                # 合併並更新雲端
                updated_df = pd.concat([history_df, new_row], ignore_index=True)
                conn.update(data=updated_df)
                st.success("✅ 紀錄已成功同步至 Google Sheets！")
                st.rerun() # 重新整理頁面以更新數據

    # 2. 數據呈現 (你原本的表格)
    st.subheader("📊 目前收支狀態")
    status_list = []
    for m in members:
        bal = balances[m]
        status = f"欠 ${bal:.2f}" if bal > 0.01 else f"應收 ${abs(bal):.2f}" if bal < -0.01 else "已清平"
        status_list.append({
            "成員": m,
            "總代墊": f"${total_paid[m]:.2f}",
            "個人總花費": f"${total_spent[m]:.2f}",
            "目前狀態": status
        })
    st.table(pd.DataFrame(status_list))

    # 3. 結算建議 (你原本的精華算法)
    if st.button("🏁 生成最終結算方案"):
        st.subheader("💡 轉帳建議 (最簡化路徑)")
        debtors = sorted([[n, b] for n, b in balances.items() if b > 0.01], key=lambda x: x[1], reverse=True)
        creditors = sorted([[n, abs(b)] for n, b in balances.items() if b < -0.01], key=lambda x: x[1], reverse=True)

        i, j = 0, 0
        if not debtors:
            st.write("所有帳目已平！")
        else:
            while i < len(debtors) and j < len(creditors):
                amt = min(debtors[i][1], creditors[j][1])
                st.info(f"💸 **{debtors[i][0]}** ➜ **{creditors[j][0]}** : `${amt:.2f}`")
                debtors[i][1] -= amt
                creditors[j][1] -= amt
                if debtors[i][1] < 0.01: i += 1
                if creditors[j][1] < 0.01: j += 1

    # 4. 歷史明細
    with st.expander("📜 查看雲端歷史明細"):
        st.dataframe(history_df)

if st.sidebar.button("⚠️ 危險：清空雲端所有紀錄"):
    empty_df = pd.DataFrame(columns=["日期", "付款人", "總金額", "分攤明細"])
    conn.update(data=empty_df)
    st.sidebar.error("資料已全數刪除")
    st.rerun()