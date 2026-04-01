import os
import json
import time
import random
import pickle
from datetime import datetime
import hagetaka_scanner as scanner
import fair_value_calc_y4 as fv

# キャッシュ保存先
CACHE_DIR = "data"
MA_CACHE_FILE = os.path.join(CACHE_DIR, "daily_ma_cache.json")
HAGETAKA_CACHE_FILE = os.path.join(CACHE_DIR, "daily_hagetaka_cache.pkl")
TEMP_MA_FILE = os.path.join(CACHE_DIR, "daily_ma_cache_temp.json")
TEMP_HAGETAKA_FILE = os.path.join(CACHE_DIR, "daily_hagetaka_cache_temp.pkl")

def run_nightly_batch():
    print(f"[{datetime.now()}] 夜間バッチ処理（APIブロック回避＆JSON修正モード）を開始します")
    
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
        
    all_codes = scanner.get_all_japan_stocks()
    total = len(all_codes)
    
    # ----------------------------------------------------
    # 1. Tab2（M&A予兆監視）用データの生成（JSON保存）
    # ----------------------------------------------------
    print(f"\n[{datetime.now()}] 1/2: M&Aスコア用データの取得を開始")
    ma_results = {}
    
    for i, code in enumerate(all_codes):
        print(f"[{i+1}/{total}] M&Aデータ取得中: {code}")
        try:
            # 1銘柄ずつ確実に取得
            bundle_data = fv.calc_genta_bundle([code])
            
            # 【修正ポイント】JSON保存エラーの原因になる「DataFrame(表データ)」を安全に削除
            for k, v in bundle_data.items():
                if "hist_data" in v:
                    v["hist_data"] = None 
                    
            ma_results.update(bundle_data)
        except Exception as e:
            print(f"エラー {code}: {e}")
            
        # APIブロック対策の確実なスリープ (3〜5秒)
        time.sleep(random.uniform(3.0, 5.0))
        
        # 50件ごとに長めの休憩＆中間セーブを入れる（クラッシュ対策）
        if (i + 1) % 50 == 0:
            print(f"--- 50件完了。API制限回避のため30秒休憩＆中間セーブ ---")
            with open(TEMP_MA_FILE, 'w', encoding='utf-8') as f:
                json.dump({"updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "data": ma_results}, f, ensure_ascii=False)
            time.sleep(30)
            
    # 最終保存
    with open(TEMP_MA_FILE, 'w', encoding='utf-8') as f:
        json.dump({"updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "data": ma_results}, f, ensure_ascii=False)
        
    # ----------------------------------------------------
    # 2. Tab1（ハゲタカスコープ）用データの生成（Pickle保存）
    # ----------------------------------------------------
    print(f"\n[{datetime.now()}] 2/2: ハゲタカシグナル用データのスキャンを開始")
    hagetaka_results = []
    
    for i, code in enumerate(all_codes):
        print(f"[{i+1}/{total}] ハゲタカスキャン中: {code}")
        try:
            # 1銘柄ずつ確実にスキャン
            res = scanner.scan_all_stocks([code])
            if res:
                hagetaka_results.extend(res)
        except Exception as e:
            print(f"エラー {code}: {e}")
            
        # APIブロック対策の確実なスリープ
        time.sleep(random.uniform(3.0, 5.0))
        
        # 50件ごとに長めの休憩＆中間セーブ
        if (i + 1) % 50 == 0:
            print(f"--- 50件完了。API制限回避のため30秒休憩＆中間セーブ ---")
            with open(TEMP_HAGETAKA_FILE, 'wb') as f:
                pickle.dump(hagetaka_results, f)
            time.sleep(30)
            
    # 最終保存
    with open(TEMP_HAGETAKA_FILE, 'wb') as f:
        pickle.dump(hagetaka_results, f)
        
    # ----------------------------------------------------
    # 3. アトミック置換（完成データを本番ファイルにすり替え）
    # ----------------------------------------------------
    os.replace(TEMP_MA_FILE, MA_CACHE_FILE)
    os.replace(TEMP_HAGETAKA_FILE, HAGETAKA_CACHE_FILE)
    print(f"\n[{datetime.now()}] 夜間バッチ処理完了。すべてのキャッシュを安全に更新しました。")

if __name__ == "__main__":
    run_nightly_batch()
