import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime

# 1. 網頁基本設定
st.set_page_config(page_title="雲端進階記帳結算系統", layout="wide")
st.title("💰 雲端進階記帳結算系統")

# 2. 連接 Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 核心修正：強制重新整理資料 ---
def load_data():
    # ttl=0 確保不使用舊快取，每次都抓最新的雲端資料
    try:
        data = conn.read(worksheet="Log", ttl=0)
        # 清除可能產生的全空行
        data = data.dropna(how='all')
        return data
    except:
        return pd.DataFrame(columns=["日期", "付款人", "總金額", "分攤明細"])

df = load_data()

# 3. 初始化成員清單
if 'members' not in st.session_state:
    st.session_state.members = ["weiche", "Michael", "Ivy", "Wendy", "Ben", "Xuan", "Kaiwen", "Daniel"]

with st.sidebar:
    st.subheader("👥 成員設定")
    member_str = st.text_input("輸入成員名稱 (用逗號隔開)", value=", ".join(st.session_state.members))
    if st.button("更新成員清單"):
        st.session_state.members = [m.strip() for m in member_str.split(",") if m.strip()]
        st.rerun()

members = st.session_state.members

# 4. 新增支出功能
st.subheader("➕ 新增支出 (將即時同步雲端)")
with st.form("expense_form", clear_on_submit=True):
    col_a, col_b = st.columns(2)
    with col_a:
        payer = st.selectbox("誰付的錢？", members)
    with col_b:
        total_amount = st.number_input("支出總金額", min_value=0.0, step=10.0)
    
    st.write("每人分攤金額 (留空則代表平分):")
    shares_input = {}
    cols = st.columns(4)
    for i, m in enumerate(members):
        shares_input[m] = cols[i % 4].text_input(f"{m}", key=f"input_{m}")
    
    submit_button = st.form_submit_button("✅ 確認提交並同步雲端")
    
    if submit_button:
        if total_amount <= 0:
            st.error("請輸入大於 0 的金額")
        else:
            # --- 處理分攤邏輯 ---
            final_shares = {}
            manual_entries = {m: float(val) for m, val in shares_input.items() if val.strip()}
            
            if not manual_entries:
                avg = total_amount / len(members)
                final_shares = {m: round(avg, 2) for m in members}
            else:
                final_shares = {m: manual_entries.get(m, 0.0) for m in members}

            # --- 關鍵修正：先讀取最新資料再合併，避免覆蓋 ---
            current_df = load_data()
            new_row = pd.DataFrame([{
                "日期": datetime.date.today().strftime("%Y-%m-%d"),
                "付款人": payer,
                "總金額": total_amount,
                "分攤明細": str(final_shares)
            }])
            
            updated_df = pd.concat([current_df, new_row], ignore_index=True)
            
            # 寫入雲端
            conn.update(worksheet="Log", data=updated_df)
            st.success("🎉 資料已成功新增，並保留舊紀錄！")
            st.rerun()

# 5. 結算報告
st.divider()
st.subheader("📊 目前收支統計狀態")

# --- 偵錯工具：如果你看不到表格，請取消下面這行的註解來檢查 ---
# st.write("雲端原始資料：", df)

if not df.empty:
    paid_summary = {m: 0.0 for m in members}
    spent_summary = {m: 0.0 for m in members}
    
    # 強制確保 DataFrame 欄位名稱正確
    df.columns = [c.strip() for c in df.columns]

    for _, row in df.iterrows():
        # 付款人累計
        p = str(row.get("付款人", "")).strip()
        amt = row.get("總金額", 0)
        if p in paid_summary:
            paid_summary[p] += float(amt)
            
        # 消費金額累計
        try:
            detail_str = row.get("分攤明細", "{}")
            detail = eval(str(detail_str))
            for m, s in detail.items():
                if m in spent_summary:
                    spent_summary[m] += float(s)
        except:
            continue

    # 顯示統計表
    status_data = []
    for m in members:
        # 淨額 = 自己吃掉的 - 自己墊的
        # 正數 = 欠別人的；負數 = 別人欠你的
        net = spent_summary[m] - paid_summary[m]
        status_data.append({
            "成員": m,
            "總代墊 (付出的錢)": f"${paid_summary[m]:,.2f}",
            "個人總花費": f"${spent_summary[m]:,.2f}",
            "目前的餘額狀態": f"🔴 欠 ${net:,.2f}" if net > 0.1 else (f"🟢 應收 ${abs(net):,.2f}" if net < -0.1 else "⚪ 已清平"),
            "raw_net": net
        })
    
    st.table(pd.DataFrame(status_data).drop(columns=["raw_net"]))

    # 6. 計算誰給誰多少錢
    if st.button("🔍 生成最簡轉帳建議"):
        debtors = sorted([[m, spent_summary[m] - paid_summary[m]] for m in members if (spent_summary[m] - paid_summary[m]) > 0.1], key=lambda x: x[1], reverse=True)
        creditors = sorted([[m, abs(spent_summary[m] - paid_summary[m])] for m in members if (spent_summary[m] - paid_summary[m]) < -0.1], key=lambda x: x[1], reverse=True)
        
        if not debtors:
            st.write("✅ 目前帳目完全平衡，不需要轉帳！")
        else:
            i, j = 0, 0
            while i < len(debtors) and j < len(creditors):
                amt = min(debtors[i][1], creditors[j][1])
                st.info(f"💸 **{debtors[i][0]}** ➜ 給 **{creditors[j][0]}**： `${amt:,.2f}`")
                debtors[i][1] -= amt
                creditors[j][1] -= amt
                if debtors[i][1] < 0.1: i += 1
                if creditors[j][1] < 0.1: j += 1
else:
    st.info("💡 雲端目前沒有任何記帳紀錄。")