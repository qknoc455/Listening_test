import streamlit as st
import os
import random
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="語音聽測系統", layout="centered")

# --- 自動路徑修正邏輯 ---
def load_files(test_type):
    # 根據截圖，確保路徑開頭為 data/
    base_path = f"data/{test_type}"
    
    if not os.path.exists(base_path):
        st.error(f"找不到路徑: {base_path}，請檢查 GitHub 檔案名稱是否正確。")
        return []

    # 取得子資料夾並過濾掉隱藏檔
    subfolders = sorted([f for f in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, f)) and not f.startswith('.')])
    
    if len(subfolders) < 2:
        st.error(f"資料夾數量不足，目前在 {test_type} 下只看到: {subfolders}")
        return []
    
    folder1, folder2 = subfolders[0], subfolders[1]
    path1, path2 = os.path.join(base_path, folder1), os.path.join(base_path, folder2)
    
    # 配對同名檔案
    files = sorted([f for f in os.listdir(path1) if f.lower().endswith(('.wav', '.mp3'))])
    
    paired_data = []
    for f in files:
        if os.path.exists(os.path.join(path2, f)):
            paired_data.append({
                "file_name": f,
                "path_1": os.path.join(path1, f), "label_1": folder1,
                "path_2": os.path.join(path2, f), "label_2": folder2
            })
    return paired_data

# --- 初始化 ---
if 'results_file' not in st.session_state:
    st.session_state.results_file = "all_user_results.csv"

# 初始化 Session State
for key in ['current_idx', 'results', 'test_data', 'shuffled', 'user_id']:
    if key not in st.session_state:
        st.session_state[key] = 0 if key == 'current_idx' else ([] if key == 'results' else (False if key == 'shuffled' else ""))

# --- 側邊欄：管理員後台 ---
with st.sidebar:
    st.title("後台管理")
    admin_mode = st.checkbox("開啟管理員模式")
    if admin_mode:
        pw = st.text_input("輸入管理密碼", type="password")
        if pw == "1234": # 您可以自行修改密碼
            st.success("管理員已登入")
            if os.path.exists(st.session_state.results_file):
                all_data = pd.read_csv(st.session_state.results_file)
                st.write(f"目前累計受測人數: {all_data['User_ID'].nunique()}")
                st.subheader("累計勝率統計")
                st.bar_chart(all_data['Winner'].value_counts())
                st.dataframe(all_data)
            else:
                st.warning("尚無累積數據")

# --- 主畫面 ---
st.title("🎧 語音品質 AB 聽測")

if not st.session_state.user_id:
    st.session_state.user_id = st.text_input("請輸入您的姓名或編號以開始：")
else:
    test_options = ["baseline_LLM", "DNSMOS_LLM", "Noisy_LLM"]
    selected_test = st.selectbox("測試組別", test_options)

    if not st.session_state.shuffled:
        st.session_state.test_data = load_files(selected_test)
        random.shuffle(st.session_state.test_data)
        st.session_state.shuffled = True

    data = st.session_state.test_data

    if data and st.session_state.current_idx < len(data):
        trial = data[st.session_state.current_idx]
        st.write(f"進度: {st.session_state.current_idx + 1} / {len(data)}")
        
        # 盲測隨機化
        random.seed(st.session_state.current_idx)
        swapped = random.choice([True, False])
        a_path, a_lab = (trial['path_2'], trial['label_2']) if swapped else (trial['path_1'], trial['label_1'])
        b_path, b_lab = (trial['path_1'], trial['label_1']) if swapped else (trial['path_2'], trial['label_2'])

        col1, col2 = st.columns(2)
        with col1: st.write("A"); st.audio(a_path)
        with col2: st.write("B"); st.audio(b_path)

        st.write("---")
        c1, c2, c3 = st.columns(3)
        
        def commit(choice, winner):
            res = {
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "User_ID": st.session_state.user_id,
                "Test_Group": selected_test,
                "File": trial['file_name'],
                "Choice": choice,
                "Winner": winner
            }
            # 即時寫入本地 CSV (Streamlit Cloud 重啟前有效)
            df_new = pd.DataFrame([res])
            df_new.to_csv(st.session_state.results_file, mode='a', index=False, header=not os.path.exists(st.session_state.results_file))
            st.session_state.current_idx += 1

        if c1.button("A 較好"): commit("A", a_lab); st.rerun()
        if c2.button("無差異"): commit("Tie", "None"); st.rerun()
        if c3.button("B 較好"): commit("B", b_lab); st.rerun()

    elif len(data) > 0:
        st.success("測試完成！")
        if st.button("進行另一組測試"):
            st.session_state.current_idx = 0
            st.session_state.shuffled = False
            st.rerun()
