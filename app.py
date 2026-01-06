import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import ast

# 1. 網頁基本設定
st.set_page_config(page_title="雲端進階記帳系統 V5", layout="wide")

# --- 進階 CSS 優化：強制排版緊湊、手機版維持一左一右 ---
st.markdown("""
    <style>
    /* 縮減所有元件的上下間距 */
    .block-container { padding-top: 1rem !important; padding-bottom: 0rem !important; }
    .stForm { padding: 10px !important; }
    
    /* 強制讓小螢幕的 Column 不要斷行（維持一左一右） */
    [data-testid="column"] {
        min-width: 120px !important; 
        flex: 1 1 45% !important;
    }
    
    /* 縮減 Checkbox 與 Input 的間隙 */
    .stCheckbox { margin-bottom: -15px !important; }
    hr { margin: 0.5rem 0 !important; }
    
    /* 讓表單內的文字更緊湊 */
    p, label { margin-bottom: 2px !important; font-size: 14px !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("💰 雲端進階記帳結算系統")

# 2. 連接 Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

def load_full_data():
    st.cache_data.clear()
    try:
        data = conn.read(worksheet="Log", ttl=0)
        data = data.dropna(how='all')
        data.columns = [str(c).strip() for c in data.columns]
        return data
    except Exception:
        return pd.DataFrame(columns=["日期", "品名", "付款人", "總金額", "分攤明細"])

df = load_full_data()

# 3. 初始化成員清單
if 'members' not in st.session_state:
    st.session_state.members = ["weiche", "Michael", "Ivy", "Wendy", "Ben", "Xuan", "Kaiwen", "Daniel"]

members = st.session_state.members

with st.sidebar:
    st.subheader("👥 成員設定")
    member_str = st.text_input("輸入成員名稱", value=", ".join(st.session_state.members))
    if st.button("更新成員"):
        st.session_state.members = [m.strip() for m in member_str.split(",") if m.strip()]
        st.rerun()

# 4. 新增支出功能 (使用 clear_on_submit 確保提交後清空)
st.subheader("➕ 新增支出")
with st.form("expense_form", clear_on_submit=True):
    col_item, col_payer, col_amt = st.columns([1.5, 1, 1])
    with col_item:
        item_name = st.text_input("品名", placeholder="品名")
    with col_payer:
        payer = st.selectbox("誰付的", members)
    with col_amt:
        total_amount = st.number_input("總金額", min_value=0.0, step=1.0, format="%.1f")
    
    st.write("📝 **分攤設定** (勾選=平分 / 填數字=指定)")
    
    # 建立分攤輸入區 (左右並排，且手機版不輕易斷行)
    check_states = {}
    manual_values = {}
    
    # 每兩個成員一組 row
    for i in range(0, len(members), 2):
        row_members = members[i:i+2]
        cols = st.columns(2)
        for idx, m in enumerate(row_members):
            with cols[idx]:
                # 內部再分兩欄，左邊勾選，右邊輸入金額
                c1, c2 = st.columns([1, 2.5])
                with c1:
                    check_states[m] = st.checkbox("平分", key=f"check_{m}")
                with c2:
                    manual_values[m] = st.text_input(f"{m}", key=f"val_{m}", placeholder="指定$", label_visibility="collapsed")
        st.markdown("---")

    submit_button = st.form_submit_button("✅ 提交紀錄並清空", use_container_width=True)
    
    if submit_button:
        final_shares = {m: 0.0 for m in members}
        total_manual = 0.0
        manual_members = []
        split_members = [m for m, checked in check_states.items() if checked]
        
        # 1. 處理手動輸入金額
        for m, val in manual_values.items():
            if val.strip():
                try:
                    amt = float(val)
                    final_shares[m] = amt
                    total_manual += amt
                    manual_members.append(m)
                except ValueError:
                    st.error(f"❌ {m} 金額錯誤")
                    st.stop()

        # 2. 處理平分剩餘金額
        remaining_amt = total_amount - total_manual
        if not split_members and not manual_members:
            # 都沒勾也沒填 -> 全員平分
            avg = total_amount / len(members)
            final_shares = {m: round(avg, 1) for m in members}
        elif split_members:
            if remaining_amt < -0.05:
                st.error(f"❌ 分攤總額已超過總金額！")
                st.stop()
            avg = max(0, remaining_amt / len(split_members))
            for m in split_members:
                final_shares[m] += round(avg, 1)
        
        # 3. 最終校驗與寫入
        if not item_name:
            st.error("❌ 請輸入品名")
        elif abs(sum(final_shares.values()) - total_amount) > 1.0:
            st.error(f"❌ 分攤總和與總金額不符")
        else:
            fresh_df = load_full_data()
            new_row = pd.DataFrame([{
                "日期": datetime.date.today().strftime("%Y-%m-%d"),
                "品名": item_name,
                "付款人": payer,
                "總金額": total_amount,
                "分攤明細": str(final_shares)
            }])
            updated_df = pd.concat([fresh_df, new_row], ignore_index=True)
            conn.update(worksheet="Log", data=updated_df)
            st.toast(f"🎉 儲存成功！")
            st.rerun() # 強制刷新頁面，確保 clear_on_submit 徹底生效

# 5. 📜 歷史明細與詳細分攤
st.subheader("📜 支出詳細清單")
if not df.empty:
    def format_detail(detail_str):
        try:
            d = ast.literal_eval(detail_str)
            # 格式： 人名($錢)
            return ", ".join([f"{k}(${v})" for k, v in d.items() if v > 0])
        except:
            return detail_str

    view_df = df.copy()
    view_df["幫誰付 (分攤明細)"] = view_df["分攤明細"].apply(format_detail)
    
    st.dataframe(
        view_df[["日期", "品名", "付款人", "總金額", "幫誰付 (分攤明細)"]], 
        use_container_width=True, 
        hide_index=True
    )

    with st.expander("🗑️ 刪除紀錄"):
        del_opt = [f"{i} | {row['品名']} (${row['總金額']})" for i, row in df.iterrows()]
        target = st.selectbox("選擇要刪除的項目", options=del_opt)
        if st.button("確認刪除", type="primary"):
            idx = int(target.split(" | ")[0])
            updated_df = df.drop(idx).reset_index(drop=True)
            conn.update(worksheet="Log", data=updated_df)
            st.rerun()

# 6. 📊 結算報告
st.divider()
st.subheader("📊 結算報告")
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
            "成員": m, 
            "代墊": f"${paid[m]:.0f}", 
            "消費": f"${spent[m]:.0f}", 
            "狀態": f"🔴 欠{net:.0f}" if net > 0.1 else (f"🟢 收{abs(net):.0f}" if net < -0.1 else "⚪ 清"),
            "net": net
        })
    st.table(pd.DataFrame(status_data).drop(columns=["net"]))

    if st.button("🔍 計算最優還款路徑"):
        debtors = sorted([[m, spent[m] - paid[m]] for m in members if (spent[m] - paid[m]) > 0.1], key=lambda x: x[1], reverse=True)
        creditors = sorted([[m, abs(spent[m] - paid[m])] for m in members if (spent[m] - paid[m]) < -0.1], key=lambda x: x[1], reverse=True)
        i, j = 0, 0
        while i < len(debtors) and j < len(creditors):
            transfer = min(debtors[i][1], creditors[j][1])
            st.success(f"💸 **{debtors[i][0]}** ➔ 給 **{creditors[j][0]}**： **${transfer:.0f}**")
            debtors[i][1] -= transfer; creditors[j][1] -= transfer
            if debtors[i][1] < 0.1: i += 1
            if creditors[j][1] < 0.1: j += 1
