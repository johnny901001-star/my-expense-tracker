import streamlit as st
import pandas as pd
import csv
import json
import io
from streamlit_gsheets import GSheetsConnection

# 設定網頁標題
st.set_page_config(page_title="雲端進階記帳結算系統", page_icon="💰")

# 1. 建立 Google Sheets 連線
conn = st.connection("gsheets", type=GSheetsConnection)

# 2. 核心邏輯：從雲端歷史紀錄計算統計數據
def calculate_all_stats(df, members):
    balances = {m: 0.0 for m in members}
    total_paid = {m: 0.0 for m in members}
    total_spent = {m: 0.0 for m in members}
    
    for _, row in df.iterrows():
        try:
            payer = row['付款人']
            total = float(row['總金額'])
            shares = json.loads(row['分攤細節'])
            
            if payer in total_paid:
                total_paid[payer] += total
                balances[payer] -= total
            
            for m, s in shares.items():
                if m in total_spent:
                    total_spent[m] += float(s)
                    balances[m] += float(s)
        except:
            continue
    return total_paid, total_spent, balances

# --- 側邊欄：成員設定 ---
st.sidebar.header("👥 成員設定")
member_input = st.sidebar.text_input("輸入成員名稱 (逗號隔開)", "weiche, Michael, Ivy, Wendy, Ben, Xuan, Kaiwen, Daniel")
members = [n.strip() for n in member_input.replace("，", ",").split(",") if n.strip()]

# 讀取雲端歷史紀錄
try:
    history_df = conn.read()
except:
    history_df = pd.DataFrame(columns=["日期", "付款人", "總金額", "分攤細節"])

# 計算即時統計
total_paid, total_spent, balances = calculate_all_stats(history_df, members)

# --- 主畫面 ---
st.title("💰 雲端進階記帳結算系統")

if not members:
    st.info("請在左側選單設定成員名稱並重設系統")
else:
    # 1. 新增支出區塊 (保留你原本的手動分攤邏輯)
    with st.expander("➕ 新增一筆支出"):
        with st.form("expense_form", clear_on_submit=True):
            payer = st.selectbox("誰付的錢？", members)
            total_amt = st.number_input("支出總金額", min_value=0.0, step=1.0)
            
            st.write("每人分攤金額 (留空則代表平分):")
            share_inputs = {}
            cols = st.columns(2)
            for idx, m in enumerate(members):
                with cols[idx % 2]:
                    val = st.text_input(f"{m} 的分攤", key=f"in_{m}")
                    share_inputs[m] = val

            submitted = st.form_submit_button("確認提交並同步雲端")
            
            if submitted:
                # 處理分攤邏輯
                manual_shares = {m: float(v) for m, v in share_inputs.items() if v.strip()}
                if not manual_shares:
                    share_each = total_amt / len(members)
                    final_shares = {m: share_each for m in members}
                else:
                    final_shares = manual_shares
                
                # 準備上傳雲端的一列資料
                new_entry = pd.DataFrame([{
                    "日期": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                    "付款人": payer,
                    "總金額": total_amt,
                    "分攤細節": json.dumps(final_shares)
                }])
                
                # 更新至 Google Sheets
                updated_history = pd.concat([history_df, new_entry], ignore_index=True)
                conn.update(data=updated_history)
                st.success("✅ 資料已同步至 Google 試算表！")
                st.rerun()

    # 2. 數據呈現 (表格)
    st.subheader("📊 目前收支狀態")
    status_data = []
    for m in members:
        bal = balances[m]
        status = f"欠 ${bal:.2f}" if bal > 0.01 else f"應收 ${abs(bal):.2f}" if bal < -0.01 else "已清平"
        status_data.append({
            "成員": m,
            "代墊總計": f"${total_paid[m]:.2f}",
            "個人總花費": f"${total_spent[m]:.2f}",
            "目前狀態": status
        })
    st.table(pd.DataFrame(status_data))

    # 3. 結算建議 (核心算法)
    if st.button("🏁 生成最終結算方案"):
        st.subheader("💡 轉帳建議 (最簡化路徑)")
        debtors = sorted([[n, b] for n, b in balances.items() if b > 0.01], key=lambda x: x[1], reverse=True)
        creditors = sorted([[n, abs(b)] for n, b in balances.items() if b < -0.01], key=lambda x: x[1], reverse=True)

        i, j = 0, 0
        if not debtors:
            st.write("目前所有帳目已平。")
        else:
            while i < len(debtors) and j < len(creditors):
                amt = min(debtors[i][1], creditors[j][1])
                st.info(f"💸 **{debtors[i][0]}** ➜ **{creditors[j][0]}** : `${amt:.2f}`")
                debtors[i][1] -= amt
                creditors[j][1] -= amt
                if debtors[i][1] < 0.01: i += 1
                if creditors[j][1] < 0.01: j += 1

    # 4. 歷史明細與 CSV 匯出 (修復 TypeError)
    with st.expander("📜 歷史明細與下載"):
        st.dataframe(history_df)
        
        # 修正後的 CSV 匯出邏輯
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["成員個人統計"])
        writer.writerow(["姓名", "總共代墊金額", "個人消費總額", "最終差額"])
        for m in members:
            writer.writerow([m, total_paid[m], total_spent[m], balances[m]])
        
        st.download_button(
            label="📥 下載結算報表 (CSV)",
            data=output.getvalue().encode('utf-8-sig'), # 加上 utf-8-sig 解決 Excel 中文亂碼
            file_name="expense_report.csv",
            mime="text/csv"
        )

# 重置按鈕
if st.sidebar.button("⚠️ 清空雲端並重設系統"):
    empty_df = pd.DataFrame(columns=["日期", "付款人", "總金額", "分攤細節"])
    conn.update(data=empty_df)
    st.sidebar.error("雲端存檔已清空")
    st.rerun()