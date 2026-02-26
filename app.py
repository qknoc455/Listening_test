import streamlit as st
import os
import random
import pandas as pd
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

# 頁面基本設定
st.set_page_config(page_title="語音品質聽測系統", layout="centered")

# --- 1. 連接 Google Sheets ---
# 確保已在 Secrets 中設定 spreadsheet 連結
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. 功能函式：自動配對檔案 ---
def load_files(test_type):
    base_path = f"data/{test_type}"
    if not os.path.exists(base_path):
        st.error(f"路徑不存在: {base_path} (請檢查 GitHub 檔案結構)")
        return []

    # 取得子資料夾並過濾隱藏檔 (例如 .DS_Store)
    subfolders = sorted([f for f in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, f)) and not f.startswith('.')])
    
    if len(subfolders) < 2:
        st.error(f"資料夾數量不足，偵測到: {subfolders}")
        return []
    
    folder1, folder2 = subfolders[0], subfolders[1]
    path1, path2 = os.path.join(base_path, folder1), os.path.join(base_path, folder2)
    
    # 抓取音檔
    files = sorted([f for f in os.listdir(path1) if f.lower().endswith(('.wav', '.mp3'))])
    
    paired_data = []
    for f in files:
        target_file = os.path.join(path2, f)
        if os.path.exists(target_file):
            paired_data.append({
                "file_name": f,
                "path_1": os.path.join(path1, f), "label_1": folder1,
                "path_2": target_file, "label_2": folder2
            })
    return paired_data

# --- 3. 初始化 Session State ---
if 'user_id' not in st.session_state: st.session_state.user_id = ""
if 'current_idx' not in st.session_state: st.session_state.current_idx = 0
if 'test_data' not in st.session_state: st.session_state.test_data = []
if 'shuffled' not in st.session_state: st.session_state.shuffled = False

# --- 4. 側邊欄：管理員後台 ---
with st.sidebar:
    st.title("⚙️ 管理員後台")
    if st.checkbox("開啟數據統計"):
        pw = st.text_input("輸入密碼", type="password")
        if pw == "1234":
            try:
                # ttl=0 確保每次切換開關都抓取最新資料
                existing_data = conn.read(ttl=0)
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

# 步驟 A: 身分確認 (user1, user2...)
if not st.session_state.user_id:
    st.info("請輸入您的受測者編號以開始測試。")
    user_num = st.number_input("受測者編號 (例如輸入 1 會記錄為 user1)", min_value=1, max_value=100, step=1)
    if st.button("確認並進入測試"):
        st.session_state.user_id = f"user{user_num}"
        st.rerun()

# 步驟 B: 進行測試
else:
    st.write(f"當前測試者: **{st.session_state.user_id}**")
    
    test_options = ["baseline_LLM", "DNSMOS_LLM", "Noisy_LLM"]
    selected_test = st.selectbox("請選擇目前的測試組別：", test_options, 
                                 on_change=lambda: st.session_state.update(current_idx=0, shuffled=False))

    if not st.session_state.shuffled:
        st.session_state.test_data = load_files(selected_test)
        random.shuffle(st.session_state.test_data)
        st.session_state.shuffled = True

    data = st.session_state.test_data

    if data and st.session_state.current_idx < len(data):
        trial = data[st.session_state.current_idx]
        st.subheader(f"進度：{st.session_state.current_idx + 1} / {len(data)}")
        
        # 盲測隨機分配 A/B (使用特定 seed 確保在同一題內 A/B 位置不隨意跳動)
        random.seed(f"{st.session_state.user_id}_{selected_test}_{st.session_state.current_idx}")
        swapped = random.choice([True, False])
        
        a_path, a_lab = (trial['path_2'], trial['label_2']) if swapped else (trial['path_1'], trial['label_1'])
        b_path, b_lab = (trial['path_1'], trial['label_1']) if swapped else (trial['path_2'], trial['label_2'])

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
            new_row = pd.DataFrame([{
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "User_ID": st.session_state.user_id,
                "Test_Group": selected_test,
                "File": trial['file_name'],
                "Choice": choice_label,
                "Winner": winner_name
            }])
            
            # 寫入邏輯：讀取目前表格內容 -> 合併新列 -> 更新回 Google Sheets
            try:
                old_df = conn.read(ttl=0)
                updated_df = pd.concat([old_df, new_row], ignore_index=True)
                conn.update(data=updated_df)
            except:
                conn.update(data=new_row)
                
            st.session_state.current_idx += 1
            st.rerun()

        if c1.button("⬅️ A 較好", use_container_width=True):
            save_and_next("A", a_lab)
        if c2.button("無明顯差異", use_container_width=True):
            save_and_next("Tie", "None")
        if c3.button("B 較好 ➡️", use_container_width=True):
            save_and_next("B", b_lab)

    elif len(data) > 0:
        st.balloons()
        st.success("本組測試已完成！您的選擇已自動存入雲端表格。")
        if st.button("切換組別或重新開始"):
            st.session_state.current_idx = 0
            st.session_state.shuffled = False
            st.rerun()
