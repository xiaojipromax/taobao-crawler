"""
淘宝搜索控制台 — Web 界面 + 后台爬虫
启动：python server.py → 浏览器打开 http://localhost:5000
"""
from flask import Flask, request, Response, render_template, jsonify
import threading, queue, re, json, os, sqlite3
from DrissionPage import Chromium
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
import jsonpath

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, '淘宝.db')
LISTEN_API = '/h5/mtop.relationrecommend.wirelessrecommend.recommend/2.0/'

# SSE 事件队列
event_queues = []

def broadcast(event):
    dead = []
    for q in event_queues:
        try:
            q.put(event)
        except:
            dead.append(q)
    for q in dead:
        event_queues.remove(q)

# ==================== 数据库 ====================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS goods (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id   TEXT,
            keyword   TEXT,
            产品名    TEXT,
            价格      TEXT,
            店铺      TEXT,
            回头客    TEXT,
            地址      TEXT,
            排名      TEXT,
            pic_path  TEXT,
            UNIQUE(item_id, keyword)
        )
    ''')
    conn.commit()
    conn.close()

def insert_batch(items, keyword):
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(build_doc, i, keyword) for i in items]
        docs = [f.result() for f in as_completed(futures)]

    conn = sqlite3.connect(DB_PATH)
    conn.executemany('''
        INSERT OR IGNORE INTO goods (item_id, keyword, 产品名, 价格, 店铺, 回头客, 地址, 排名, pic_path)
        VALUES (:item_id, :keyword, :产品名, :价格, :店铺, :回头客, :地址, :排名, :pic_path)
    ''', docs)
    conn.commit()
    conn.close()
    return docs

def build_doc(item, keyword):
    return {
        'item_id': (jsonpath.jsonpath(item, 'item_id') or [''])[0],
        'keyword': keyword,
        '产品名':  (jsonpath.jsonpath(item, 'title') or [''])[0],
        '价格':    (jsonpath.jsonpath(item, 'priceShow.price') or [''])[0],
        '店铺':    (jsonpath.jsonpath(item, 'shopInfo.title') or [''])[0],
        '回头客':  (jsonpath.jsonpath(item, 'shopTag') or [''])[0],
        '地址':    (jsonpath.jsonpath(item, 'procity') or [''])[0],
        '排名':    (jsonpath.jsonpath(item, 'hotListInfo.rank_short_text') or [''])[0],
        'pic_path':(jsonpath.jsonpath(item, 'pic_path') or [''])[0],
    }

# ==================== 爬虫 ====================

def crawl(keyword):
    try:
        broadcast({'type': 'status', 'running': True, 'page': 0, 'total': 0,
                    'message': f'正在启动浏览器...'})

        chrome = Chromium()
        tab = chrome.latest_tab
        tab.listen.start(LISTEN_API)

        encoded = quote(keyword)
        url = (f'https://uland.taobao.com/sem/tbsearch?bc_fl_src=tbsite_l2Y0Iait'
               f'&keyword={encoded}&q={encoded}'
               f'&refpid=mm_26632258_3504122_32538762&search_type=item&tab=all')
        tab.get(url)

        page = 1
        total_items = 0

        while True:
            broadcast({'type': 'status', 'running': True, 'page': page, 'total': total_items,
                        'message': f'正在采集第 {page} 页...'})

            tab.wait(1, scope=2)
            res = tab.listen.wait(timeout=10)
            if not res:
                broadcast({'type': 'status', 'running': True, 'page': page, 'total': total_items,
                            'message': f'第 {page} 页无数据'})
                break

            result = re.findall(r'mtopjsonp\d+\((.*)\)', res.response.body, re.S)[0]
            items = json.loads(result)['data']['itemsArray']

            if not items:
                break

            docs = insert_batch(items, keyword)
            total_items += len(docs)

            for doc in docs:
                broadcast({'type': 'item', 'data': doc})

            broadcast({'type': 'status', 'running': True, 'page': page, 'total': total_items,
                        'message': f'第 {page} 页完成，+{len(docs)} 条'})

            btn = tab.ele('下一页')
            if not btn:
                broadcast({'type': 'status', 'running': True, 'page': page, 'total': total_items,
                            'message': '已到最后一页'})
                break

            btn.click(by_js=True)
            page += 1

        # 汇总
        conn = sqlite3.connect(DB_PATH)
        ranked = conn.execute(
            "SELECT COUNT(*) FROM goods WHERE keyword=? AND 排名 != ''",
            (keyword,)
        ).fetchone()[0]
        conn.close()

        broadcast({'type': 'done', 'page': page, 'total': total_items, 'ranked': ranked,
                    'message': f'完成，共 {page} 页，入库 {total_items} 条（其中 {ranked} 条有排名）'})
        broadcast({'type': 'status', 'running': False, 'page': page, 'total': total_items,
                    'message': f'完成，共 {page} 页，入库 {total_items} 条（其中 {ranked} 条有排名）'})

    except Exception as e:
        broadcast({'type': 'error', 'message': str(e)})
        broadcast({'type': 'status', 'running': False, 'page': 0, 'total': 0,
                    'message': f'出错：{e}'})

# ==================== Flask 路由 ====================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/search', methods=['POST'])
def api_search():
    keyword = request.json.get('keyword', '').strip()
    if not keyword:
        return jsonify({'error': '请输入搜索关键词'}), 400

    t = threading.Thread(target=crawl, args=(keyword,), daemon=True)
    t.start()
    return jsonify({'status': 'started'})

@app.route('/api/stream')
def api_stream():
    def event_stream():
        q = queue.Queue()
        event_queues.append(q)
        try:
            while True:
                data = q.get()
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        except GeneratorExit:
            if q in event_queues:
                event_queues.remove(q)
    return Response(event_stream(), content_type='text/event-stream')

@app.route('/api/history')
def api_history():
    keyword = request.args.get('keyword', '')
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if keyword:
        rows = conn.execute(
            "SELECT * FROM goods WHERE keyword=? ORDER BY id DESC",
            (keyword,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT keyword, COUNT(*) as cnt FROM goods GROUP BY keyword ORDER BY cnt DESC"
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

if __name__ == '__main__':
    init_db()
    print('淘宝搜索控制台 → http://localhost:5000')
    app.run(host='0.0.0.0', port=5000, debug=False)
