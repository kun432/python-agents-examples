import os

import yaml


def load_prompt(filename):
    """YAMLファイルからプロンプトを読み込む"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_path = os.path.join(script_dir, "prompts", filename)

    try:
        with open(prompt_path) as file:
            prompt_data = yaml.safe_load(file)
            return prompt_data.get("instructions", "")
    except (FileNotFoundError, yaml.YAMLError) as e:
        print(f"エラー: プロンプトファイル {filename} の読み込みに失敗しました: {e}")
        return ""
