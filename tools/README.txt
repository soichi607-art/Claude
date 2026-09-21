FFmpeg を PATH に追加できない場合は、ダウンロードした FFmpeg の zip を解凍して、
そのフォルダをまるごと この tools フォルダに入れてください（例: tools/ffmpeg-8.0-essentials_build/...）。
アプリが中の ffmpeg.exe / ffprobe.exe を自動で探します。bin フォルダを探す必要はありません。

Windows なら、コマンドプロンプトで次を実行してもインストールできます（Microsoft の winget 公式リポジトリに登録されたパッケージ）:
  winget install -e --id Gyan.FFmpeg
インストール後は新しいウィンドウで start_windows.bat を実行してください。
