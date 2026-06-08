
"""
淘宝搜索页爬虫 — 翻到底 + 线程池 + SQLite 入库
SQLite 无需安装，数据库就是一个 .db 文件，Python 自带 sqlite3 模块直接操作
"""
import jsonpath
import sqlite3
import re, json, os
from DrissionPage import Chromium
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== 数据库 ====================

DB_PATH = os.path.join(os.path.dirname(__file__), '淘宝.db')


def init_db():
    """创建表 + 唯一索引。SQLite 用 IF NOT EXISTS 不会重复建表"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS goods (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id   TEXT UNIQUE,       -- 淘宝商品唯一ID，UNIQUE 自动帮你去重
            产品名    TEXT,
            价格      TEXT,
            店铺      TEXT,
            回头客    TEXT,
            地址      TEXT,
            排名      TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print('数据库就绪:', DB_PATH)


def insert_batch(items):
    """
    批量入库，先多线程组装数据，再一条 SQL 全插进去。
    线程池说明见下方注释。
    """
    # ============================================================
    # ThreadPoolExecutor：线程池，用来并行处理一批任务。
    # max_workers=4：最多同时开 4 个线程。线程数不是越多越好，
    # 这里是 I/O 密集型（等数据库写入），4 个足够了。
    #
    # 流程：
    #   1. pool.submit(build_doc, item)  →  把每个 item 提交给线程池
    #   2. 返回一个 Future 对象（可以理解为"未来的结果"）
    #   3. as_completed(futures)  →  谁先完成就先拿谁的结果
    #   4. f.result()  →  取出 build_doc 返回的字典
    #
    # 对比单线程 for 循环一个一个转：
    #   单线程：item1 → item2 → item3 → ...  （串行）
    #   线程池：item1、item2、item3、item4 同时处理  （并行）
    #   48 条数据量小感受不到区别，但写法可以复用到大批量场景
    # ============================================================
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(build_doc, i) for i in items]
        docs = [f.result() for f in as_completed(futures)]

    # insert or ignore：遇到重复的 item_id 就跳过，不报错
    conn = sqlite3.connect(DB_PATH)
    conn.executemany('''
        INSERT OR IGNORE INTO goods (item_id, 产品名, 价格, 店铺, 回头客, 地址, 排名)
        VALUES (:item_id, :产品名, :价格, :店铺, :回头客, :地址, :排名)
    ''', docs)
    conn.commit()
    conn.close()


def build_doc(item):
    """单条数据转字典，线程池里每个线程各跑一个 item"""
    return {
        'item_id': (jsonpath.jsonpath(item, 'item_id') or [''])[0],
        '产品名':  (jsonpath.jsonpath(item, 'title') or [''])[0],
        '价格':    (jsonpath.jsonpath(item, 'priceShow.price') or [''])[0],
        '店铺':    (jsonpath.jsonpath(item, 'shopInfo.title') or [''])[0],
        '回头客':  (jsonpath.jsonpath(item, 'shopTag') or [''])[0],
        '地址':    (jsonpath.jsonpath(item, 'procity') or [''])[0],
        '排名':    (jsonpath.jsonpath(item, 'hotListInfo.rank_short_text') or [''])[0],
    }


# ==================== 爬虫 ====================

def start_browser():
    """启动浏览器，打开淘宝搜索页，开启接口监听"""
    chrome = Chromium()
    tab = chrome.latest_tab
    tab.listen.start('/h5/mtop.relationrecommend.wirelessrecommend.recommend/2.0/')
    tab.get('https://uland.taobao.com/sem/tbsearch?bc_fl_src=tbsite_l2Y0Iait'
            '&keyword=%E6%89%8B%E6%9C%BA&q=%E6%89%8B%E6%9C%BA'
            '&refpid=mm_00000000_0000000_00000000&search_type=item&tab=all')
    return tab


def crawl_page(tab):
    """
    采集当前页数据，返回 item 列表。
    返回空列表表示没数据（到最后一页了）
    """
    tab.wait(1, scope=2)
    res = tab.listen.wait(timeout=10)
    if not res:
        return []

    # 淘宝接口返回的是 jsonp 格式：mtopjsonp3({...})，正则把 {} 部分抠出来
    result = re.findall(r'mtopjsonp\d+\((.*)\)', res.response.body, re.S)[0]
    return json.loads(result)['data']['itemsArray']


def has_next_page(tab):
    """找到"下一页"按钮就点击翻页，找不到说明到底了"""
    btn = tab.ele('下一页')
    if btn:
        btn.click(by_js=True)
        return True
    return False


# ==================== 主流程 ====================

def main():
    init_db()
    tab = start_browser()

    page = 1
    while True:
        items = crawl_page(tab)
        if not items:
            print(f'第{page}页无数据，结束')
            break

        insert_batch(items)
        print(f'第{page}页 {len(items)} 条')

        if not has_next_page(tab):
            break
        page += 1

    # 打印汇总
    conn = sqlite3.connect(DB_PATH)
    total = conn.execute('SELECT COUNT(*) FROM goods').fetchone()[0]
    ranked = conn.execute("SELECT COUNT(*) FROM goods WHERE 排名 != ''").fetchone()[0]
    conn.close()
    print(f'完成，共{page}页，入库 {total} 条（其中 {ranked} 条有排名）')


if __name__ == '__main__':
    main()
