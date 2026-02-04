import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import ast

# 1. 網頁基本設定
st.set_page_config(page_title="雲端進階記帳系統 V4 - 旅程智慧選單版", layout="wide")

st.markdown("""
    <style>
    .stCheckbox { margin-top: 15px; }
    .stTextInput { margin-top: 0px; }
    </style>
    """, unsafe_allow_html=True)

st.title("💰 雲端進階記帳結算系統")

# 2. 連接 Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 核心資料讀取 (為了獲取所有旅程清單) ---
def get_full_cloud_data():
    try:
        data = conn.read(worksheet="Log", ttl=0)
        data = data.dropna(how='all')
        if not data.empty:
            data.columns = [str(c).strip() for c in data.columns]
        return data
    except Exception:
        return pd.DataFrame(columns=["日期", "旅程分類", "品名", "付款人", "總金額", "分攤明細"])

full_raw_data = get_full_cloud_data()

# --- 1. 旅程管理 (Sidebar - 箭頭列表與新增功能) ---
with st.sidebar:
    st.header("✈️ 旅程切換")
    
    # 取得現有的旅程清單
    existing_trips = []
    if "旅程分類" in full_raw_data.columns:
        existing_trips = full_raw_data["旅程分類"].unique().tolist()
    
    # 過濾掉空值
    existing_trips = [t for t in existing_trips if str(t).strip() and t != "nan"]
    
    # 建立選單選項
    trip_options = existing_trips + ["➕ 新增新旅程..."]
    
    # 箭頭列表 (下拉選單)
    selected_trip_part = st.selectbox("選擇現有旅程", options=trip_options, index=0 if existing_trips else 0)
    
    # 如果選擇「新增」，才顯示輸入框
    if selected_trip_part == "➕ 新增新旅程...":
        current_trip = st.text_input("輸入新旅程名稱", placeholder="例如：台東、日本...")
    else:
        current_trip = selected_trip_part

    if current_trip:
        st.info(f"📍 目前正在查看/記錄：**{current_trip}**")
    else:
        st.warning("⚠️ 請選擇或輸入一個旅程名稱")

    st.divider()

    st.subheader("👥 成員設定")
    if 'members' not in st.session_state:
        st.session_state.members = ["weiche", "Michael", "Ivy", "Wendy", "Ben", "Xuan", "Kaiwen", "Daniel"]
    
    member_str = st.text_input("編輯成員 (用逗號隔開)", value=", ".join(st.session_state.members))
    if st.button("更新成員名單"):
        st.session_state.members = [m.strip() for m in member_str.split(",") if m.strip()]
        st.rerun()

members = st.session_state.members

# --- 2. 根據目前旅程篩選資料 ---
if not full_raw_data.empty and "旅程分類" in full_raw_data.columns and current_trip:
    df = full_raw_data[full_raw_data["旅程分類"] == current_trip].copy()
else:
    df = pd.DataFrame(columns=["日期", "旅程分類", "品名", "付款人", "總金額", "分攤明細"])

# 3. 新增支出功能 (含驗證功能)
st.subheader(f"➕ 新增支出 - 【{current_trip if current_trip else '未命名旅程'}】")

with st.form("expense_form", clear_on_submit=True):
    col_item, col_payer, col_amt = st.columns([2, 1, 1])
    with col_item:
        item_name = st.text_input("品名", placeholder="例如：早餐、門票...")
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
        # 驗證 1：基本欄位必填
        if not current_trip:
            st.error("❌ 請先在左側選擇或輸入旅程名稱！"); st.stop()
        if not item_name.strip():
            st.error("❌ 請輸入品名！"); st.stop()
        if total_amount <= 0:
            st.error("❌ 支出總金額必須大於 0！"); st.stop()

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
        
        # 驗證 2：手動金額不可超過總額
        if remaining_amt < -0.1:
            st.error(f"❌ 指定金額總和 (${total_manual}) 已超過支出總額 (${total_amount})！"); st.stop()

        if not split_members and total_manual == 0:
            avg = total_amount / len(members)
            final_shares = {m: round(avg, 2) for m in members}
        elif split_members:
            avg = remaining_amt / len(split_members)
            for m in split_members: final_shares[m] += round(avg, 2)
        
        # 驗證 3：分帳總額必須等於總金額
        sum_shares = sum(final_shares.values())
        if abs(sum_shares - total_amount) > 0.1:
            st.error(f"❌ 分攤金額總計 (${sum_shares:.2f}) 與總額不符，請檢查！"); st.stop()

        # 寫入雲端
        new_row = pd.DataFrame([{
            "日期": datetime.date.today().strftime("%Y-%m-%d"),
            "旅程分類": current_trip,
            "品名": item_name,
            "付款人": payer,
            "總金額": total_amount,
            "分攤明細": str(final_shares)
        }])
        
        updated_df = pd.concat([full_raw_data, new_row], ignore_index=True)
        conn.update(worksheet="Log", data=updated_df)
        st.success(f"🎉 成功存入旅程：{current_trip}")
        st.rerun()

# 4. 📜 支出明細與結算 (功能聯動顯示)
st.divider()
if not df.empty:
    st.subheader(f"📜 {current_trip} - 支出詳細清單")
    view_df = df.copy()
    def format_detail(s):
        try:
            d = ast.literal_eval(s)
            return ", ".join([f"{k}: ${v}" for k, v in d.items() if v > 0])
        except: return s
    view_df["幫誰付 (分攤明細)"] = view_df["分攤明細"].apply(format_detail)
    st.dataframe(view_df[["日期", "品名", "付款人", "總金額", "幫誰付 (分攤明細)"]], use_container_width=True, hide_index=True)

    # 刪除功能
    with st.expander("🗑️ 刪除支出紀錄"):
        del_list = [f"{idx} | {row['日期']} | {row['品名']} (${row['總金額']})" for idx, row in df.iterrows()]
        target_del = st.selectbox("選擇要刪除的項目：", options=del_list)
        if st.button("🔴 確認刪除此筆紀錄", type="primary"):
            target_idx = int(target_del.split(" | ")[0])
            final_df = full_raw_data.drop(target_idx).reset_index(drop=True)
            conn.update(worksheet="Log", data=final_df)
            st.success("✅ 紀錄已成功刪除！")
            st.rerun()

    # 結算報告
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
    st.subheader(f"📊 {current_trip} - 結算報告 (誰欠誰錢)")
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
else:
    st.info(f"旅程「{current_trip}」目前尚無資料，請填寫上方表單新增第一筆支出。")
