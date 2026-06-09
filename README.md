# taobao-crawler

淘宝搜索全自动抓取，Web 界面控制 + DrissionPage 驱动 + SQLite 入库。

## 运行

```bash
pip install flask DrissionPage jsonpath
python server.py
# → http://localhost:5000
```

打开网页，输入关键词，后台自动启动 Chrome，拦截淘宝接口，翻到底，商品实时显示。

## 流程

```
浏览器输入关键词 → Flask 启动后台线程 → DrissionPage 打开 Chrome
  → 监听淘宝推荐接口 → 拦截 jsonp 响应
    → 线程池解析字段 → SQLite 入库 → SSE 实时推前端
      → 点击下一页 → 循环直到到底
```

## 文件

| 文件 | 说明 |
|------|------|
| `server.py` | Flask + 爬虫 + SSE 实时推送 |
| `templates/index.html` | Web 前端 |
| `淘宝.py` | 原命令行版，单文件可独立跑 |

## 两种用法

### Web 版（推荐）
```bash
python server.py
# 浏览器打开 http://localhost:5000，输入关键词点搜索
```

### 命令行版
```bash
python 淘宝.py
# 固定搜索"手机"，翻到底入库
```

## 抓取字段

商品 ID、产品名、价格、店铺、回头客数、所在地、排名、商品图

## 注意

- 首次运行自动创建 `淘宝.db`
- Cookie、PID 等参数已在代码中填写真实值，替换成你自己的即可
- 仅供学习研究，请遵守平台使用协议
