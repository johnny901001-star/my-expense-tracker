import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import ast

# 1. 網頁基本設定
st.set_page_config(page_title="雲端進階記帳結算系統 V2", layout="wide")
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
    except Exception as e:
        return pd.DataFrame(columns=["日期", "品名", "付款人", "總金額", "分攤明細"])

df = load_full_data()

# 3. 初始化成員清單與計算機狀態
if 'members' not in st.session_state:
    st.session_state.members = ["weiche", "Michael", "Ivy", "Wendy", "Ben", "Xuan", "Kaiwen", "Daniel"]

if 'calc_display' not in st.session_state:
    st.session_state.calc_display = ""

members = st.session_state.members

# 側邊欄：成員設定
with st.sidebar:
    st.subheader("👥 成員設定")
    member_str = st.text_input("輸入成員名稱", value=", ".join(st.session_state.members))
    if st.button("更新成員"):
        st.session_state.members = [m.strip() for m in member_str.split(",") if m.strip()]
        st.rerun()

# 4. 新增支出功能
st.subheader("➕ 新增支出")
with st.form("expense_form", clear_on_submit=True):
    col_item, col_payer, col_amt = st.columns([2, 1, 1])
    with col_item:
        item_name = st.text_input("品名 (例：晚餐、機票)", placeholder="請輸入品名...")
    with col_payer:
        payer = st.selectbox("誰付的錢？", members)
    with col_amt:
        total_amount = st.number_input("支出總金額", min_value=0.0, step=1.0)
    
    st.write("每人分攤金額 (留空代表平分):")
    shares_input = {}
    cols = st.columns(4)
    for i, m in enumerate(members):
        shares_input[m] = cols[i % 4].text_input(f"{m}", key=f"input_{m}")
    
    submit_button = st.form_submit_button("✅ 提交紀錄至雲端")
    
    if submit_button:
        if not item_name:
            st.error("請輸入品名！")
        else:
            final_shares = {}
            manual_entries = {m: float(val) for m, val in shares_input.items() if val.strip()}
            if not manual_entries:
                avg = total_amount / len(members)
                final_shares = {m: round(avg, 2) for m in members}
            else:
                final_shares = {m: manual_entries.get(m, 0.0) for m in members}

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
            st.success(f"🎉 【{item_name}】已成功存入！")
            st.rerun()

# 5. 支出明細與刪除功能
st.divider()
st.subheader("📜 歷史支出清單")

if not df.empty:
    # 建立顯示用的 DataFrame (不顯示複雜的字典)
    display_df = df.copy()
    # 增加一個「操作」欄位（雖然 Streamlit Table 不能直接放按鈕，我們用選單刪除）
    st.dataframe(display_df[["日期", "品名", "付款人", "總金額"]], use_container_width=True)
    
    with st.expander("🗑️ 刪除錯誤紀錄"):
        # 建立選項標籤：索引 - 日期 - 品名 - 金額
        delete_options = [f"{i}: {row['日期']} | {row['品名']} (${row['總金額']})" for i, row in df.iterrows()]
        target = st.selectbox("選擇要刪除的項目：", options=delete_options)
        if st.button("確認永久刪除", type="primary"):
            target_idx = int(target.split(":")[0])
            updated_df = df.drop(target_idx).reset_index(drop=True)
            conn.update(worksheet="Log", data=updated_df)
            st.warning("項目已刪除！")
            st.rerun()
else:
    st.info("目前尚無支出紀錄。")

# 6. 結算統計報告
st.divider()
st.subheader("📊 結算報告")

if not df.empty:
    paid_summary = {m: 0.0 for m in members}
    spent_summary = {m: 0.0 for m in members}

    for _, row in df.iterrows():
        p = str(row.get("付款人", "")).strip()
        amt = row.get("總金額", 0)
        if p in paid_summary:
            paid_summary[p] += float(amt)
        try:
            detail = ast.literal_eval(str(row.get("分攤明細", "{}")))
            for m, s in detail.items():
                if m.strip() in spent_summary:
                    spent_summary[m.strip()] += float(s)
        except:
            continue

    status_list = []
    for m in members:
        net = spent_summary[m] - paid_summary[m]
        status_list.append({
            "成員": m,
            "幫大家付(代墊)": f"${paid_summary[m]:.2f}",
            "個人應付(消費)": f"${spent_summary[m]:.2f}",
            "結餘狀態": f"🔴 欠 ${net:.2f}" if net > 0.1 else (f"🟢 應收 ${abs(net):.2f}" if net < -0.1 else "⚪ 已清平"),
            "net": net
        })
    st.table(pd.DataFrame(status_list).drop(columns=["net"]))

    if st.button("🔍 計算最優還款路徑"):
        debtors = sorted([[m, spent_summary[m] - paid_summary[m]] for m in members if (spent_summary[m] - paid_summary[m]) > 0.1], key=lambda x: x[1], reverse=True)
        creditors = sorted([[m, abs(spent_summary[m] - paid_summary[m])] for m in members if (spent_summary[m] - paid_summary[m]) < -0.1], key=lambda x: x[1], reverse=True)
        
        i, j = 0, 0
        while i < len(debtors) and j < len(creditors):
            transfer = min(debtors[i][1], creditors[j][1])
            st.success(f"💸 **{debtors[i][0]}** ➜ 給 **{creditors[j][0]}**： **${transfer:.2f}**")
            debtors[i][1] -= transfer
            creditors[j][1] -= transfer
            if debtors[i][1] < 0.1: i += 1
            if creditors[j][1] < 0.1: j += 1

# 7. 按鍵式小計算機 (位於最底部)
st.divider()
st.subheader("🧮 按鍵式計算機")

# 計算機邏輯處理
def click_button(label):
    if label == "C":
        st.session_state.calc_display = ""
    elif label == "=":
        try:
            # 安全地計算結果
            st.session_state.calc_display = str(round(eval(st.session_state.calc_display, {"__builtins__": None}, {}), 2))
        except:
            st.session_state.calc_display = "Error"
    else:
        # 避免連續輸入兩個算符或 Error 後繼續輸入
        if st.session_state.calc_display == "Error":
            st.session_state.calc_display = ""
        st.session_state.calc_display += str(label)

# 顯示計算機畫面
st.code(st.session_state.calc_display if st.session_state.calc_display else "0", language="text")

# 按鈕排列
calc_layout = [
    ["7", "8", "9", "/"],
    ["4", "5", "6", "*"],
    ["1", "2", "3", "-"],
    ["0", ".", "C", "+"],
    ["="]
]

for row in calc_layout:
    cols = st.columns(len(row))
    for i, btn_label in enumerate(row):
        if cols[i].button(btn_label, key=f"btn_{btn_label}", use_container_width=True):
            click_button(btn_label)
            st.rerun()

