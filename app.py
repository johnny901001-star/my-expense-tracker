import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import ast

# 1. 網頁基本設定
st.set_page_config(page_title="雲端進階記帳系統 V4 - 穩定建表版", layout="wide")

st.markdown("""
    <style>
    .stCheckbox { margin-top: 15px; }
    .stTextInput { margin-top: 0px; }
    </style>
    """, unsafe_allow_html=True)

st.title("💰 雲端進階記帳結算系統")

# 2. 連接 Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 核心邏輯改進：確保工作表存在 ---
def ensure_worksheet_exists(sheet_name):
    """
    更穩定的建表邏輯：直接透過網址開啟試算表並建立分頁
    """
    try:
        # 測試是否能讀取，若成功則直接回傳
        conn.read(worksheet=sheet_name, ttl=0)
    except Exception:
        try:
            # 從 secrets 取得試算表網址
            # 如果你的 secrets 格式不同，請確保這裡指向正確的 URL
            spreadsheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
            
            # 使用底層 client 強行打開試算表
            sh = conn.client.open_by_url(spreadsheet_url)
            
            # 建立新工作表
            sh.add_worksheet(title=sheet_name, rows="1000", cols="10")
            
            # 寫入初始標題列，確保後續讀取不會報錯
            df_init = pd.DataFrame(columns=["日期", "品名", "付款人", "總金額", "分攤明細"])
            conn.update(worksheet=sheet_name, data=df_init)
            st.toast(f"✅ 已成功建立新分頁：{sheet_name}")
        except Exception as e:
            st.error(f"❌ 自動建表失敗：{e}")
            st.info("請檢查：1. Secrets 中的 spreadsheet 網址是否正確。 2. 帳號是否有編輯權限。")
            st.stop()

# --- 3. 旅程與成員管理 (Sidebar) ---
with st.sidebar:
    st.header("✈️ 旅程切換")
    trip_name = st.text_input("輸入當前旅程分頁名稱", value="Log")
    
    if "current_trip" not in st.session_state or st.session_state.current_trip != trip_name:
        st.session_state.current_trip = trip_name
        st.cache_data.clear()

    st.info(f"📍 目前記錄於：**{st.session_state.current_trip}**")
    st.divider()

    st.subheader("👥 成員設定")
    if 'members' not in st.session_state:
        st.session_state.members = ["weiche", "Michael", "Ivy", "Wendy", "Ben", "Xuan", "Kaiwen", "Daniel"]
    
    member_str = st.text_input("編輯成員 (用逗號隔開)", value=", ".join(st.session_state.members))
    if st.button("更新成員名單"):
        st.session_state.members = [m.strip() for m in member_str.split(",") if m.strip()]
        st.rerun()

members = st.session_state.members

# 4. 資料讀取函數
def load_full_data():
    try:
        data = conn.read(worksheet=st.session_state.current_trip, ttl=0)
        data = data.dropna(how='all')
        if data.empty:
            return pd.DataFrame(columns=["日期", "品名", "付款人", "總金額", "分攤明細"])
        data.columns = [str(c).strip() for c in data.columns]
        return data
    except Exception:
        return pd.DataFrame(columns=["日期", "品名", "付款人", "總金額", "分攤明細"])

df = load_full_data()

# 5. 新增支出功能
st.subheader(f"➕ 新增支出 - 【{st.session_state.current_trip}】")

with st.form("expense_form", clear_on_submit=True):
    col_item, col_payer, col_amt = st.columns([2, 1, 1])
    with col_item:
        item_name = st.text_input("品名", placeholder="例如：晚餐、機票...")
    with col_payer:
        payer = st.selectbox("誰付的錢？", members)
    with col_amt:
        total_amount = st.number_input("支出總金額", min_value=0.0, step=1.0, format="%.2f")
    
    st.write("📝 **分攤設定**")
    check_states = {}; manual_values = {}
    outer_cols = st.columns(2)
    for i, m in enumerate(members):
        with outer_cols[i % 2]:
            st.markdown(f"**👤 {m}**")
            c1, c2 = st.columns([1, 2])
            with c1:
                check_states[m] = st.checkbox("平分", key=f"check_{m}")
            with c2:
                manual_values[m] = st.text_input("指定金額", key=f"val_{m}", placeholder="0.0", label_visibility="collapsed")
            st.markdown("---")

    if st.form_submit_button("✅ 提交紀錄至雲端", use_container_width=True):
        final_shares = {m: 0.0 for m in members}
        total_manual = 0.0
        split_members = [m for m, checked in check_states.items() if checked]
        
        for m, val in manual_values.items():
            if val.strip():
                try:
                    amt = float(val)
                    final_shares[m] = amt
                    total_manual += amt
                except ValueError:
                    st.error(f"❌ {m} 的金額格式錯誤"); st.stop()

        remaining_amt = total_amount - total_manual
        if not split_members and total_manual == 0:
            avg = total_amount / len(members)
            final_shares = {m: round(avg, 2) for m in members}
        elif split_members:
            if remaining_amt < -0.01:
                st.error(f"❌ 指定金額超過總額"); st.stop()
            avg = remaining_amt / len(split_members)
            for m in split_members: final_shares[m] += round(avg, 2)
        
        if not item_name:
            st.error("❌ 請輸入品名")
        else:
            # 1. 確保分頁存在 (使用改進後的邏輯)
            ensure_worksheet_exists(st.session_state.current_trip)
            
            # 2. 準備資料
            new_row = pd.DataFrame([{
                "日期": datetime.date.today().strftime("%Y-%m-%d"),
                "品名": item_name,
                "付款人": payer,
                "總金額": total_amount,
                "分攤明細": str(final_shares)
            }])
            
            # 3. 重新抓取最新資料並合併
            current_df = load_full_data()
            updated_df = pd.concat([current_df, new_row], ignore_index=True)
            
            # 4. 更新雲端
            conn.update(worksheet=st.session_state.current_trip, data=updated_df)
            st.success(f"🎉 儲存成功！")
            st.rerun()

# --- 6. 支出明細與結算報告 (與之前邏輯相同) ---
st.divider()
if not df.empty:
    st.subheader(f"📜 {st.session_state.current_trip} - 支出清單")
    view_df = df.copy()
    def format_detail(s):
        try:
            d = ast.literal_eval(s)
            return ", ".join([f"{k}: ${v}" for k, v in d.items() if v > 0])
        except: return s
    view_df["幫誰付 (分攤明細)"] = view_df["分攤明細"].apply(format_detail)
    st.dataframe(view_df[["日期", "品名", "付款人", "總金額", "幫誰付 (分攤明細)"]], use_container_width=True, hide_index=True)

    # 結算數據處理
    paid = {m: 0.0 for m in members}; spent = {m: 0.0 for m in members}
    for _, row in df.iterrows():
        p = str(row.get("付款人", "")).strip()
        if p in paid: paid[p] += float(row.get("總金額", 0))
        try:
            detail = ast.literal_eval(str(row.get("分攤明細", "{}")))
            for m, s in detail.items():
                if m.strip() in spent: spent[m.strip()] += float(s)
        except: continue
    
    st.divider()
    st.subheader(f"📊 {st.session_state.current_trip} - 結算報告")
    status_data = []
    for m in members:
        net = spent[m] - paid[m]
        status_data.append({
            "成員": m, "代墊總計": f"${paid[m]:.1f}", "消費總計": f"${spent[m]:.1f}",
            "目前狀態": f"🔴 欠 ${net:.1f}" if net > 0.1 else (f"🟢 應收 ${abs(net):.1f}" if net < -0.1 else "⚪ 已清算"),
            "net": net
        })
    st.table(pd.DataFrame(status_data).drop(columns=["net"]))

    if st.button("🔍 計算最優還款路徑"):
        debtors = sorted([[m, spent[m] - paid[m]] for m in members if (spent[m] - paid[m]) > 0.1], key=lambda x: x[1], reverse=True)
        creditors = sorted([[m, abs(spent[m] - paid[m])] for m in members if (spent[m] - paid[m]) < -0.1], key=lambda x: x[1], reverse=True)
        i, j = 0, 0
        while i < len(debtors) and j < len(creditors):
            transfer = min(debtors[i][1], creditors[j][1])
            st.success(f"💸 **{debtors[i][0]}** ➜ 給 **{creditors[j][0]}**： **${transfer:.1f}**")
            debtors[i][1] -= transfer; creditors[j][1] -= transfer
            if debtors[i][1] < 0.1: i += 1
            if creditors[j][1] < 0.1: j += 1


