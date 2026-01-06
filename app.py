import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import ast

# 1. 網頁基本設定
st.set_page_config(page_title="雲端進階記帳系統", layout="wide")

# --- 自定義 CSS：讓計算機變小且美觀 ---
st.markdown("""
    <style>
    .stButton>button {
        height: 3em;
        font-size: 1.2rem !important;
        font-weight: bold;
    }
    .calc-container {
        max-width: 300px;
        margin: auto;
    }
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

# 4. 新增支出功能 (表單部分保持不變，略)
# ... [保留原本的新增支出 form 程式碼] ...

# 5. 📜 支出明細與刪除功能 (優化版)
st.divider()
st.subheader("📜 支出詳細清單")

if not df.empty:
    # 建立一個美觀的顯示清單
    display_df = df.copy()
    
    # 這裡顯示詳細項目，讓使用者一目瞭然
    st.dataframe(
        display_df[["日期", "品名", "付款人", "總金額"]], 
        use_container_width=True,
        hide_index=True
    )

    # 刪除功能
    with st.expander("🗑️ 刪除/修正紀錄"):
        # 建立選項標籤
        delete_options = [f"{i} | {row['品名']} (${row['總金額']}) by {row['付款人']}" for i, row in df.iterrows()]
        target = st.selectbox("選擇要刪除的項目：", options=delete_options)
        if st.button("確認刪除這筆紀錄", type="primary"):
            idx = int(target.split(" | ")[0])
            updated_df = df.drop(idx).reset_index(drop=True)
            conn.update(worksheet="Log", data=updated_df)
            st.toast("✅ 紀錄已刪除！")
            st.rerun()
else:
    st.info("💡 目前還沒有任何支出喔！")

# 6. 📊 結算統計與報表 (保持不變，略)
# ... [保留原本的結算報表與計算誰該給誰錢的程式碼] ...

# 7. 🧮 強化版按鍵式計算機
st.divider()
st.markdown("<h3 style='text-align: center;'>🧮 快速計算機</h3>", unsafe_allow_html=True)

# 讓計算機置中且變小
_, calc_center, _ = st.columns([1, 1.5, 1])

with calc_center:
    # 螢幕顯示
    st.code(st.session_state.calc_display if st.session_state.calc_display else "0", language="text")
    
    # 計算邏輯
    def click_button(label):
        if label == "C":
            st.session_state.calc_display = ""
        elif label == "=":
            try:
                # 替換特殊符號進行運算
                expr = st.session_state.calc_display.replace('x', '*').replace('÷', '/')
                st.session_state.calc_display = str(round(eval(expr, {"__builtins__": None}, {}), 2))
            except:
                st.session_state.calc_display = "Error"
        else:
            if st.session_state.calc_display == "Error":
                st.session_state.calc_display = ""
            st.session_state.calc_display += str(label)

    # 按鈕佈局 (採用標準計算機排列)
    rows = [
        ["7", "8", "9", "÷"],
        ["4", "5", "6", "x"],
        ["1", "2", "3", "-"],
        ["0", ".", "C", "+"],
        ["="]
    ]

    for row in rows:
        cols = st.columns(len(row))
        for i, btn_label in enumerate(row):
            # 為 = 號特別加強顏色
            btn_type = "primary" if btn_label == "=" else "secondary"
            if cols[i].button(btn_label, key=f"key_{btn_label}_{i}", use_container_width=True, type=btn_type):
                click_button(btn_label)
                st.rerun()


