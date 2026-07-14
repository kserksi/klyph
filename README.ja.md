# Klyph

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md)

リポジトリ：[github.com/kserksi/klyph](https://github.com/kserksi/klyph)

Klyph は決定論的でセルフホスト可能な Web フォント・サブセットサービスです。FastAPI と FontTools を使用して要求された文字集合を正規化し、不変な WOFF2 サブセットを生成して、バージョン付き API とブラウザ SDK から配信します。特定のドメインやホスティング基盤には依存しません。

## 特長

- フォントバージョン、生成オプション、正規化済み文字に基づく決定論的なサブセット
- 同時実行数、キュー長、タイムアウトを制限した独立プロセスでの生成
- ブラウザと CDN の長期キャッシュに対応する不変なフォント URL
- 30 日を超えてアクセスされていないキャッシュの自動削除
- Origin 許可リスト、リクエストサイズ制限、セキュリティヘッダー、構造化ログ
- ヘルスチェック、準備状態、法務、ライセンス、OSS コンポーネントの各ページ

## フォント資産

フォントは Google Fonts の公式 GitHub リポジトリから取得し、特定のコミットに固定しています。

```powershell
python scripts/download_fonts.py
```

スクリプトは取得元情報と SHA-256 ダイジェストを `fonts/sources.json` に記録します。両フォントファミリーには SIL Open Font License 1.1 のライセンス文書が含まれています。

## ローカル開発

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[test]"
python scripts/download_fonts.py
.venv\Scripts\uvicorn app.main:app --reload
```

テストの実行：

```powershell
.venv\Scripts\python.exe -m pytest
```

## Docker

イメージをビルドする前にフォントを取得します。

```powershell
python scripts/download_fonts.py
docker build -t klyph .
docker run --rm -p 8000:8000 `
  -e FONT_PUBLIC_BASE_URL=https://fonts.example.com `
  -e FONT_ALLOWED_ORIGINS=https://www.example.com `
  -v font-cache:/app/cache `
  klyph
```

イメージは Python 3.14.6 slim をベースとし、非 root ユーザーで単一の HTTP プロセスを起動します。`/healthz` は生存確認、`/readyz` は必要なフォントファイルとキャッシュディレクトリの書き込み可否も確認します。実行時依存関係は `requirements.lock` に固定されています。

## API v2

```http
POST /v2/subsets
Content-Type: application/json

{"font":"zen-kaku-regular","characters":"障害情報"}
```

レスポンスには、フォントバージョンと正規化済み文字ハッシュでバージョン管理された不変の WOFF2 URL が含まれます。

エラーレスポンス：

- `400`：フォントまたは文字入力が不正
- `403`：ブラウザの Origin が許可されていない
- `413`：リクエストボディが設定上限を超過
- `503`：生成キュー満杯、ロック待機タイムアウト、または生成タイムアウト
- `507`：キャッシュ容量または最小空き容量の制限に到達

## ブラウザ SDK

```html
<script defer src="https://fonts.example.com/sdk/v2.js"></script>
<script>
document.addEventListener('DOMContentLoaded', function () {
  WebFont.load({
    font: 'zen-kaku-regular',
    family: 'Zen Kaku Gothic New',
    selectors: ['.post-content', '.site-header']
  });
});
</script>
```

監視対象のコンテンツが変化する場合は、`WebFont.observe()` でデバウンス付き増分読み込みを利用できます。

## 情報ページ

- `/`：サービス概要、リアルタイム準備状態、フォント見本、内部 API の概要
- `/terms`：利用規約
- `/privacy`：文字データ、ログ、外部サービス、キャッシュの取扱方針
- `/licenses`：フォント、背景作品、ソフトウェアのライセンスとクレジット
- `/components`：本番環境の OSS コンポーネントと固定バージョン

各ページは `/assets/site.css` と `/assets/site.js` を共有し、Cookie、localStorage、第三者分析を使用しません。FastAPI の対話型ドキュメントと OpenAPI Schema は公開していません。

検索向け情報は `robots.txt`、`sitemap.xml`、Canonical、hreflang、Open Graph、Twitter Card、Schema.org JSON-LD で提供します。機械向けエンドポイントは `X-Robots-Tag: noindex, nofollow` を返します。

ビジュアルを変更した場合は、Windows でローカルのブランド資産を再生成します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/generate_brand_assets.ps1
```

## 設定

| 環境変数 | デフォルト | 説明 |
| --- | ---: | --- |
| `FONT_PUBLIC_BASE_URL` | `http://localhost:8000` | API レスポンスと動的メタデータで使用する固定の公開ルート URL |
| `FONT_ALLOWED_ORIGINS` | ローカルの 8000 番ポート | 生成 API を呼び出せる Origin のカンマ区切り一覧 |
| `FONT_MAX_REQUEST_BYTES` | `65536` | リクエストボディの最大バイト数 |
| `FONT_MAX_CHARACTERS` | `8000` | 正規化後のユニーク文字数上限 |
| `FONT_GENERATION_TIMEOUT` | `20` | ロック待機と生成処理を合わせたタイムアウト秒数 |
| `FONT_GENERATION_WORKERS` | `2` | 同時に実行するフォント生成プロセス数 |
| `FONT_MAX_PENDING_GENERATIONS` | `32` | 異なる文字集合に対する保留ジョブ数上限 |
| `FONT_MAX_CACHE_BYTES` | `10737418240` | 不変フォントキャッシュの上限（10 GiB） |
| `FONT_MIN_FREE_BYTES` | `268435456` | キャッシュボリュームに残す最小空き容量（256 MiB） |
| `FONT_CACHE_MAX_AGE_DAYS` | `30` | 未アクセスのフォントを削除するまでの日数 |
| `FONT_CACHE_CLEANUP_INTERVAL` | `86400` | キャッシュ清掃の間隔秒数（24 時間） |
| `FONT_SHUTDOWN_TIMEOUT` | `10` | 正常終了時の待機秒数 |
| `FONT_LOG_LEVEL` | `INFO` | 構造化アプリケーションログのレベル |

Klyph は標準出力に 1 行形式の JSON ログを出力します。リクエスト ID、フォント ID、ユニーク文字数、サブセットハッシュ、キャッシュヒット、出力サイズ、処理時間を記録し、元の文字内容は記録しません。

## 本番運用上の注意

- CORS と Origin の確認は認証ではありません。オリジンサーバーへのアクセスをエッジプロキシに限定し、`/v2/subsets` にメソッド制限、クライアント別レート制限、全体サーキットブレーカーを設定してください。
- `/v2/fonts/*` は長期 CDN キャッシュを使用してください。
- オリジンインスタンスごとに HTTP プロセスを 1 つに保ちます。各サブセット処理は独立した子プロセスで実行され、タイムアウト時に終了します。
- キャッシュ済み WOFF2 の内容は不変です。アクセスマーカーで利用時刻を記録し、30 日を超えて未使用の項目を定期的に削除します。
- 複数オリジン構成では、ローカルキャッシュを共有オブジェクトストレージに、ファイルロックを分散ロックに置き換えてください。
- `503`、`507`、生成失敗、生成レイテンシーを監視してください。

## ライセンス

Klyph のソースコードは [Apache License 2.0](LICENSE) で提供されます。同梱フォントには別途 SIL Open Font License 1.1 が適用されます。クレジットの詳細は `fonts/OFL-kaku.txt`、`fonts/OFL-maru.txt`、`/licenses` ページを参照してください。
