"""人手动改过的页，不许被整页重写静默覆盖。

背景（2026-10-05 真人实测）：审阅页上的轻量直改（改字、移位、删除）会确定性写回
`.svg` —— 这一步是对的。但同一页还有第二个写手：模型自己的生成脚本，脚本一跑就是
**整份 SVG 重写**，人那一笔不在脚本里，于是静默消失，人白改一场。

所以这条链要能被证伪：人改完 → 模型重画 → **必须有人交代过**，否则 `/check` 报 fix、
`/export` 拦下、`/next` 在入口就说出来。交代走 `ack-human-edit`。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'orchestrate'))

from canvas_frame import FRAME_H_INT, FRAME_VIEWBOX, FRAME_W_INT
from project_state import (CONTENT, PNG, REVIEW, SVG, VALIDATION, digest, page_version,
                           read, sha, sync, versions, write)
from ppt_pipeline import human_edit_problems, layout_check, make_review, next_action
from review_feedback import (APPLIED_EDITS_FILE, ack_human_edit, consume, human_edit_state,
                             human_edits)

S = Path(__file__).resolve().parents[1]
PAGE = 'alpha'


class HumanEditGuardTests(unittest.TestCase):
    """合成项目：两页、已渲染已检视，然后走真实的「页面写反馈 → consume 收件」接缝。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'project'
        src = Path(self.tmp.name) / 'source.md'
        src.write_text('# Demo\nEvidence 42% with qualification.\n')
        subprocess.run([sys.executable, str(S / 'init_svg_project.py'), str(self.root),
                        '--source', str(src)], check=True, capture_output=True)
        write(self.root / CONTENT, {'project': 'Test', 'pages': [
            {'page_key': k, 'title': k, 'content': '42% with qualification', 'source_assets': []}
            for k in ['alpha', 'omega']]})
        sync(self.root)
        for k in ['alpha', 'omega']:
            self.svg(k)
        self.seal()

    def tearDown(self):
        self.tmp.cleanup()

    # —— fixture ——
    def svg(self, key, text='Evidence'):
        (self.root / SVG / (key + '.svg')).write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{FRAME_W_INT}" height="{FRAME_H_INT}"'
            f' viewBox="{FRAME_VIEWBOX}"><rect width="{FRAME_W_INT}" height="{FRAME_H_INT}" fill="#FFFFFF"/>'
            f'<text x="120" y="180" font-size="48" font-family="Arial" fill="#111111">{text}</text></svg>',
            encoding='utf-8')

    def seal(self):
        ins = {}
        for key, version in versions(self.root).items():
            png = self.root / PNG / (key + '.png')
            png.parent.mkdir(parents=True, exist_ok=True)
            Image.new('RGB', (192, 108), 'white').save(png)
            rec = {'version': version, 'errors': 0, 'png_sha256': sha(png), 'validator': {}}
            write(self.root / VALIDATION / (key + '.json'), rec)
            ins[key] = {'render_token': digest(rec), 'note': 'Synthetic test fixture',
                        'first_glance': 'fixture focal element', 'design_check': 'fixture rule check',
                        'position': 'x=120,y=150,w=400,h=80', 'verdict': 'clean', 'must_fix': False}
        write(self.root / VALIDATION / 'inspections.json', ins)

    def submit_human_edit(self, edits):
        """人点一下审阅页：页面写整份状态，Skill 侧 `consume` 把直改写回 SVG。"""
        snap = make_review(self.root)
        pages = {k: {'decision': 'pending', 'feedback': '', 'annotations': [], 'assets': []}
                 for k in snap['versions']}
        pages[PAGE]['decision'] = 'revise'
        pages[PAGE]['svg_edits'] = edits
        pages[PAGE]['feedback'] = '顺手改了一处'
        document = {'review_id': snap['review_id'], 'pages': pages, 'overall_feedback': '',
                    'provenance': {'source': 'review_page', 'transport': 'http',
                                   'submitted_at': datetime.now(timezone.utc).isoformat()}}
        write(self.root / REVIEW / 'feedback.json', document)
        result = consume(self.root)
        self.assertIn(PAGE, result['svg_edits_applied'])
        return result

    def page_version(self, key=PAGE):
        from project_state import content
        page = next(p for p in content(self.root)['pages'] if p['page_key'] == key)
        return page_version(self.root, page)

    def current_svg(self, key=PAGE):
        return (self.root / SVG / (key + '.svg')).read_text(encoding='utf-8')

    # —— 用例 ——
    def test_edit_lands_in_svg_and_is_recorded_with_its_content(self):
        self.submit_human_edit([{'review_id': '0.1', 'tag': 'text', 'text': '人改过的字'}])
        self.assertIn('人改过的字', self.current_svg())

        ledger = read(self.root / REVIEW / APPLIED_EDITS_FILE, {})
        record = next(iter(ledger.values()))
        # 逐笔内容必须存下来 —— 只存 hash 的话，连「人改了什么」都查不回来。
        self.assertEqual([e['review_id'] for e in record['edits']], ['0.1'])
        self.assertEqual(record['edits'][0]['text'], '人改过的字')
        self.assertEqual(record['edits'][0]['tag'], 'text')
        # 人改完那一版 SVG 要留档，模型重画后可还原。
        snapshot = self.root / record['svg_snapshot']
        self.assertTrue(snapshot.is_file(), '人改完那版 SVG 应有快照')
        self.assertIn('人改过的字', snapshot.read_text(encoding='utf-8'))
        # 快照必须和 PNG 快照住在同一个 versions/ 下。
        # 只断言「记录的路径能打开」是不够的：写盘与记账用同一个错路径时，两边一起错，
        # 断言照样通过 —— 双层前缀（`_internal/05_review/_internal/05_review/versions/`）
        # 就是这样躲过上一版测试、并在真项目里复现两次的。
        self.assertEqual(Path(record['svg_snapshot']).parent, Path(REVIEW) / 'versions',
                         '人改底本的快照要落在 _internal/05_review/versions/')

        state = human_edit_state(self.root, PAGE, self.page_version())
        self.assertTrue(state['carried'])
        self.assertEqual(human_edit_problems(self.root, [PAGE]), [])

    def test_regenerating_a_human_edited_page_is_caught(self):
        self.submit_human_edit([{'review_id': '0.1', 'tag': 'text', 'text': '人改过的字'}])
        # 模型整份重画这一页：人的那一笔不在脚本里。
        self.svg(PAGE, text='模型重画')

        state = human_edit_state(self.root, PAGE, self.page_version())
        self.assertFalse(state['carried'])
        self.assertFalse(state['acknowledged'])

        problems = human_edit_problems(self.root, [PAGE])
        self.assertEqual(len(problems), 1)
        self.assertIn(PAGE, problems[0]['error'])
        self.assertIn('ack-human-edit', problems[0]['error'])
        # 导出这条路也要拦：转换 PPT 之前就断。
        self.assertTrue(any(p.get('page') == PAGE for p in layout_check(self.root, [PAGE])))
        # 入口也要说：模型不该靠自己去翻账本才发现。
        self.assertEqual([x['page'] for x in next_action(self.root)['human_edits_lost']], [PAGE])

    def test_acknowledging_clears_it_and_empty_notes_do_not(self):
        self.submit_human_edit([{'review_id': '0.1', 'tag': 'text', 'text': '人改过的字'}])
        self.svg(PAGE, text='模型重画')

        with self.assertRaisesRegex(ValueError, '空话'):
            ack_human_edit(self.root, PAGE, '   ')

        ack_human_edit(self.root, PAGE, '人那笔改字已按原意带进新版标题')
        self.assertTrue(human_edit_state(self.root, PAGE, self.page_version())['acknowledged'])
        self.assertEqual(human_edit_problems(self.root, [PAGE]), [])

    def test_ack_is_per_version_so_a_later_rewrite_re_arms_the_guard(self):
        self.submit_human_edit([{'review_id': '0.1', 'tag': 'text', 'text': '人改过的字'}])
        self.svg(PAGE, text='第一版重画')
        ack_human_edit(self.root, PAGE, '已带进新版')
        self.assertEqual(human_edit_problems(self.root, [PAGE]), [])

        # 再画一次 —— 上一次的交代只对上一版有效，不能当永久免死金牌。
        self.svg(PAGE, text='第二次重画')
        self.assertEqual(len(human_edit_problems(self.root, [PAGE])), 1)

    def test_a_page_nobody_touched_is_never_flagged(self):
        self.submit_human_edit([{'review_id': '0.1', 'tag': 'text', 'text': '人改过的字'}])
        self.svg('omega', text='另一页怎么改都行')
        self.assertEqual(human_edit_problems(self.root, ['omega']), [])
        self.assertNotIn('omega', human_edits(self.root))
        self.assertIsNone(human_edit_state(self.root, 'omega', self.page_version('omega')))


if __name__ == '__main__':
    unittest.main()
