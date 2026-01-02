import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime

# 1. 網頁基本設定
st.set_page_config(page_title="雲端進階記帳結算系統", layout="centered")
st.title("💰 雲端進階記帳結算系統")

# 2. 連接 Google Sheets
# 注意：這會去讀取你在 Secrets 設定的 URL
conn = st.connection("gsheets", type=GSheetsConnection)

# 讀取現有資料 (這裡指定讀取名為 "Log" 的分頁)
try:
    # ttl="0" 代表不快取，每次重新整理都會讀取最新資料
    df = conn.read(worksheet="Log", ttl="0")
except Exception as e:
    # 如果讀取失敗（例如分頁不存在），建立一個符合你影片格式的空資料表
    df = pd.DataFrame(columns=["日期", "付款人", "總金額", "分攤明細"])

# 3. 初始化成員清單
if 'members' not in st.session_state:
    st.session_state.members = ["weiche", "Michael", "Ivy", "Wendy", "Ben", "Xuan", "Kaiwen", "Daniel"]

with st.expander("👥 成員設定"):
    member_str = st.text_input("輸入成員名稱 (用半角逗號隔開)", value=", ".join(st.session_state.members))
    if st.button("更新成員"):
        st.session_state.members = [m.strip() for m in member_str.split(",") if m.strip()]
        st.rerun()

members = st.session_state.members

# 4. 新增支出功能 (表單介面)
st.subheader("➕ 新增支出 (將即時同步雲端)")
with st.form("expense_form", clear_on_submit=True):
    payer = st.selectbox("誰付的錢？", members)
    total_amount = st.number_input("支出總金額", min_value=0.0, step=10.0)
    
    st.write("每人分攤金額 (留空則代表平分):")
    shares_input = {}
    cols = st.columns(2)
    for i, m in enumerate(members):
        shares_input[m] = cols[i % 2].text_input(f"{m} 的分攤", key=f"input_{m}")
    
    submit_button = st.form_submit_button("送出紀錄並同步")
    
    if submit_button:
        # --- 分攤邏輯計算 ---
        final_shares = {}
        manual_entries = {m: float(val) for m, val in shares_input.items() if val.strip()}
        
        if not manual_entries:
            # 全部平分
            avg = total_amount / len(members)
            final_shares = {m: round(avg, 2) for m in members}
        else:
            # 使用手動輸入的金額
            final_shares = {m: manual_entries.get(m, 0.0) for m in members}
            if abs(sum(final_shares.values()) - total_amount) > 0.1:
                st.warning(f"提醒：分攤總和 ${sum(final_shares.values())} 與總金額 ${total_amount} 有落差")

        # --- 寫入 Google Sheets (關鍵修正點) ---
        new_data = pd.DataFrame([{
            "日期": datetime.date.today().strftime("%Y-%m-%d"),
            "付款人": payer,
            "總金額": total_amount,
            "分攤明細": str(final_shares)
        }])
        
        # 合併新舊資料
        updated_df = pd.concat([df, new_data], ignore_index=True)
        
        # 修正後的 update 指令：明確指定 worksheet="Log"
        conn.update(worksheet="Log", data=updated_df)
        
        st.success("✅ 紀錄已成功寫入 Google 試算表！")
        st.rerun()

# 5. 結算報告
st.divider()
st.subheader("📊 目前結算狀態")

if not df.empty and "分攤明細" in df.columns:
    # 統計邏輯
    paid_summary = {m: 0.0 for m in members}
    spent_summary = {m: 0.0 for m in members}
    
    for _, row in df.iterrows():
        p = row["付款人"]
        amt = row["總金額"]
        try:
            detail = eval(row["分攤明細"])
            if p in paid_summary: paid_summary[p] += amt
            for m, s in detail.items():
                if m in spent_summary: spent_summary[m] += s
        except:
            continue

    # 顯示統計表
    display_df = pd.DataFrame([
        {
            "成員": m,
            "總代墊金額": paid_summary[m],
            "個人總消費": spent_summary[m],
            "應付/應收": round(spent_summary[m] - paid_summary[m], 2)
        } for m in members
    ])
    st.table(display_df)

    # 轉帳建議按鈕
    if st.button("點我計算最簡轉帳方案"):
        balances = {m: spent_summary[m] - paid_summary[m] for m in members}
        debtors = sorted([[n, b] for n, b in balances.items() if b > 0.1], key=lambda x: x[1], reverse=True)
        creditors = sorted([[n, abs(b)] for n, b in balances.items() if b < -0.1], key=lambda x: x[1], reverse=True)
        
        if not debtors and not creditors:
            st.write("目前帳目已平，不需要轉帳！")
        else:
            i, j = 0, 0
            while i < len(debtors) and j < len(creditors):
                transfer = min(debtors[i][1], creditors[j][1])
                st.info(f"👉 **{debtors[i][0]}** 應給 **{creditors[j][0]}** `${transfer:.2f}`")
                debtors[i][1] -= transfer
                creditors[j][1] -= transfer
                if debtors[i][1] < 0.1: i += 1
                if creditors[j][1] < 0.1: j += 1
else:
    st.info("尚未有任何紀錄，請從上方新增。")