#!/usr/bin/env python3
"""审阅面的接缝测试：surface 契约、公共件宿主、页面经桥写反馈。

这一条缝把「页面 ↔ 落文件 ↔ 唤醒模型」从本 Skill 手里拿走了：页面是 review-surface 的入口，
宿主是 `planners-review-core` 的 `serve-review.mjs`（有插件时是 DSH 侧栏）。本 Skill 只剩三件事
——写 surface、判断宿主死活、把 URL 打开。所以这里测的是**这三件事加宿主真的能干活**：
注入点被换成桥、write 落到 feedback.json、wake 带 page_key 落到日志、上传落在 dir 里、
宿主死了重启/活着复用、端口被占不端别人的页面。
"""
import hashlib
import contextlib
import json
import os
import signal
import sys
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / 'orchestrate'))
sys.path.insert(0, str(SCRIPTS / 'test'))

import test_v5 as fixtures  # noqa: E402
from project_state import REVIEW, read  # noqa: E402
from ppt_pipeline import make_review  # noqa: E402
from review_feedback import consume  # noqa: E402
import review_surface  # noqa: E402
from lib.planners_modules import resolve_module  # noqa: E402
sys.path.insert(0, str(resolve_module('planners-review-core') / 'scripts' / 'lib'))
import review_host  # noqa: E402  （宿主生命周期只有公共模组那一份）


def locate_node():
    # node 的查找也跟着宿主生命周期搬进公共模组了（只有那一份）
    try:
        return review_host.node_binary()
    except ValueError:
        return None

NODE = locate_node()

def http(url, method='GET', body=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode('utf-8') if body is not None else None)
    headers = {'content-type': 'application/json'} if data is not None else {}
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, response.read()

def http_json(url, method='GET', body=None, raw=None):
    status, payload = http(url, method, body, raw)
    return status, json.loads(payload.decode('utf-8'))

@unittest.skipUnless(NODE, 'needs node (the review host is serve-review.mjs)')
@contextlib.contextmanager
def _spy_cli(seen):
    """在传输层的单一出口（`review_host._run`）上观察：这次 `open` 带没带 `--no-open`。

    真调用照旧发生（真起宿主），只把 `open` 补一个 `--no-open` —— 测试要无头，
    但**断言仍然落在实现真正的边界上**（CLI 的参数），不是落在某个 Python 内部件上。
    """
    real = review_host._run

    def spy(command, *args, **kwargs):
        if command != 'open':
            return real(command, *args, **kwargs)
        seen.append(list(args))
        return real(command, *args, '--no-open', **kwargs)

    with mock.patch.object(review_host, '_run', side_effect=spy):
        yield


class ReviewSurfaceTests(unittest.TestCase):
    """用 test_v5 的项目夹具（组合，不继承：继承会把那 28 条用例在本文件里再跑一遍）。"""

    def setUp(self):
        self.project = fixtures.V5Tests()
        self.project.setUp()
        self.root = self.project.root.resolve()
        self.hosts = []
        make_review(self.root)

    def tearDown(self):
        for state in self.hosts:
            review_host.stop_host(state)
        self.project.tearDown()

    def svg(self, key, text='Evidence'):
        return self.project.svg(key, text)

    def seal(self):
        return self.project.seal()

    def payload(self):
        return self.project.payload()

    def start_host(self, port=0):
        state = review_host.start_host(self.root / review_surface.SURFACE_REL, port=port)
        self.hosts.append(state)
        return state

    def entry_file(self):
        return self.root / review_surface.PAGE_REL

    def entry_served(self, state):
        status, body = http(state['url'])
        self.assertEqual(status, 200)
        return body.decode('utf-8')

    # ---- surface ----

    def test_surface_is_written_by_the_generator_and_passes_the_public_validator(self):
        surface = self.root / review_surface.SURFACE_REL
        self.assertTrue(surface.is_file(), '生成审阅页时要一起写 surface')
        doc = json.loads(surface.read_text(encoding='utf-8'))
        self.assertEqual(doc['contract_version'], 'review-surface/2.0.0')
        self.assertEqual(doc['id'], 'planners-ppt-hell/visual')
        self.assertEqual(doc['entry'], '02_visual_review.html')
        self.assertEqual(doc['feedback'], 'feedback.json')
        self.assertEqual(doc['wake']['mode'], 'queue')
        self.assertIn('{unit}', doc['wake']['text'])
        self.assertEqual(doc['capabilities'], ['asset-upload'])
        # 宿主只 stat 它；页面收到戳之后自己去读、自己 diff（相对 surface 文件）
        self.assertEqual(doc['watch'], ['snapshot.json'])
        # dir 只能取项目根：页面在根上，渲染图/上传件/素材分别在 _internal 的几处（见 review_surface 的 docstring）
        self.assertEqual((surface.parent / doc['dir']).resolve(), self.root)
        self.assertTrue(review_surface.validate_surface(self.root), '公共件校验器必须认这份 surface')

    def test_a_surface_pointing_outside_the_project_is_rejected(self):
        surface = self.root / review_surface.SURFACE_REL
        doc = json.loads(surface.read_text(encoding='utf-8'))
        surface.write_text(json.dumps({**doc, 'dir': '../../../../..'}, ensure_ascii=False), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '不合规'):
            review_surface.validate_surface(self.root)
        surface.write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')   # 复原，别影响别的用例
        self.assertEqual(review_surface.validate_surface(self.root), True)

    def test_the_entry_leaves_an_injection_point_and_ships_no_bridge_copy(self):
        text = self.entry_file().read_text(encoding='utf-8')
        self.assertIn('{{REVIEW_BRIDGE}}', text, '入口必须留注入点')
        self.assertEqual(text.count('{{REVIEW_BRIDGE}}'), 1, '注入点只能有一个（宿主 replaceAll，两个就注入两次）')
        # 注入点必须**独立**：宿主把它换成什么由它定（URL 或"base + 内联桥源码"整段）。
        # 塞进 <script src="…"> 的话，整段替换会把标签撑破、桥 404（实测踩过）。
        self.assertNotIn('src="{{REVIEW_BRIDGE}}"', text, '注入点不能塞在 src 属性里')
        self.assertNotIn('review-bridge.js">', text.replace('{{REVIEW_BRIDGE}}', ''), '页面里不能有桥的副本')
        self.assertFalse((self.root / 'review-bridge.js').exists())
        self.assertFalse((self.root / REVIEW / 'review-bridge.js').exists())

    # ---- 宿主 ----

    def test_the_page_paints_itself_without_a_bridge(self):
        """**桥是增强，不是氧气**（与 bypage 的判据同一套，措辞也照抄）。

        公共规则：页面必须能"没有桥也把自己画出来"——渲染**不许**挂在握手、网络或任何外部依赖上；
        握手要有上限；连不上要**在页面上说出来**（只读）；不许在顶层裸用本地存储
        （不透明源 iframe 里读它会直接抛 → 整页脚本当场死、**零报错**）。
        行为上的对照在浏览器冒烟里（connect 永不返回 / 旧写法必须红）。
        """
        import re as _re
        source = (Path(review_surface.__file__).resolve().parent.parent / 'assets/review/review.html').read_text(encoding='utf-8')
        boot = source[source.index('(async function boot(){'):]
        self.assertLess(boot.index('render()'), boot.index('await'),
                        '渲染必须排在第一个 await 之前（桥是增强，不是氧气）')
        self.assertRegex(source, r'BRIDGE_TIMEOUT_MS', '握手必须有超时上限：不落地就按"没有桥"降级继续画')
        self.assertRegex(source, r'connectWithTimeout')
        self.assertIn('只读', source, '连不上宿主时页面要**说出来**（只读），不能零报错地空着')
        for storage in ('localStorage', 'sessionStorage'):
            stripped = _re.sub(r'window\.' + storage, '', source)
            self.assertIsNone(_re.search(r'(^|[^.\w])' + storage + r'\s*[.\[]', stripped),
                              '页面不许裸用 ' + storage + '（不透明源 iframe 里读它会直接抛 → 整页脚本当场死）')

    def test_the_host_serves_the_entry_with_the_bridge_injected(self):
        state = self.start_host()
        page = self.entry_served(state)
        self.assertNotIn('{{REVIEW_BRIDGE}}', page, '宿主 serve 时必须替换注入点')
        self.assertIn('/__review/bridge.js', page)
        # 页面就是磁盘上那一份：**注入点以外**逐字节相同（注入什么由宿主定，所以不比那一小段）
        head, tail = self.entry_file().read_text(encoding='utf-8').split('{{REVIEW_BRIDGE}}', 1)
        self.assertTrue(page.startswith(head) and page.endswith(tail), '注入点以外的字节必须就是磁盘上那一份')
        self.assertGreater(len(page), len(head) + len(tail), '注入点必须真的被换掉了')
        # 桥本体由宿主从公共件里给，不是页面旁边的副本
        status, body = http(state['url'].rsplit('/', 1)[0] + '/__review/bridge.js')
        self.assertEqual(status, 200)
        self.assertIn(b'ReviewBridge', body)
        from lib.planners_modules import module_script
        self.assertEqual(body, module_script('planners-review-core', 'assets/review-bridge.js').read_bytes())

    def test_write_lands_feedback_wake_carries_the_page_key(self):
        state = self.start_host()
        snapshot = read(self.root / REVIEW / 'snapshot.json')
        document = {'review_id': snapshot['review_id'], 'pages': {k: {'decision': 'approved', 'feedback': '', 'annotations': [], 'assets': []} for k in snapshot['versions']},
                    'overall_feedback': '', 'items': [],
                    'provenance': {'source': 'review_page', 'transport': 'http', 'submitted_at': '2026-09-26T00:00:00.000Z'}}
        document['pages']['alpha'] = {'decision': 'revise', 'feedback': '标题压到了图', 'annotations': [{'x': .1, 'y': .1, 'w': .2, 'h': .2, 'text': '这块留白'}], 'assets': []}
        base = state['url'].rsplit('/', 1)[0]
        status, result = http_json(base + '/__review/write', 'POST', document)
        self.assertEqual(status, 200)
        self.assertTrue(result['ok'])
        written = read(self.root / REVIEW / 'feedback.json')
        self.assertEqual(written['pages']['alpha']['feedback'], '标题压到了图')
        # Skill 侧收件：规范化 + 留档，条目 id 由「哪一页 + 哪一轮」定出来
        intake = consume(self.root)
        self.assertFalse(intake['stale'])
        self.assertEqual([i['pages'] for i in intake['document']['items']], [['alpha']])
        self.assertTrue(intake['archived'].endswith('round-01.json'))
        # wake：宿主没有 Agent 可唤，落日志（人回对话说一声），文案来自 surface 且 {unit} 被替换
        status, result = http_json(base + '/__review/wake', 'POST', {'unit': 'alpha'})
        self.assertEqual(status, 200)
        self.assertFalse(result['woke'])
        lines = [json.loads(line) for line in (self.root / review_surface.WAKE_LOG_REL).read_text(encoding='utf-8').splitlines()]
        self.assertEqual(lines[-1]['unit'], 'alpha')
        self.assertIn('alpha 已定', lines[-1]['text'])
        self.assertIn('只重出这一页', lines[-1]['text'])

    def test_upload_lands_inside_dir_and_an_escape_is_refused(self):
        state = self.start_host()
        base = state['url'].rsplit('/', 1)[0]
        relative = REVIEW + '/uploads/alpha/new-1.png'
        status, result = http_json(base + '/__review/upload?rel=' + urllib.parse.quote(relative), 'POST', raw=b'\x89PNG\r\n\x1a\nfake')
        self.assertEqual(status, 200)
        self.assertTrue(result['ok'])
        self.assertTrue((self.root / relative).is_file())
        self.assertEqual(result['sha256'], hashlib.sha256(b'\x89PNG\r\n\x1a\nfake').hexdigest())
        with self.assertRaises(urllib.error.HTTPError) as caught:
            http(base + '/__review/upload?rel=' + urllib.parse.quote('../outside.png'), 'POST', raw=b'x')
        self.assertEqual(caught.exception.code, 403)
        self.assertFalse((self.root.parent / 'outside.png').exists())

    def test_a_live_host_is_reused_and_a_dead_one_is_restarted(self):
        first = self.start_host()
        self.assertIsNotNone(review_host.host_alive(self.root / review_surface.SURFACE_REL), '活着的宿主必须认出来')
        self.assertEqual(review_surface.open_review(self.root, open_browser=False)['reused'], True)
        os.kill(int(first['pid']), signal.SIGTERM)
        for _ in range(50):
            if not review_host._pid_alive(first['pid']): break
            time.sleep(.1)
        # 元数据还留在盘上：只看它就会以为宿主还在（P-20(d) 的现场）；判据是读回页面
        self.assertTrue((self.root / review_surface.HOST_STATE_REL).is_file())
        self.assertIsNone(review_host.host_alive(self.root / review_surface.SURFACE_REL))
        again = review_surface.open_review(self.root, open_browser=False)
        self.hosts.append(again)
        self.assertTrue(again['started'])
        self.assertFalse(again['reused'])
        self.assertNotEqual(again['pid'], first['pid'])
        self.assertEqual(http(again['url'])[0], 200)

    def test_the_review_command_starts_the_surface_host_and_reuses_it(self):
        """CLI 那条路（`ppt_pipeline review`）真的接上了新宿主：起来一次、第二次复用同一个 URL。"""
        from unittest import mock
        from ppt_pipeline import review_open
        opened = []
        # 开浏览器这件事现在只有一套行为，在 CLI 里。所以断言落在**CLI 边界**上：
        # 作者那两次调用里都不许带 `--no-open`（＝都要求开）；同时给真调用补上 `--no-open`，
        # 免得测试真去拉一个浏览器起来。
        with _spy_cli(opened):
            first = review_open(self.root)
            self.hosts.append(first)
            self.assertTrue(first['started'])
            self.assertFalse(first['reused'])
            self.assertEqual(first['surface'], str(self.root / review_surface.SURFACE_REL))
            self.assertTrue(first['feedback_path'].endswith('_internal/05_review/feedback.json'))
            second = review_open(self.root)
            self.assertFalse(second['started'])
            self.assertTrue(second['reused'])
            self.assertEqual(second['url'], first['url'])
        self.assertEqual(len(opened), 2, '两次都替作者把页面打开')
        for one in opened:
            self.assertNotIn('--no-open', one, '作者那两次是"要开"的')

    def test_surface_only_prepares_everything_and_starts_nothing(self):
        """宿主有 `review_open` 工具时走这条：只生成页面 + 写 surface + 校验，**不起宿主、不开浏览器**。

        "没有东西在监听端口"在这条路上是构造性的：一个宿主进程都没被起过（`start_host` 未被调用、
        没写 host state / 日志、`host_alive` 为 None），所以没有端口被占。
        """
        from unittest import mock
        from ppt_pipeline import review_open
        opened = []
        # 生命周期搬进 Node 之后，Python 侧不再持有宿主进程句柄（也就没有 _SPAWNED_HOSTS）——
        # 断言换成**传输层的调用痕迹**：这一趟里一次 `start` 都不许发生。
        starts_before = [one for one in review_host._INVOCATIONS if one and one[0] == 'start']
        with mock.patch('review_host.start_host', side_effect=AssertionError('带开关时不许起宿主')) as starter, \
             _spy_cli(opened):
            result = review_open(self.root, surface_only=True)
        self.assertFalse(starter.called, '带开关时不许起宿主')
        self.assertEqual(opened, [], '带开关时不许开浏览器')
        self.assertEqual([one for one in review_host._INVOCATIONS if one and one[0] == 'start'],
                         starts_before, '带开关时不许起宿主（一次 start 调用都不许有）')
        self.assertFalse((self.root / review_surface.HOST_STATE_REL).exists(), '不许写宿主状态文件')
        self.assertFalse((self.root / review_surface.REVIEW / 'review_host.log').exists(), '不许起宿主日志')
        self.assertIsNone(review_host.host_alive(self.root / review_surface.SURFACE_REL))
        self.assertFalse(result.get('host_started'))
        surface = Path(result['surface'])
        self.assertTrue(surface.is_absolute(), '报出来的必须是绝对路径（宿主拿它去挂）')
        self.assertTrue(surface.is_file())
        self.assertEqual(surface, (self.root / review_surface.SURFACE_REL).resolve())
        self.assertTrue(Path(result['entry']).is_file(), '页面也要生成')
        self.assertTrue(result['feedback_path'].endswith('_internal/05_review/feedback.json'))
        self.assertEqual(review_surface.validate_surface(self.root), True, 'surface 必须合规')

    def test_a_busy_port_fails_loudly_instead_of_serving_someone_elses_page(self):
        import socket
        blocker = socket.socket(); blocker.bind(('127.0.0.1', 0)); blocker.listen(1)
        taken = blocker.getsockname()[1]
        try:
            with self.assertRaisesRegex(ValueError, '启动失败'):
                review_host.start_host(self.root / review_surface.SURFACE_REL, port=taken)
        finally:
            blocker.close()

    def test_host_alive_refuses_a_page_that_is_not_ours(self):
        """端口可能是别人的（或上一个会话留下的）：只有**内容**能证明它端的是我们的页面。

        宿主按请求读盘，所以「磁盘上的入口换了一版」不算异常（页面本来就该被重出）——
        被拒的是「这个 URL 端出来的字节不是我们这个 dir 里的入口」。
        """
        import http.server
        import threading
        state = self.start_host()
        self.assertIsNotNone(review_host.host_alive(self.root / review_surface.SURFACE_REL, state))
        self.entry_file().write_text(self.entry_file().read_text(encoding='utf-8').replace('整套审阅', '重出过的一版'), encoding='utf-8')
        self.assertIsNotNone(review_host.host_alive(self.root / review_surface.SURFACE_REL, state), '页面被重出（同一份文件的新版本）仍是它')

        class Foreign(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = b'<!doctype html><html><body>\xe5\x88\xab\xe4\xba\xba\xe7\x9a\x84\xe9\xa1\xb5\xe9\x9d\xa2</body></html>'
                self.send_response(200); self.send_header('content-type', 'text/html; charset=utf-8')
                self.send_header('content-length', str(len(body))); self.end_headers(); self.wfile.write(body)
            def log_message(self, *args): pass

        foreign = http.server.HTTPServer(('127.0.0.1', 0), Foreign)
        threading.Thread(target=foreign.serve_forever, daemon=True).start()
        try:
            stolen = {**state, 'url': f'http://127.0.0.1:{foreign.server_port}/02_visual_review.html'}
            self.assertIsNone(review_host.host_alive(self.root / review_surface.SURFACE_REL, stolen), '端的是别人的页面就不认')
        finally:
            foreign.shutdown(); foreign.server_close()

    def test_a_missing_node_is_reported_not_guessed(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {'PATH': '', 'REVIEW_CORE_NODE': ''}):
            with mock.patch('review_host.Path.exists', return_value=False):
                with self.assertRaisesRegex(ValueError, 'node'):
                    review_host.node_binary()

if __name__ == '__main__':
    unittest.main()
