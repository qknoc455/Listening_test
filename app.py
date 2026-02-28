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

def get_used_names():
    try:
        df = read_sheet()
        if df.empty or "User_ID" not in df.columns:
            return set()
        return set(df["User_ID"].unique())
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
    sheet = get_sheet()
    all_values = sheet.get_all_values()
    for i in range(len(all_values) - 1, 0, -1):
        row = all_values[i]
        if len(row) >= 3 and row[1] == user_id and row[2] == test_group:
            sheet.delete_rows(i + 1)
            return True
    return False

# --- 2. 統計圖表函式 ---
def show_group_stats(df, group_name):
    df_group = df[df["Test_Group"] == group_name]
    if df_group.empty:
        st.info(f"{group_name}：尚無資料")
        return

    total  = len(df_group)
    counts = df_group["Winner"].value_counts()
    pct    = (counts / total * 100).round(1)

    # 整理表格
    stat_df = pd.DataFrame({
        "勝利筆數": counts,
        "勝率 (%)": pct,
        "總筆數":   total
    }).fillna(0)
    stat_df["勝利筆數"] = stat_df["勝利筆數"].astype(int)
    stat_df.index.name = "方法"

    st.markdown(f"**{group_name}**　（共 {total} 筆）")
    st.bar_chart(pct)
    st.dataframe(stat_df, use_container_width=True)

# --- 3. 功能函式：自動配對檔案 ---
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

def build_combined_test(user_id):
    combined = []
    for group in ["baseline_LLM", "DNSMIOS_LLM"]:
        trials = load_files(group)
        random.seed(f"{user_id}_{group}_order")
        random.shuffle(trials)
        trials = trials[:10]
        for t in trials:
            t["test_group"] = group
        combined.extend(trials)
    return combined

# --- 4. 初始化 Session State ---
if 'user_id'     not in st.session_state: st.session_state.user_id     = ""
if 'current_idx' not in st.session_state: st.session_state.current_idx = 0
if 'test_data'   not in st.session_state: st.session_state.test_data   = []
if 'test_ready'  not in st.session_state: st.session_state.test_ready  = False

# --- 5. 側邊欄：管理員後台 ---
with st.sidebar:
    st.title("管理員後台")
    if st.checkbox("開啟數據統計"):
        pw = st.text_input("輸入密碼", type="password")
        if pw == "1234":
            try:
                existing_data = read_sheet()
                if not existing_data.empty:
                    st.success(f"累計受測人數：{existing_data['User_ID'].nunique()} 人")
                    st.markdown("---")
                    show_group_stats(existing_data, "baseline_LLM")
                    st.markdown("---")
                    show_group_stats(existing_data, "DNSMIOS_LLM")
                    st.markdown("---")
                    st.subheader("原始資料")
                    st.dataframe(existing_data, use_container_width=True)
                else:
                    st.info("目前雲端表格內沒有任何資料。")
            except Exception as e:
                st.error(f"讀取失敗: {e}")

# --- 6. 主介面流程 ---
st.title("語音品質主觀聽測 (AB Test)")

# 步驟 A: 填寫名字
if not st.session_state.user_id:
    st.info("請輸入您的姓名以開始測試。")
    name_input = st.text_input("姓名")

    if st.button("確認並進入測試"):
        name = name_input.strip()
        if not name:
            st.error("姓名不能為空白，請輸入您的姓名。")
        else:
            used_names = get_used_names()
            if name in used_names:
                st.error(f"「{name}」已參加過測試，請確認姓名是否正確。")
            else:
                st.session_state.user_id   = name
                st.session_state.test_data = build_combined_test(name)
                st.session_state.test_ready = True
                st.rerun()

# 步驟 B: 進行測試
else:
    st.write(f"受測者：**{st.session_state.user_id}**")

    data  = st.session_state.test_data
    total = len(data)

    if data and st.session_state.current_idx < total:
        trial         = data[st.session_state.current_idx]
        current_group = trial["test_group"]
        idx           = st.session_state.current_idx

        section = "第一部分 (1-10題)" if idx < 10 else "第二部分 (11-20題)"
        st.subheader(f"進度：{idx + 1} / {total}　　{section}")

        random.seed(f"{st.session_state.user_id}_{current_group}_{idx}")
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
        st.write("哪一個聲音品質較好？")
        c1, c2, c3 = st.columns(3)

        def save_and_next(choice_label, winner_name):
            new_row = {
                "Timestamp":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "User_ID":    st.session_state.user_id,
                "Test_Group": current_group,
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

        if c1.button("A 較好", use_container_width=True):
            save_and_next("A", a_lab)
        if c2.button("無明顯差異", use_container_width=True):
            save_and_next("Tie", "None")
        if c3.button("B 較好", use_container_width=True):
            save_and_next("B", b_lab)

        st.markdown("---")
        if st.session_state.current_idx > 0:
            if st.button("回上一題"):
                prev_trial = data[st.session_state.current_idx - 1]
                try:
                    delete_last_row_for_user(st.session_state.user_id, prev_trial["test_group"])
                except Exception as e:
                    st.error(f"刪除記錄失敗: {e}")
                st.session_state.current_idx -= 1
                st.rerun()

    elif total > 0:
        st.balloons()
        st.success("測試完成！感謝您的參與，您的答案已自動儲存。")
