import streamlit as st
import pandas as pd
import csv
from io import BytesIO

# 設定網頁標題與圖示
st.set_page_config(page_title="進階揪團記帳系統", page_icon="💰")

# 初始化 Session State (確保重新整理時資料不會消失)
if 'members' not in st.session_state:
    st.session_state.members = []
if 'history' not in st.session_state:
    st.session_state.history = []
if 'balances' not in st.session_state:
    st.session_state.balances = {}
if 'total_paid' not in st.session_state:
    st.session_state.total_paid = {}
if 'total_spent' not in st.session_state:
    st.session_state.total_spent = {}

# --- 側邊欄：成員設定 ---
st.sidebar.header("👥 成員設定")
member_input = st.sidebar.text_input("輸入成員名稱 (逗號隔開)", "weiche, Michael, Ivy, Wendy, Ben, Xuan, Kaiwen, Daniel")

if st.sidebar.button("初始化/重設系統"):
    names = member_input.replace("，", ",").split(",")
    st.session_state.members = [n.strip() for n in names if n.strip()]
    st.session_state.balances = {m: 0.0 for m in st.session_state.members}
    st.session_state.total_paid = {m: 0.0 for m in st.session_state.members}
    st.session_state.total_spent = {m: 0.0 for m in st.session_state.members}
    st.session_state.history = []
    st.sidebar.success("系統已就緒！")

# --- 主畫面 ---
st.title("💰 進階揪團記帳結算系統")

if not st.session_state.members:
    st.info("請在左側選單輸入成員名稱並點擊『開始記帳』")
else:
    # 1. 新增支出區塊
    with st.expander("➕ 新增一筆支出"):
        with st.form("expense_form"):
            payer = st.selectbox("誰付的錢？", st.session_state.members)
            total_amt = st.number_input("支出總金額", min_value=0.0, step=1.0)
            
            st.write("每人分攤金額 (留空則代表平分):")
            manual_shares = {}
            cols = st.columns(2)
            for idx, m in enumerate(st.session_state.members):
                with cols[idx % 2]:
                    val = st.text_input(f"{m} 的分攤", key=f"share_{m}")
                    manual_shares[m] = val

            submitted = st.form_submit_button("提交紀錄")
            
            if submitted:
                # 處理分攤邏輯
                processed_shares = {}
                filled_shares = {m: float(v) for m, v in manual_shares.items() if v.strip()}
                
                if not filled_shares:
                    share_each = total_amt / len(st.session_state.members)
                    processed_shares = {m: share_each for m in st.session_state.members}
                else:
                    processed_shares = filled_shares
                
                # 更新數據
                st.session_state.total_paid[payer] += total_amt
                st.session_state.balances[payer] -= total_amt
                for m, s in processed_shares.items():
                    st.session_state.total_spent[m] += s
                    st.session_state.balances[m] += s
                
                st.session_state.history.append({"payer": payer, "total": total_amt, "shares": processed_shares})
                st.success("紀錄成功！")

    # 2. 數據呈現
    st.subheader("📊 目前收支狀態")
    status_data = []
    for m in st.session_state.members:
        bal = st.session_state.balances[m]
        status = f"欠 ${bal:.2f}" if bal > 0.01 else f"應收 ${abs(bal):.2f}" if bal < -0.01 else "已清平"
        status_data.append({
            "成員": m,
            "個人總花費": f"${st.session_state.total_spent[m]:.2f}",
            "目前狀態": status
        })
    st.table(pd.DataFrame(status_data))

    # 3. 結算建議
    if st.button("🏁 生成最終結算方案"):
        st.subheader("💡 轉帳建議")
        debtors = sorted([[n, b] for n, b in st.session_state.balances.items() if b > 0.01], key=lambda x: x[1], reverse=True)
        creditors = sorted([[n, abs(b)] for n, b in st.session_state.balances.items() if b < -0.01], key=lambda x: x[1], reverse=True)

        i, j = 0, 0
        if not debtors:
            st.write("所有帳目已平！")
        else:
            while i < len(debtors) and j < len(creditors):
                amt = min(debtors[i][1], creditors[j][1])
                st.info(f"💸 **{debtors[i][0]}** ➜ **{creditors[j][0]}** : `${amt:.2f}`")
                debtors[i][1] -= amt
                creditors[j][1] -= amt
                if debtors[i][1] < 0.01: i += 1
                if creditors[j][1] < 0.01: j += 1

    # 4. 匯出 CSV
    if st.session_state.history:
        output = BytesIO()
        writer = csv.writer(output)
        writer.writerow(["成員個人統計"])
        writer.writerow(["姓名", "總共代墊金額", "個人消費總額", "最終差額"])
        for m in st.session_state.members:
            writer.writerow([m, st.session_state.total_paid[m], st.session_state.total_spent[m], st.session_state.balances[m]])
        
        st.download_button(
            label="📥 下載結算報表 (CSV)",
            data=output.getvalue(),
            file_name="expense_report.csv",
            mime="text/csv"
        )