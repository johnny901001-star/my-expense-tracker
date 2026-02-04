import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import ast

# 1. 網頁基本設定
st.set_page_config(page_title="雲端進階記帳系統 V4 - 旅程標籤版", layout="wide")

st.markdown("""
    <style>
    .stCheckbox { margin-top: 15px; }
    .stTextInput { margin-top: 0px; }
    </style>
    """, unsafe_allow_html=True)

st.title("💰 雲端進階記帳結算系統")

# 2. 連接 Google Sheets (固定讀取 Log 分頁)
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 旅程管理 (Sidebar) ---
with st.sidebar:
    st.header("✈️ 旅程切換")
    # 使用者在這邊輸入「台東」、「日本」等，會直接過濾資料
    current_trip = st.text_input("輸入當前旅程名稱", value="預設旅程")
    
    st.info(f"📍 目前正在查看/記錄：**{current_trip}**")
    st.divider()

    st.subheader("👥 成員設定")
    if 'members' not in st.session_state:
        st.session_state.members = ["weiche", "Michael", "Ivy", "Wendy", "Ben", "Xuan", "Kaiwen", "Daniel"]
    
    member_str = st.text_input("編輯成員 (用逗號隔開)", value=", ".join(st.session_state.members))
    if st.button("更新成員名單"):
        st.session_state.members = [m.strip() for m in member_str.split(",") if m.strip()]
        st.rerun()

members = st.session_state.members

# 3. 資料讀取與過濾
def load_and_filter_data(trip_label):
    try:
        # 永遠讀取同一個 Worksheet "Log"
        data = conn.read(worksheet="Log", ttl=0)
        data = data.dropna(how='all')
        
        # 如果是空表，建立正確欄位
        if data.empty:
            return pd.DataFrame(columns=["日期", "旅程分類", "品名", "付款人", "總金額", "分攤明細"])
        
        data.columns = [str(c).strip() for c in data.columns]
        
        # 核心：根據旅程名稱過濾
        if "旅程分類" in data.columns:
            filtered_data = data[data["旅程分類"] == trip_label].copy()
            return filtered_data
        else:
            # 如果雲端還沒有這一欄，就回傳空表
            return pd.DataFrame(columns=["日期", "旅程分類", "品名", "付款人", "總金額", "分攤明細"])
    except Exception:
        return pd.DataFrame(columns=["日期", "旅程分類", "品名", "付款人", "總金額", "分攤明細"])

# 取得目前旅程的資料
df = load_and_filter_data(current_trip)

# 4. 新增支出功能 (含功能 2 & 3：輸入驗證)
st.subheader(f"➕ 新增支出 - 【{current_trip}】")

with st.form("expense_form", clear_on_submit=True):
    col_item, col_payer, col_amt = st.columns([2, 1, 1])
    with col_item:
        item_name = st.text_input("品名", placeholder="例如：晚餐...")
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
        # 功能 2：驗證品名與金額是否填寫
        if not item_name.strip():
            st.error("❌ 請輸入品名！")
            st.stop()
        if total_amount <= 0:
            st.error("❌ 支出總金額必須大於 0！")
            st.stop()

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
            if remaining_amt < -0.01: # 功能 3 的一部分：手動輸入已超過總額
                st.error(f"❌ 指定金額總和 (${total_manual}) 已超過支出總額 (${total_amount})！")
                st.stop()
            avg = remaining_amt / len(split_members)
            for m in split_members: final_shares[m] += round(avg, 2)
        
        # 功能 3：驗證分帳總額是否等於總金額
        sum_shares = sum(final_shares.values())
        if abs(sum_shares - total_amount) > 0.1:
            st.error(f"❌ 分攤金額總計 (${sum_shares:.2f}) 與支出總額 (${total_amount:.2f}) 不符，請檢查分攤設定！")
            st.stop()

        # 讀取「全部」資料準備合併 (不分旅程)
        full_df = conn.read(worksheet="Log", ttl=0).dropna(how='all')
        
        new_row = pd.DataFrame([{
            "日期": datetime.date.today().strftime("%Y-%m-%d"),
            "旅程分類": current_trip,
            "品名": item_name,
            "付款人": payer,
            "總金額": total_amount,
            "分攤明細": str(final_shares)
        }])
        
        updated_df = pd.concat([full_df, new_row], ignore_index=True)
        conn.update(worksheet="Log", data=updated_df)
        st.success(f"🎉 已加入旅程：{current_trip}")
        st.rerun()

# 5. 📜 支出明細與結算 (含功能 1：刪除支出內容)
st.divider()
if not df.empty:
    st.subheader(f"📜 {current_trip} - 支出清單")
    view_df = df.copy()
    def format_detail(s):
        try:
            d = ast.literal_eval(s)
            return ", ".join([f"{k}: ${v}" for k, v in d.items() if v > 0])
        except: return s
    view_df["幫誰付 (分攤明細)"] = view_df["分攤明細"].apply(format_detail)
    st.dataframe(view_df[["日期", "品名", "付款人", "總金額", "幫誰付 (分攤明細)"]], use_container_width=True, hide_index=True)

    # --- 功能 1：刪除支出功能 ---
    with st.expander("🗑️ 刪除支出紀錄"):
        full_data_for_del = conn.read(worksheet="Log", ttl=0).dropna(how='all')
        # 僅列出目前旅程的選項供選擇
        trip_options = full_data_for_del[full_data_for_del["旅程分類"] == current_trip]
        
        if not trip_options.empty:
            del_list = [f"{idx} | {row['日期']} | {row['品名']} (${row['總金額']})" for idx, row in trip_options.iterrows()]
            target_del = st.selectbox("選擇要刪除的項目：", options=del_list)
            
            if st.button("🔴 確認刪除此筆紀錄", type="primary"):
                target_idx = int(target_del.split(" | ")[0])
                # 從原始總表中刪除該索引
                final_df = full_data_for_del.drop(target_idx).reset_index(drop=True)
                conn.update(worksheet="Log", data=final_df)
                st.success("✅ 紀錄已成功刪除！")
                st.rerun()
        else:
            st.write("此旅程尚無紀錄可刪除。")
    # ---------------------------

    # 結算數據處理 (只針對過濾後的 df)
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
    st.subheader(f"📊 {current_trip} - 結算報告")
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
    st.info(f"旅程「{current_trip}」目前尚無資料，快去新增第一筆吧！")

