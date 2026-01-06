import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import ast

# 1. 網頁基本設定
st.set_page_config(page_title="雲端進階記帳系統 V3", layout="wide")

# 自定義 CSS：優化按鈕樣式與計算機大小
st.markdown("""
    <style>
    .stButton>button { height: 3em; font-size: 1.1rem !important; font-weight: bold; }
    .share-box { border: 1px solid #ddd; padding: 10px; border-radius: 5px; background-color: #f9f9f9; }
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

# 3. 初始化狀態
if 'members' not in st.session_state:
    st.session_state.members = ["weiche", "Michael", "Ivy", "Wendy", "Ben", "Xuan", "Kaiwen", "Daniel"]
if 'calc_display' not in st.session_state:
    st.session_state.calc_display = ""

members = st.session_state.members

with st.sidebar:
    st.subheader("👥 成員設定")
    member_str = st.text_input("輸入成員名稱", value=", ".join(st.session_state.members))
    if st.button("更新成員"):
        st.session_state.members = [m.strip() for m in member_str.split(",") if m.strip()]
        st.rerun()

# 4. 新增支出功能 (含複雜分攤邏輯)
st.subheader("➕ 新增支出")
with st.form("expense_form"):
    col_item, col_payer, col_amt = st.columns([2, 1, 1])
    with col_item:
        item_name = st.text_input("品名", placeholder="例如：晚餐、計程車...")
    with col_payer:
        payer = st.selectbox("誰付的錢？", members)
    with col_amt:
        total_amount = st.number_input("支出總金額", min_value=0.0, step=1.0, format="%.2f")
    
    st.write("📝 **分攤設定** (勾選=參與平分 / 填寫數字=指定金額)")
    
    # 建立分攤輸入區
    check_states = {}
    manual_values = {}
    cols = st.columns(4)
    for i, m in enumerate(members):
        with cols[i % 4]:
            st.markdown(f"**{m}**")
            check_states[m] = st.checkbox("平分", key=f"check_{m}")
            manual_values[m] = st.text_input("指定金額", key=f"val_{m}", placeholder="0.0")

    submit_button = st.form_submit_button("✅ 提交紀錄至雲端", use_container_width=True)
    
    if submit_button:
        # --- 核心邏輯計算開始 ---
        final_shares = {m: 0.0 for m in members}
        total_manual = 0.0
        manual_members = []
        split_members = [m for m, checked in check_states.items() if checked]
        
        # 1. 處理手動輸入的部分
        for m, val in manual_values.items():
            if val.strip():
                try:
                    amt = float(val)
                    final_shares[m] = amt
                    total_manual += amt
                    manual_members.append(m)
                except ValueError:
                    st.error(f"❌ {m} 的金額輸入格式錯誤")
                    st.stop()

        # 2. 處理平分部分
        remaining_amt = total_amount - total_manual
        
        if not split_members and not manual_members:
            # 情況 A: 沒勾也沒填 -> 全員平分
            avg = total_amount / len(members)
            final_shares = {m: round(avg, 2) for m in members}
        elif split_members:
            # 情況 B: 有勾選 -> 剩下的錢給勾選的人平分
            if remaining_amt < -0.01: # 容許微小浮點數誤差
                st.error(f"❌ 指定金額總和 (${total_manual}) 已超過總金額 (${total_amount})！")
                st.stop()
            avg = remaining_amt / len(split_members)
            for m in split_members:
                final_shares[m] += round(avg, 2)
        
        # 3. 最終驗證：總和必須等於代墊金額
        sum_shares = sum(final_shares.values())
        if abs(sum_shares - total_amount) > 0.5: # 允許 0.5 塊以內的進位誤差
            st.error(f"❌ 分攤不均！目前分攤總計 ${sum_shares:.2f}，與總金額 ${total_amount:.2f} 不符。")
            st.info("提示：若要平分剩餘金額，請記得勾選成員名字前的『平分』方框。")
        elif not item_name:
            st.error("❌ 請輸入品名！")
        else:
            # 寫入雲端
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
            st.success(f"🎉 【{item_name}】儲存成功！")
            st.rerun()

# 5. 📜 歷史明細與刪除
st.divider()
st.subheader("📜 支出詳細清單")
if not df.empty:
    st.dataframe(df[["日期", "品名", "付款人", "總金額"]], use_container_width=True, hide_index=True)
    with st.expander("🗑️ 刪除紀錄"):
        del_opt = [f"{i} | {row['日期']} | {row['品名']} (${row['總金額']})" for i, row in df.iterrows()]
        target = st.selectbox("選擇要刪除的項目：", options=del_opt)
        if st.button("確認刪除", type="primary"):
            idx = int(target.split(" | ")[0])
            updated_df = df.drop(idx).reset_index(drop=True)
            conn.update(worksheet="Log", data=updated_df)
            st.rerun()

# 6. 📊 結算報告 (同前版)
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
        status_data.append({"成員": m, "代墊": f"${paid[m]:.1f}", "應付": f"${spent[m]:.1f}", 
                            "狀態": f"🔴 欠 ${net:.1f}" if net > 0.1 else (f"🟢 應收 ${abs(net):.1f}" if net < -0.1 else "⚪ 清"), "net": net})
    st.table(pd.DataFrame(status_data).drop(columns=["net"]))

# 7. 🧮 按鍵式計算機 (瘦身置中版)
st.divider()
st.markdown("<h3 style='text-align: center;'>🧮 快速計算機</h3>", unsafe_allow_html=True)
_, calc_col, _ = st.columns([1, 1.2, 1]) # 手機版會自動調整比例
with calc_col:
    st.code(st.session_state.calc_display if st.session_state.calc_display else "0", language="text")
    def click_calc(label):
        if label == "C": st.session_state.calc_display = ""
        elif label == "=":
            try:
                expr = st.session_state.calc_display.replace('x', '*').replace('÷', '/')
                st.session_state.calc_display = str(round(eval(expr, {"__builtins__": None}, {}), 2))
            except: st.session_state.calc_display = "Error"
        else:
            if st.session_state.calc_display == "Error": st.session_state.calc_display = ""
            st.session_state.calc_display += str(label)

    rows = [["7", "8", "9", "÷"], ["4", "5", "6", "x"], ["1", "2", "3", "-"], ["0", ".", "C", "+"], ["="]]
    for row in rows:
        btn_cols = st.columns(len(row))
        for i, b in enumerate(row):
            if btn_cols[i].button(b, key=f"calc_{b}_{i}", use_container_width=True, type="primary" if b=="=" else "secondary"):
                click_calc(b); st.rerun()

