"""
HuggingFaceトークンの状態を診断するスクリプト。
トークンはgetpassでその場入力するのみで、ファイルには一切保存しない。
使い方: python tools/check_hf_token.py
"""
import getpass

token = getpass.getpass("HuggingFaceアクセストークンを入力してください（画面には表示されません）: ")

print("\n=== 1. トークンの持ち主を確認 ===")
try:
    from huggingface_hub import whoami
    info = whoami(token=token)
    print(f"OK: このトークンは '{info.get('name')}' というアカウントのものです")
except Exception as e:
    print(f"NG: トークン自体が無効な可能性があります: {e}")

print("\n=== 2. pyannote/embedding へのアクセス権を直接確認 ===")
try:
    from huggingface_hub import model_info
    info = model_info("pyannote/embedding", token=token)
    print(f"OK: アクセスできています（gated={info.gated}）")
except Exception as e:
    print(f"NG: アクセスできません: {e}")

print("\n=== 3. pyannote/embedding のファイル一覧取得を試す ===")
try:
    from huggingface_hub import list_repo_files
    files = list_repo_files("pyannote/embedding", token=token)
    print(f"OK: ファイル一覧を取得できました: {files}")
except Exception as e:
    print(f"NG: ファイル一覧の取得に失敗: {e}")

print("\n=== 4. pyannote.audio の Model.from_pretrained を token= で試す ===")
try:
    from pyannote.audio import Model
    model = Model.from_pretrained("pyannote/embedding", token=token)
    print("OK: token= でロードできました")
except Exception as e:
    print(f"NG: token= で失敗: {type(e).__name__}: {e}")

print("\n=== 5. pyannote.audio の Model.from_pretrained を use_auth_token= で試す ===")
try:
    from pyannote.audio import Model
    model = Model.from_pretrained("pyannote/embedding", use_auth_token=token)
    print("OK: use_auth_token= でロードできました")
except Exception as e:
    print(f"NG: use_auth_token= で失敗: {type(e).__name__}: {e}")
