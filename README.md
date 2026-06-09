# taobao-crawler

淘宝搜索页爬虫，DrissionPage 驱动浏览器 + 线程池解析 + SQLite 入库。

## 流程

```
启动 Chromium
    ↓
打开淘宝搜索页 + 开启接口监听
    ↓
┌─ 循环翻页 ──────────────────┐
│ 1. 拦截接口响应（jsonp）     │
│ 2. 正则提取 JSON             │
│ 3. 线程池并行解析字段         │
│ 4. 批量 INSERT OR IGNORE     │
│ 5. 点击"下一页"              │
└─────────────────────────────┘
    ↓
汇总：入库总数 / 有排名数
```

## 技术栈

| 组件 | 用途 |
|------|------|
| [DrissionPage](https://github.com/g1879/DrissionPage) | 浏览器控制 + 接口监听 |
| `concurrent.futures.ThreadPoolExecutor` | 多线程解析，max_workers=4 |
| `sqlite3`（Python 自带） | 本地存储，`INSERT OR IGNORE` 自动去重 |
| `jsonpath` | 从响应 JSON 中提取字段 |

## 安装

```bash
pip install DrissionPage jsonpath
```

## 运行

```bash
python 淘宝.py
```

## 输出

- `淘宝.db` — SQLite 数据库，goods 表结构：

| 字段 | 说明 |
|------|------|
| item_id | 商品唯一 ID（UNIQUE） |
| 产品名 | title |
| 价格 | priceShow.price |
| 店铺 | shopInfo.title |
| 回头客 | shopTag |
| 地址 | procity |
| 排名 | hotListInfo.rank_short_text |

## 环境

- Python 3.8+
- Chrome / Chromium 浏览器
- 首次运行会自动创建数据库文件

## 注意

- 淘宝客 PID 已替换为 placeholder，使用时替换为自己的推客 PID
- 爬虫数据库（淘宝.db）已删除，仓库只保留代码
- 仅供学习研究，请遵守平台使用协议
