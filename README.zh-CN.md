# Klyph

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md)

项目地址：[github.com/kserksi/klyph](https://github.com/kserksi/klyph)

Klyph 是确定性、可自行托管的 Web 字体子集服务。它使用 FastAPI 和 FontTools 规范化请求的字符集合，生成不可变的 WOFF2 子集，并通过版本化 API 和浏览器 SDK 提供字体加载能力，不依赖特定域名或托管平台。

## 功能特点

- 根据字体版本、生成选项和规范化字符确定性生成子集
- 使用独立进程生成字体，并限制并发量、队列长度和执行时间
- 使用不可变字体 URL，支持浏览器和 CDN 长期缓存
- 自动删除超过 30 天未访问的缓存字体
- 提供 Origin 白名单、请求大小限制、安全响应头和结构化日志
- 提供健康检查、就绪检查、法律、许可和开源组件页面

## 字体资源

字体来自 Google Fonts 官方 GitHub 仓库，并固定到准确的提交：

```powershell
python scripts/download_fonts.py
```

脚本会将来源信息和 SHA-256 摘要写入 `fonts/sources.json`。两个字体系列均附带 SIL Open Font License 1.1 许可文本。

## 本地开发

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[test]"
python scripts/download_fonts.py
.venv\Scripts\uvicorn app.main:app --reload
```

运行测试：

```powershell
.venv\Scripts\python.exe -m pytest
```

## Docker

构建镜像前先下载字体：

```powershell
python scripts/download_fonts.py
docker build -t klyph .
docker run --rm -p 8000:8000 `
  -e FONT_PUBLIC_BASE_URL=https://fonts.example.com `
  -e FONT_ALLOWED_ORIGINS=https://www.example.com `
  -v font-cache:/app/cache `
  klyph
```

镜像基于 Python 3.14.6 slim，以非 root 用户运行，并仅启动一个 HTTP 进程。`/healthz` 用于存活检查；`/readyz` 还会检查字体文件是否存在以及缓存目录是否可写。运行依赖固定在 `requirements.lock`。

## API v2

```http
POST /v2/subsets
Content-Type: application/json

{"font":"zen-kaku-regular","characters":"障害情報"}
```

响应包含基于字体版本和规范化字符哈希的不可变 WOFF2 地址。

错误响应：

- `400`：字体或字符输入无效
- `403`：浏览器 Origin 不在允许列表中
- `413`：请求体超过配置限制
- `503`：生成队列已满、锁等待超时或字体生成超时
- `507`：缓存容量或磁盘最小剩余空间达到限制

## 浏览器 SDK

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

当被监控的内容发生变化时，可以使用 `WebFont.observe()` 进行防抖增量加载。

## 信息页面

- `/`：服务介绍、实时就绪状态、字体示例和内部 API 概览
- `/terms`：使用条款
- `/privacy`：字符数据、日志、外部服务和缓存处理政策
- `/licenses`：字体、背景作品和软件的许可与署名
- `/components`：生产环境使用的开源组件和固定版本

页面共享 `/assets/site.css` 和 `/assets/site.js`，不使用 Cookie、localStorage 或第三方分析脚本。FastAPI 的交互式文档和 OpenAPI Schema 均未公开。

搜索信息通过 `robots.txt`、`sitemap.xml`、Canonical、hreflang、Open Graph、Twitter Card 和 Schema.org JSON-LD 提供。机器接口返回 `X-Robots-Tag: noindex, nofollow`。

修改视觉标识后，可在 Windows 上重新生成本地品牌资源：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/generate_brand_assets.ps1
```

## 配置

| 环境变量 | 默认值 | 说明 |
| --- | ---: | --- |
| `FONT_PUBLIC_BASE_URL` | `http://localhost:8000` | API 响应和动态元数据使用的固定公网根地址 |
| `FONT_ALLOWED_ORIGINS` | 本机 8000 端口 | 允许调用生成接口的 Origin，使用逗号分隔 |
| `FONT_MAX_REQUEST_BYTES` | `65536` | 请求体字节上限 |
| `FONT_MAX_CHARACTERS` | `8000` | 规范化后唯一字符数量上限 |
| `FONT_GENERATION_TIMEOUT` | `20` | 锁等待和单次生成的总超时秒数 |
| `FONT_GENERATION_WORKERS` | `2` | 同时运行的字体生成进程数 |
| `FONT_MAX_PENDING_GENERATIONS` | `32` | 不同字符集合的最大待处理任务数 |
| `FONT_MAX_CACHE_BYTES` | `10737418240` | 不可变字体缓存总量上限（10 GiB） |
| `FONT_MIN_FREE_BYTES` | `268435456` | 缓存卷必须保留的最小空间（256 MiB） |
| `FONT_CACHE_MAX_AGE_DAYS` | `30` | 字体连续未访问多少天后删除 |
| `FONT_CACHE_CLEANUP_INTERVAL` | `86400` | 缓存清理间隔秒数（24 小时） |
| `FONT_SHUTDOWN_TIMEOUT` | `10` | 服务优雅退出的等待秒数 |
| `FONT_LOG_LEVEL` | `INFO` | 应用结构化日志级别 |

Klyph 仅向标准输出写入单行 JSON 日志。日志包括请求 ID、字体 ID、唯一字符数、子集哈希、缓存命中、输出大小和耗时，不记录原始字符内容。

## 生产部署说明

- CORS 和 Origin 检查不是身份验证。源站应仅允许边缘代理访问，并为 `/v2/subsets` 配置方法规则、客户端限流和全局熔断。
- `/v2/fonts/*` 应使用长期 CDN 缓存。
- 每个源站实例保持一个 HTTP 进程。每次字体裁剪在独立子进程中运行，并在超时后终止。
- 缓存的 WOFF2 内容保持不可变。服务使用访问标记记录使用时间，并定期删除超过 30 天未访问的条目。
- 多源站实例部署时，应将本地缓存替换为共享对象存储，并使用分布式生成锁。
- 应对 `503`、`507`、生成失败和生成延迟配置监控告警。

## 许可

Klyph 源代码使用 [Apache License 2.0](LICENSE)。项目包含的字体单独使用 SIL Open Font License 1.1。Hero 背景图由 **Lilac** 创作（[Pixiv 作品 #146748240](https://www.pixiv.net/artworks/146748240)），图片的著作权、所有权及其他全部权利均归作者所有，不适用 Apache-2.0。署名信息请参阅 `fonts/OFL-kaku.txt`、`fonts/OFL-maru.txt` 和 `/licenses` 页面。
