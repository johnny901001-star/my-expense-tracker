import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime

# 1. 網頁基本設定
st.set_page_config(page_title="雲端進階記帳結算系統", layout="wide")
st.title("💰 雲端進階記帳結算系統")

# 2. 連接 Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 核心修正：強制重新整理資料 (解決覆蓋問題) ---
def load_data_from_gsheets():
    try:
        # 使用 ttl=0 強制不使用快取，保證抓到雲端最新狀態
        data = conn.read(worksheet="Log", ttl=0)
        # 自動清除欄位名稱前後的空格 (解決統計不動的問題)
        data.columns = [str(c).strip() for c in data.columns]
        # 移除全空的行
        data = data.dropna(how='all')
        return data
    except Exception as e:
        st.error(f"讀取資料失敗: {e}")
        return pd.DataFrame(columns=["日期", "付款人", "總金額", "分攤明細"])

# 初始讀取
df = load_data_from_gsheets()

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
st.subheader("➕ 新增支出")
with st.form("expense_form", clear_on_submit=True):
    col_a, col_b = st.columns(2)
    with col_a:
        payer = st.selectbox("誰付的錢？", members)
    with col_b:
        total_amount = st.number_input("支出總金額", min_value=0.0, step=10.0)
    
    st.write("每人分攤金額 (留空代表平分):")
    shares_input = {}
    cols = st.columns(4)
    for i, m in enumerate(members):
        shares_input[m] = cols[i % 4].text_input(f"{m}", key=f"input_{m}")
    
    submit_button = st.form_submit_button("✅ 確認提交 (新增至下一行)")
    
    if submit_button:
        if total_amount <= 0:
            st.warning("請輸入有效的金額。")
        else:
            # 計算分攤邏輯
            final_shares = {}
            manual_entries = {m: float(val) for m, val in shares_input.items() if val.strip()}
            if not manual_entries:
                avg = total_amount / len(members)
                final_shares = {m: round(avg, 2) for m in members}
            else:
                final_shares = {m: manual_entries.get(m, 0.0) for m in members}

            # --- 關鍵修正：寫入前「再讀一次」最新資料，確保不覆蓋 ---
            latest_df = load_data_from_gsheets()
            
            new_row = pd.DataFrame([{
                "日期": datetime.date.today().strftime("%Y-%m-%d"),
                "付款人": payer,
                "總金額": total_amount,
                "分攤明細": str(final_shares)
            }])
            
            # 將新資料接到舊資料後面
            updated_df = pd.concat([latest_df, new_row], ignore_index=True)
            
            # 更新回雲端
            conn.update(worksheet="Log", data=updated_df)
            st.success(f"🎉 成功新增！目前共有 {len(updated_df)} 筆紀錄。")
            st.rerun()

# 5. 結算報告
st.divider()
st.subheader("📊 目前收支統計狀態")

# --- 偵錯功能 (若統計不動，請看這裡顯示的內容) ---
with st.expander("🔍 點開查看雲端原始資料內容"):
    st.write(df)

if not df.empty:
    paid_summary = {m: 0.0 for m in members}
    spent_summary = {m: 0.0 for m in members}

    for _, row in df.iterrows():
        # 讀取並清除付款人空格
        p_in_row = str(row.get("付款人", "")).strip()
        amt = row.get("總金額", 0)
        
        if p_in_row in paid_summary:
            paid_summary[p_in_row] += float(amt)
            
        try:
            # 解析分攤明細字典
            detail_str = str(row.get("分攤明細", "{}"))
            detail = eval(detail_str)
            for m, s in detail.items():
                m_clean = str(m).strip()
                if m_clean in spent_summary:
                    spent_summary[m_clean] += float(s)
        except:
            continue

    # 建立統計表格
    status_list = []
    for m in members:
        net = spent_summary[m] - paid_summary[m]
        status_list.append({
            "成員": m,
            "總代墊 (付出)": f"${paid_summary[m]:,.2f}",
            "個人總花費": f"${spent_summary[m]:,.2f}",
            "狀態": f"🔴 欠 ${net:,.2f}" if net > 0.1 else (f"🟢 應收 ${abs(net):,.2f}" if net < -0.1 else "⚪ 已清平"),
            "raw_net": net
        })
    
    st.table(pd.DataFrame(status_list).drop(columns=["raw_net"]))

    # 6. 計算結算建議
    if st.button("🔍 生成轉帳建議"):
        debtors = sorted([[m, spent_summary[m] - paid_summary[m]] for m in members if (spent_summary[m] - paid_summary[m]) > 0.1], key=lambda x: x[1], reverse=True)
        creditors = sorted([[m, abs(spent_summary[m] - paid_summary[m])] for m in members if (spent_summary[m] - paid_summary[m]) < -0.1], key=lambda x: x[1], reverse=True)
        
        i, j = 0, 0
        while i < len(debtors) and j < len(creditors):
            transfer = min(debtors[i][1], creditors[j][1])
            st.info(f"💸 **{debtors[i][0]}** ➜ 給 **{creditors[j][0]}**： `${transfer:,.2f}`")
            debtors[i][1] -= transfer
            creditors[j][1] -= transfer
            if debtors[i][1] < 0.1: i += 1
            if creditors[j][1] < 0.1: j += 1
else:
    st.info("💡 目前雲端沒有紀錄，請新增資料。")