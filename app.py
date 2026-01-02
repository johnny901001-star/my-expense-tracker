import streamlit as st
import pandas as pd
import csv
import json
import io
from streamlit_gsheets import GSheetsConnection

# 0. 設定網頁標題與圖示
st.set_page_config(page_title="雲端進階記帳結算系統", page_icon="💰", layout="wide")

# 1. 初始化 Google Sheets 連線
conn = st.connection("gsheets", type=GSheetsConnection)

# 2. 核心邏輯：從雲端歷史紀錄計算所有人的收支狀態
def calculate_all_stats(df, members):
    balances = {m: 0.0 for m in members}
    total_paid = {m: 0.0 for m in members}
    total_spent = {m: 0.0 for m in members}
    
    for _, row in df.iterrows():
        try:
            payer = str(row['付款人']).strip()
            total = float(row['總金額'])
            # 將儲存的 JSON 字串轉回字典格式
            shares = json.loads(row['分攤細節'])
            
            if payer in total_paid:
                total_paid[payer] += total
                balances[payer] -= total
            
            for m, s in shares.items():
                member_name = str(m).strip()
                if member_name in total_spent:
                    total_spent[member_name] += float(s)
                    balances[member_name] += float(s)
        except:
            continue # 跳過格式不正確的列
    return total_paid, total_spent, balances

# --- 側邊欄：成員設定 ---
st.sidebar.header("👥 成員設定")
member_input = st.sidebar.text_input("輸入成員名稱 (用半角逗號隔開)", "weiche, Michael, Ivy, Wendy, Ben, Xuan, Kaiwen, Daniel")
members = [n.strip() for n in member_input.replace("，", ",").split(",") if n.strip()]

# 3. 讀取雲端歷史紀錄 (從 Google Sheets 抓取)
try:
    # 每次跑程式都會重新讀取雲端最新資料
    history_df = conn.read()
except:
    # 如果試算表是全新的，建立基礎欄位
    history_df = pd.DataFrame(columns=["日期", "付款人", "總金額", "分攤細節"])

# 計算目前即時統計
total_paid, total_spent, balances = calculate_all_stats(history_df, members)

# --- 主畫面 UI ---
st.title("💰 雲端進階記帳結算系統")

if not members:
    st.info("請在左側選單輸入成員名稱並開始使用")
else:
    # 區塊 A：新增支出 (保留你原始的手動分攤邏輯)
    with st.expander("➕ 新增一筆支出 (資料將同步至雲端)"):
        with st.form("expense_form", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            with col_a:
                payer = st.selectbox("誰付的錢？", members)
            with col_b:
                total_amt = st.number_input("支出總金額", min_value=0.0, step=1.0)
            
            st.write("每人分攤金額 (若全部留空則代表大家平分):")
            share_inputs = {}
            cols = st.columns(4) # 四欄佈局節省空間
            for idx, m in enumerate(members):
                with cols[idx % 4]:
                    val = st.text_input(f"{m} 的分攤", key=f"in_{m}")
                    share_inputs[m] = val

            submitted = st.form_submit_button("確認提交並上傳雲端")
            
            if submitted:
                # 處理分攤金額逻辑
                manual_shares = {m: float(v) for m, v in share_inputs.items() if v.strip()}
                if not manual_shares:
                    share_each = total_amt / len(members)
                    final_shares = {m: share_each for m in members}
                else:
                    final_shares = manual_shares
                
                # 準備上傳的一列資料
                new_entry = pd.DataFrame([{
                    "日期": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                    "付款人": payer,
                    "總金額": total_amt,
                    "分攤細節": json.dumps(final_shares) # 複雜分攤存成 JSON
                }])
                
                # 合併新舊資料並寫回 Google Sheets
                updated_history = pd.concat([history_df, new_entry], ignore_index=True)
                conn.update(data=updated_history)
                st.success("✅ 紀錄已成功同步至雲端！")
                st.rerun()

    # 區塊 B：數據呈現表格 (你原本的狀態表格)
    st.subheader("📊 目前收支狀態")
    status_list = []
    for m in members:
        bal = balances[m]
        status = f"欠 ${bal:.2f}" if bal > 0.01 else f"應收 ${abs(bal):.2f}" if bal < -0.01 else "已清平"
        status_list.append({
            "成員": m,
            "代墊總計 (付出的錢)": f"${total_paid[m]:.2f}",
            "個人總花費 (吃掉的錢)": f"${total_spent[m]:.2f}",
            "目前餘額狀態": status
        })
    st.table(pd.DataFrame(status_list))

    # 區塊 C：結算建議 (你原本最精華的算法)
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

    # 區塊 D：歷史紀錄與 CSV 下載 (修正後的代碼)
# --- 歷史明細與 CSV 匯出 (修正 TypeError 版) ---
with st.expander("📜 歷史明細與下載"):
    st.dataframe(history_df)
    
    # 關鍵修正點：使用 io.StringIO 而不是 BytesIO
    output = io.StringIO()
    writer = csv.writer(output)
    
    # 寫入標題與資料
    writer.writerow(["成員個人統計"])
    writer.writerow(["姓名", "總共代墊金額", "個人消費總額", "最終差額(負數為應收)"])
    
    for m in members:
        writer.writerow([m, total_paid[m], total_spent[m], balances[m]])
    
    # 下載時轉換成 bytes 並加上 utf-8-sig 解決 Excel 亂碼
    st.download_button(
        label="📥 下載結算報表 (CSV)",
        data=output.getvalue().encode('utf-8-sig'), 
        file_name="expense_report.csv",
        mime="text/csv"
    )

# 區塊 E：側邊欄重置
if st.sidebar.button("⚠️ 危險：清空雲端並重設系統"):
    empty_df = pd.DataFrame(columns=["日期", "付款人", "總金額", "分攤細節"])
    conn.update(data=empty_df)
    st.sidebar.error("資料已全數刪除")
    st.rerun()