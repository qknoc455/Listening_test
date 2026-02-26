import streamlit as st
import os
import random
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# 頁面基本設定
st.set_page_config(page_title="語音品質聽測系統", layout="centered")

# --- 1. 連接 Google Sheets ---
def get_sheet():
    creds_dict = dict(st.secrets["gcp_service_account"])
    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(
        "https://docs.google.com/spreadsheets/d/13Xh-_L9bu6b75KQSiGn6uzK2X9_rUk6mmFIvmZiqN6Q/edit"
    ).sheet1
    return sheet

def read_sheet():
    sheet = get_sheet()
    data = sheet.get_all_records()
    return pd.DataFrame(data) if data else pd.DataFrame(
        columns=["Timestamp", "User_ID", "Test_Group", "File", "Choice", "Winner"]
    )

def get_used_user_ids():
    """從 Google Sheets 取得已使用的 user 編號"""
    try:
        df = read_sheet()
        if df.empty or "User_ID" not in df.columns:
            return set()
        ids = df["User_ID"].unique()
        # 取出數字部分，e.g. "user3" -> 3
        nums = set()
        for uid in ids:
            try:
                nums.add(int(str(uid).replace("user", "")))
            except:
                pass
        return nums
    except:
        return set()

def append_row(row_dict):
    sheet = get_sheet()
    if sheet.row_count == 0 or sheet.cell(1, 1).value == "":
        sheet.append_row(["Timestamp", "User_ID", "Test_Group", "File", "Choice", "Winner"])
    sheet.append_row([
        row_dict["Timestamp"],
        row_dict["User_ID"],
        row_dict["Test_Group"],
        row_dict["File"],
        row_dict["Choice"],
        row_dict["Winner"]
    ])

def delete_last_row_for_user(user_id, test_group):
    """刪除該使用者在該組別的最後一筆記錄（用於回上一題）"""
    sheet = get_sheet()
    all_values = sheet.get_all_values()
    # 從最後一列往上找
    for i in range(len(all_values) - 1, 0, -1):
        row = all_values[i]
        if len(row) >= 3 and row[1] == user_id and row[2] == test_group:
            sheet.delete_rows(i + 1)  # gspread 是 1-indexed
            return True
    return False

# --- 2. 功能函式：自動配對檔案 ---
def load_files(test_type):
    base_path = f"data/{test_type}"
    if not os.path.exists(base_path):
        st.error(f"路徑不存在: {base_path} (請檢查 GitHub 檔案結構)")
        return []

    subfolders = sorted([
        f for f in os.listdir(base_path)
        if os.path.isdir(os.path.join(base_path, f)) and not f.startswith('.')
    ])

    if len(subfolders) < 2:
        st.error(f"資料夾數量不足，偵測到: {subfolders}")
        return []

    folder1, folder2 = subfolders[0], subfolders[1]
    path1 = os.path.join(base_path, folder1)
    path2 = os.path.join(base_path, folder2)

    files = sorted([f for f in os.listdir(path1) if f.lower().endswith(('.wav', '.mp3'))])

    paired_data = []
    for f in files:
        base = os.path.splitext(f)[0]
        ext  = os.path.splitext(f)[1]
        candidate1 = os.path.join(path2, f)
        candidate2 = os.path.join(path2, f"{base}_mix{ext}")
        if os.path.exists(candidate1):
            target_file = candidate1
        elif os.path.exists(candidate2):
            target_file = candidate2
        else:
            continue

        paired_data.append({
            "file_name": f,
            "path_1": os.path.join(path1, f), "label_1": folder1,
            "path_2": target_file,             "label_2": folder2
        })
    return paired_data

# --- 3. 初始化 Session State ---
if 'user_id'     not in st.session_state: st.session_state.user_id     = ""
if 'current_idx' not in st.session_state: st.session_state.current_idx = 0
if 'test_data'   not in st.session_state: st.session_state.test_data   = []
if 'shuffled'    not in st.session_state: st.session_state.shuffled    = False

# --- 4. 側邊欄：管理員後台 ---
with st.sidebar:
    st.title("⚙️ 管理員後台")
    if st.checkbox("開啟數據統計"):
        pw = st.text_input("輸入密碼", type="password")
        if pw == "1234":
            try:
                existing_data = read_sheet()
                if not existing_data.empty:
                    st.success(f"目前累計受測人數: {existing_data['User_ID'].nunique()}")
                    st.subheader("勝率分佈 (Winner Count)")
                    st.bar_chart(existing_data['Winner'].value_counts())
                    st.dataframe(existing_data)
                else:
                    st.info("目前雲端表格內沒有任何資料。")
            except Exception as e:
                st.error(f"讀取失敗: {e}")

# --- 5. 主介面流程 ---
st.title("🎧 語音品質主觀聽測 (AB Test)")

# 步驟 A: 身分確認
if not st.session_state.user_id:
    st.info("請輸入您的受測者編號以開始測試。")
    user_num = st.number_input("受測者編號 (例如輸入 1 會記錄為 user1)", min_value=1, max_value=100, step=1)

    if st.button("確認並進入測試"):
        used_ids = get_used_user_ids()
        if int(user_num) in used_ids:
            st.error(f"編號 {int(user_num)} 已被使用，請選擇其他編號。")
        else:
            st.session_state.user_id = f"user{int(user_num)}"
            st.rerun()

# 步驟 B: 進行測試
else:
    st.write(f"當前測試者: **{st.session_state.user_id}**")

    test_options = ["baseline_LLM", "DNSMIOS_LLM", "Noisy_LLM"]
    selected_test = st.selectbox(
        "請選擇目前的測試組別：", test_options,
        on_change=lambda: st.session_state.update(current_idx=0, shuffled=False)
    )

    if not st.session_state.shuffled:
        st.session_state.test_data = load_files(selected_test)
        random.shuffle(st.session_state.test_data)
        st.session_state.shuffled = True

    data = st.session_state.test_data

    if data and st.session_state.current_idx < len(data):
        trial = data[st.session_state.current_idx]
        st.subheader(f"進度：{st.session_state.current_idx + 1} / {len(data)}")

        random.seed(f"{st.session_state.user_id}_{selected_test}_{st.session_state.current_idx}")
        swapped = random.choice([True, False])

        a_path = trial['path_2'] if swapped else trial['path_1']
        a_lab  = trial['label_2'] if swapped else trial['label_1']
        b_path = trial['path_1'] if swapped else trial['path_2']
        b_lab  = trial['label_1'] if swapped else trial['label_2']

        col1, col2 = st.columns(2)
        with col1:
            st.write("**樣本 A**")
            st.audio(a_path)
        with col2:
            st.write("**樣本 B**")
            st.audio(b_path)

        st.markdown("---")
        st.write("💡 **哪一個聲音品質較好？**")
        c1, c2, c3 = st.columns(3)

        def save_and_next(choice_label, winner_name):
            new_row = {
                "Timestamp":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "User_ID":    st.session_state.user_id,
                "Test_Group": selected_test,
                "File":       trial['file_name'],
                "Choice":     choice_label,
                "Winner":     winner_name
            }
            try:
                append_row(new_row)
            except Exception as e:
                st.error(f"寫入失敗: {e}")
            st.session_state.current_idx += 1
            st.rerun()

        if c1.button("⬅️ A 較好", use_container_width=True):
            save_and_next("A", a_lab)
        if c2.button("無明顯差異", use_container_width=True):
            save_and_next("Tie", "None")
        if c3.button("B 較好 ➡️", use_container_width=True):
            save_and_next("B", b_lab)

        # 回上一題按鈕
        st.markdown("---")
        if st.session_state.current_idx > 0:
            if st.button("↩️ 回上一題"):
                try:
                    delete_last_row_for_user(st.session_state.user_id, selected_test)
                except Exception as e:
                    st.error(f"刪除記錄失敗: {e}")
                st.session_state.current_idx -= 1
                st.rerun()

    elif len(data) > 0:
        st.balloons()
        st.success("本組測試已完成！您的選擇已自動存入雲端表格。")
        if st.button("切換組別或重新開始"):
            st.session_state.current_idx = 0
            st.session_state.shuffled    = False
            st.rerun()
