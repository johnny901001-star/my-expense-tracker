import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import ast

# 1. 網頁基本設定
st.set_page_config(page_title="雲端進階記帳系統 V4 - 自動建表版", layout="wide")

# 自定義 CSS
st.markdown("""
    <style>
    .stCheckbox { margin-top: 15px; }
    .stTextInput { margin-top: 0px; }
    </style>
    """, unsafe_allow_html=True)

st.title("💰 雲端進階記帳結算系統")

# 2. 連接 Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 旅程與成員管理 (Sidebar) ---
with st.sidebar:
    st.header("✈️ 旅程切換")
    
    # 讓使用者輸入旅程名稱
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

# --- 核心邏輯：自動檢查與建立工作表 ---
def ensure_worksheet_exists(sheet_name):
    """
    檢查工作表是否存在，若不存在則建立它並初始化標題列
    """
    try:
        # 嘗試讀取，如果失敗會報錯
        conn.read(worksheet=sheet_name, ttl=0)
    except Exception:
        # 進入這裡代表工作表不存在
        # 獲取背後的 gspread 試算表物件
        # 注意：這取決於你的 gsheets 連接方式，通常可透過以下方式存取
        try:
            # 取得 spreadsheet 實例
            spreadsheet = conn._spreadsheet
            # 建立新工作表 (預設 1000 列, 20 欄)
            spreadsheet.add_worksheet(title=sheet_name, rows="1000", cols="20")
            
            # 初始化標題列
            df_init = pd.DataFrame(columns=["日期", "品名", "付款人", "總金額", "分攤明細"])
            conn.update(worksheet=sheet_name, data=df_init)
            st.toast(f"✅ 已為您建立新工作表：{sheet_name}")
        except Exception as e:
            st.error(f"無法自動建立工作表，請手動在 Google Sheets 建立名為 '{sheet_name}' 的分頁。錯誤: {e}")

# 3. 資料讀取函數
def load_full_data():
    try:
        data = conn.read(worksheet=st.session_state.current_trip, ttl=0)
        data = data.dropna(how='all')
        if data.empty:
            return pd.DataFrame(columns=["日期", "品名", "付款人", "總金額", "分攤明細"])
        data.columns = [str(c).strip() for c in data.columns]
        return data
    except Exception:
        # 如果讀取失敗（通常是因為工作表還沒建立）
        return pd.DataFrame(columns=["日期", "品名", "付款人", "總金額", "分攤明細"])

df = load_full_data()

# 4. 新增支出功能
st.subheader(f"➕ 新增支出 - 【{st.session_state.current_trip}】")

with st.form("expense_form", clear_on_submit=True):
    col_item, col_payer, col_amt = st.columns([2, 1, 1])
    with col_item:
        item_name = st.text_input("品名", placeholder="例如：晚餐、機票...")
    with col_payer:
        payer = st.selectbox("誰付的錢？", members)
    with col_amt:
        total_amount = st.number_input("支出總金額", min_value=0.0, step=1.0, format="%.2f")
    
    st.write("📝 **分攤設定** (勾選=參與平分 / 填寫數字=指定金額)")
    
    check_states = {}
    manual_values = {}
    
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

    submit_button = st.form_submit_button("✅ 提交紀錄至雲端", use_container_width=True)
    
    if submit_button:
        # ... (中間計算邏輯相同，省略部分以保持簡潔) ...
        final_shares = {m: 0.0 for m in members}
        total_manual = 0.0
        manual_members = []
        split_members = [m for m, checked in check_states.items() if checked]
        
        for m, val in manual_values.items():
            if val.strip():
                try:
                    amt = float(val)
                    final_shares[m] = amt
                    total_manual += amt
                    manual_members.append(m)
                except ValueError:
                    st.error(f"❌ {m} 的金額格式錯誤"); st.stop()

        remaining_amt = total_amount - total_manual
        if not split_members and not manual_members:
            avg = total_amount / len(members)
            final_shares = {m: round(avg, 2) for m in members}
        elif split_members:
            if remaining_amt < -0.01:
                st.error(f"❌ 指定金額總和超過總金額"); st.stop()
            avg = remaining_amt / len(split_members)
            for m in split_members: final_shares[m] += round(avg, 2)
        
        if not item_name:
            st.error("❌ 請輸入品名")
        else:
            # --- 關鍵修正處 ---
            # 1. 確保工作表存在
            ensure_worksheet_exists(st.session_state.current_trip)
            
            # 2. 重新讀取（避免建立新表後讀取舊緩存）
            fresh_df = load_full_data()
            new_row = pd.DataFrame([{
                "日期": datetime.date.today().strftime("%Y-%m-%d"),
                "品名": item_name,
                "付款人": payer,
                "總金額": total_amount,
                "分攤明細": str(final_shares)
            }])
            updated_df = pd.concat([fresh_df, new_row], ignore_index=True)
            
            # 3. 更新
            conn.update(worksheet=st.session_state.current_trip, data=updated_df)
            st.success(f"🎉 儲存成功！")
            st.rerun()

# --- 5. 📜 支出明細 與 6. 📊 結算報告 (與之前程式碼相同) ---
st.divider()
st.subheader(f"📜 {st.session_state.current_trip} - 支出詳細清單")
if not df.empty:
    def format_detail(detail_str):
        try:
            d = ast.literal_eval(detail_str)
            return ", ".join([f"{k}: ${v}" for k, v in d.items() if v > 0])
        except: return detail_str

    view_df = df.copy()
    view_df["幫誰付 (分攤明細)"] = view_df["分攤明細"].apply(format_detail)
    st.dataframe(view_df[["日期", "品名", "付款人", "總金額", "幫誰付 (分攤明細)"]], use_container_width=True, hide_index=True)

    with st.expander("🗑️ 刪除紀錄"):
        del_opt = [f"{i} | {row['日期']} | {row['品名']} (${row['總金額']})" for i, row in df.iterrows()]
        target = st.selectbox("選擇要刪除的項目：", options=del_opt)
        if st.button("確認刪除", type="primary"):
            idx = int(target.split(" | ")[0])
            updated_df = df.drop(idx).reset_index(drop=True)
            conn.update(worksheet=st.session_state.current_trip, data=updated_df)
            st.rerun()

st.divider()
st.subheader(f"📊 {st.session_state.current_trip} - 結算報告")
if not df.empty:
    paid = {m: 0.0 for m in members}; spent = {m: 0.0 for m in members}
    for _, row in df.iterrows():
        p = str(row.get("付款人", "")).strip()
        if p in paid: paid[p] += float(row.get("總金額", 0))
        try:
            detail = ast.literal_eval(str(row.get("分攤明細", "{}")))
            for m, s in detail.items():
                if m.strip() in spent: spent[m.strip()] += float(s)
        except: continue
    
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



