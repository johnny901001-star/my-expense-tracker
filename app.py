import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import ast  # 比 eval 更安全的解析工具

# 1. 網頁基本設定
st.set_page_config(page_title="雲端進階記帳結算系統", layout="wide")
st.title("💰 雲端進階記帳結算系統")

# 2. 連接 Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 核心修正：強制清除快取並重新讀取 ---
def load_full_data():
    st.cache_data.clear()
    try:
        data = conn.read(worksheet="Log", ttl=0)
        data = data.dropna(how='all')
        data.columns = [str(c).strip() for c in data.columns]
        return data
    except Exception as e:
        st.error(f"連線或讀取失敗: {e}")
        # 這裡增加了 "品名" 預設欄位
        return pd.DataFrame(columns=["日期", "品名", "付款人", "總金額", "分攤明細"])

df = load_full_data()

# 3. 初始化成員清單
if 'members' not in st.session_state:
    st.session_state.members = ["weiche", "Michael", "Ivy", "Wendy", "Ben", "Xuan", "Kaiwen", "Daniel"]

with st.sidebar:
    st.subheader("👥 成員設定")
    member_str = st.text_input("輸入成員名稱", value=", ".join(st.session_state.members))
    if st.button("更新成員"):
        st.session_state.members = [m.strip() for m in member_str.split(",") if m.strip()]
        st.rerun()

members = st.session_state.members

# 4. 新增支出功能
st.subheader("➕ 新增支出 (同步雲端)")
with st.form("expense_form", clear_on_submit=True):
    # 新增品名與付款人、金額排列
    col_item, col_payer, col_amt = st.columns([2, 1, 1])
    with col_item:
        item_name = st.text_input("品名 (例：晚餐、計程車)", placeholder="請輸入支出項目...")
    with col_payer:
        payer = st.selectbox("誰付的錢？", members)
    with col_amt:
        total_amount = st.number_input("支出總金額", min_value=0.0, step=10.0)
    
    st.write("每人分攤金額 (留空代表平分):")
    shares_input = {}
    cols = st.columns(4)
    for i, m in enumerate(members):
        shares_input[m] = cols[i % 4].text_input(f"{m}", key=f"input_{m}")
    
    submit_button = st.form_submit_button("✅ 確認提交並保留舊紀錄")
    
    if submit_button:
        # 計算分攤
        final_shares = {}
        manual_entries = {m: float(val) for m, val in shares_input.items() if val.strip()}
        if not manual_entries:
            avg = total_amount / len(members)
            final_shares = {m: round(avg, 2) for m in members}
        else:
            final_shares = {m: manual_entries.get(m, 0.0) for m in members}

        # 寫入前再次抓取
        fresh_df = load_full_data()
        
        new_row = pd.DataFrame([{
            "日期": datetime.date.today().strftime("%Y-%m-%d"),
            "品名": item_name,  # 儲存品名
            "付款人": payer,
            "總金額": total_amount,
            "分攤明細": str(final_shares)
        }])
        
        updated_df = pd.concat([fresh_df, new_row], ignore_index=True)
        conn.update(worksheet="Log", data=updated_df)
        st.success(f"🎉 【{item_name}】已成功存入！")
        st.rerun()

# 5. 結算報告
st.divider()
st.subheader("📊 收支統計狀態")

with st.expander("🛠️ 系統偵錯面板 (查看雲端原始資料)"):
    st.dataframe(df)

if not df.empty:
    paid_summary = {m: 0.0 for m in members}
    spent_summary = {m: 0.0 for m in members}

    for _, row in df.iterrows():
        p = str(row.get("付款人", "")).strip()
        amt = row.get("總金額", 0)
        if p in paid_summary:
            paid_summary[p] += float(amt)
            
        try:
            d_str = str(row.get("分攤明細", "{}")).strip()
            detail = ast.literal_eval(d_str)
            for m, s in detail.items():
                m_clean = str(m).strip()
                if m_clean in spent_summary:
                    spent_summary[m_clean] += float(s)
        except:
            continue

    status_list = []
    for m in members:
        net = spent_summary[m] - paid_summary[m]
        status_list.append({
            "成員": m,
            "代墊總額": paid_summary[m],
            "消費總額": spent_summary[m],
            "結餘狀態": f"🔴 欠 ${net:.2f}" if net > 0.1 else (f"🟢 應收 ${abs(net):.2f}" if net < -0.1 else "⚪ 已清平"),
            "net": net
        })
    
    st.table(pd.DataFrame(status_list).drop(columns=["net"]))

    if st.button("🔍 計算誰該給誰錢"):
        debtors = sorted([[m, spent_summary[m] - paid_summary[m]] for m in members if (spent_summary[m] - paid_summary[m]) > 0.1], key=lambda x: x[1], reverse=True)
        creditors = sorted([[m, abs(spent_summary[m] - paid_summary[m])] for m in members if (spent_summary[m] - paid_summary[m]) < -0.1], key=lambda x: x[1], reverse=True)
        
        i, j = 0, 0
        while i < len(debtors) and j < len(creditors):
            transfer = min(debtors[i][1], creditors[j][1])
            st.info(f"💸 **{debtors[i][0]}** ➜ 給 **{creditors[j][0]}**： `${transfer:.2f}`")
            debtors[i][1] -= transfer
            creditors[j][1] -= transfer
            if debtors[i][1] < 0.1: i += 1
            if creditors[j][1] < 0.1: j += 1
else:
    st.info("💡 雲端目前是空的，請先新增支出。")

# 6. 底部小計算機
st.divider()
st.subheader("🧮 快速計算小工具")
with st.container():
    calc_col1, calc_col2 = st.columns([3, 1])
    with calc_col1:
        calc_input = st.text_input("輸入算式 (例如: 1250 + 480/2)", placeholder="請輸入數學算式...")
    with calc_col2:
        if calc_input:
            try:
                # 使用 eval 進行基礎運算，並加入簡易安全檢查
                result = eval(calc_input, {"__builtins__": None}, {})
                st.metric("計算結果", f"{result:.2f}")
            except Exception:
                st.error("算式錯誤")
        else:
            st.write("等待輸入...")
