import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime

# 1. 網頁基本設定
st.set_page_config(page_title="雲端進階記帳結算系統", layout="centered")
st.title("💰 雲端進階記帳結算系統")

# 2. 連接 Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# 讀取資料函數 (增加清除快取功能)
def get_data():
    try:
        # ttl=0 確保每次都從雲端抓最新，不讀取舊快取
        return conn.read(worksheet="Log", ttl=0)
    except:
        return pd.DataFrame(columns=["日期", "付款人", "總金額", "分攤明細"])

df = get_data()

# 3. 初始化成員清單
if 'members' not in st.session_state:
    st.session_state.members = ["weiche", "Michael", "Ivy", "Wendy", "Ben", "Xuan", "Kaiwen", "Daniel"]

with st.expander("👥 成員設定"):
    member_str = st.text_input("輸入成員名稱 (用半角逗號隔開)", value=", ".join(st.session_state.members))
    if st.button("更新成員"):
        st.session_state.members = [m.strip() for m in member_str.split(",") if m.strip()]
        st.rerun()

members = st.session_state.members

# 4. 新增支出功能
st.subheader("➕ 新增支出 (同步雲端)")
with st.form("expense_form", clear_on_submit=True):
    payer = st.selectbox("誰付的錢？", members)
    total_amount = st.number_input("支出總金額", min_value=0.0, step=10.0)
    
    st.write("每人分攤金額 (留空則代表平分):")
    shares_input = {}
    cols = st.columns(2)
    for i, m in enumerate(members):
        shares_input[m] = cols[i % 2].text_input(f"{m} 的分攤", key=f"input_{m}")
    
    submit_button = st.form_submit_button("送出紀錄並同步")
    
    if submit_button:
        # 計算分攤
        final_shares = {}
        manual_entries = {m: float(val) for m, val in shares_input.items() if val.strip()}
        
        if not manual_entries:
            avg = total_amount / len(members)
            final_shares = {m: round(avg, 2) for m in members}
        else:
            final_shares = {m: manual_entries.get(m, 0.0) for m in members}

        # 寫入雲端
        new_data = pd.DataFrame([{
            "日期": datetime.date.today().strftime("%Y-%m-%d"),
            "付款人": payer,
            "總金額": total_amount,
            "分攤明細": str(final_shares)
        }])
        
        updated_df = pd.concat([df, new_data], ignore_index=True)
        conn.update(worksheet="Log", data=updated_df)
        st.success("✅ 已寫入雲端！")
        st.rerun()

# 5. 結算報告 (統計與誰付多少)
st.divider()
st.subheader("📊 目前收支統計表")

# 核心修正：強健解析資料
if not df.empty:
    paid_summary = {m: 0.0 for m in members}
    spent_summary = {m: 0.0 for m in members}
    
    # 遍歷每一行資料進行累加
    for _, row in df.iterrows():
        # 取得付款人 (使用 get 避免欄位名稱微小差異導致報錯)
        p = row.get("付款人")
        amt = row.get("總金額", 0)
        detail_str = row.get("分攤明細", "{}")
        
        # 累加付款金額
        if p in paid_summary:
            paid_summary[p] += float(amt)
            
        # 累加個人消費金額
        try:
            # 將字串格式的字典轉回真正的字典
            detail = eval(str(detail_str))
            for m, s in detail.items():
                if m in spent_summary:
                    spent_summary[m] += float(s)
        except:
            continue

    # 建立統計表格
    status_list = []
    for m in members:
        # 淨結餘 = 自己吃掉的錢 - 自己代墊的錢
        # 正數：代表欠人錢 (應付)；負數：代表別人欠你錢 (應收)
        balance = spent_summary[m] - paid_summary[m]
        status_list.append({
            "成員": m,
            "總代墊 (付出的)": round(paid_summary[m], 2),
            "個人總花費": round(spent_summary[m], 2),
            "狀態": f"欠 ${round(balance, 2)}" if balance > 0.1 else (f"應收 ${round(abs(balance), 2)}" if balance < -0.1 else "已平帳"),
            "raw_balance": balance
        })
    
    display_df = pd.DataFrame(status_list)
    st.table(display_df.drop(columns=["raw_balance"]))

    # 6. 最簡轉帳建議 (這就是你要的「誰要付多少」)
    st.subheader("💸 最簡轉帳建議")
    if st.button("計算結算方案"):
        debtors = sorted([[d["成員"], d["raw_balance"]] for d in status_list if d["raw_balance"] > 0.1], key=lambda x: x[1], reverse=True)
        creditors = sorted([[d["成員"], abs(d["raw_balance"])] for d in status_list if d["raw_balance"] < -0.1], key=lambda x: x[1], reverse=True)
        
        if not debtors and not creditors:
            st.write("目前大家都不互相欠錢囉！")
        else:
            i, j = 0, 0
            while i < len(debtors) and j < len(creditors):
                transfer = min(debtors[i][1], creditors[j][1])
                st.info(f"👉 **{debtors[i][0]}** 應支付給 **{creditors[j][0]}**： `${round(transfer, 2)}`")
                debtors[i][1] -= transfer
                creditors[j][1] -= transfer
                if debtors[i][1] < 0.1: i += 1
                if creditors[j][1] < 0.1: j += 1
else:
    st.info("目前雲端尚無紀錄。")