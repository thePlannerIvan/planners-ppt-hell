import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from import_bypage import import_bypage, feedback_source_hash


class BypageImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.project = self.root / 'project'
        upstream = {}
        for name in ('copy', 'memory', 'source_index', 'audit', 'feedback', 'asset_manifest',
                     'deliverable', 'delivered_asset_manifest'):
            path = self.root / f'{name}.md'
            data = name.encode()
            path.write_bytes(data)
            upstream[name] = {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest()}
        audit = {'artifact': upstream['copy'], 'source_index': {'path': upstream['source_index']['path']}}
        self.bind(upstream['audit'], json.dumps(audit).encode())
        feedback_hash = feedback_source_hash(Path(upstream['copy']['path']).read_bytes(),
                                              Path(upstream['audit']['path']).read_bytes(),
                                              Path(upstream['asset_manifest']['path']).read_bytes())
        self.bind(upstream['feedback'], json.dumps({'overall_decision': 'approve', 'source_sha256': feedback_hash}).encode())
        asset_path = self.root / 'image.png'
        asset_path.write_bytes(b'pinned image')
        self.asset = {'path': str(asset_path), 'sha256': hashlib.sha256(asset_path.read_bytes()).hexdigest(),
                      'asset_id': 'original-photo', 'source_id': 'src-1', 'reference': 'assets/image.png'}
        self.payload = {'version': 'bypage-production/1', 'route': 'slides', 'upstream': upstream,
                        'order': ['stable-page'], 'pages': [{
                            'page_key': 'stable-page', 'page_number': 7, 'identity': {'kind': 'explicit', 'value': 'stable-page'},
                            'title': 'Page title', 'content': 'Body\n![Photo](assets/image.png)', 'notes': 'Speak this',
                            'production_notes': 'Use `assets/image.png`', 'sources': 'src-1', 'assets': [self.asset]}],
                        'provenance': {'kind': 'upstream-baseline', 'audit_scope': 'original-bypage-copy', 'reverse_sync': False}}
        self.production = self.root / 'production.json'

    def bind(self, record, data):
        Path(record['path']).write_bytes(data)
        record['sha256'] = hashlib.sha256(data).hexdigest()

    def run_import(self):
        self.production.write_text(json.dumps(self.payload))
        return import_bypage(self.production, self.project)

    def test_program_import_preserves_upstream_ids_and_content(self):
        self.run_import()
        content = json.loads((self.project / '_internal/01_content/page_content.json').read_text())
        page = content['pages'][0]
        self.assertEqual(page['page_key'], 'stable-page')
        self.assertEqual(page['bypage_page_number'], 7)
        self.assertEqual(page['notes'], 'Speak this')
        self.assertEqual(page['source_assets'], ['original-photo'])
        self.assertIn('_internal/00_project/source/assets/', page['content'])
        self.assertIn('_internal/00_project/source/assets/', page['production_notes'])
        assets = json.loads((self.project / '_internal/00_project/source/source_assets.json').read_text())
        self.assertEqual(assets['assets'][0]['asset_id'], 'original-photo')
        self.assertEqual((self.project / assets['assets'][0]['normalized_path']).read_bytes(), b'pinned image')
        manifest = json.loads((self.project / '_internal/00_project/page_manifest.json').read_text())
        self.assertEqual(manifest['input_binding']['upstream']['audit'], self.payload['upstream']['audit'])
        self.assertEqual(manifest['input_binding']['provenance']['audit_scope'], 'original-bypage-copy')

    def test_existing_project_never_overwritten(self):
        self.project.mkdir()
        sentinel = self.project / 'user-edited.svg'
        sentinel.write_text('user edit')
        with self.assertRaisesRegex(ValueError, 'empty project'):
            self.run_import()
        self.assertEqual(sentinel.read_text(), 'user edit')

    def test_mutated_upstream_and_assets_rejected_without_project(self):
        Path(self.asset['path']).write_bytes(b'mutated')
        with self.assertRaisesRegex(ValueError, 'binding changed'):
            self.run_import()
        self.assertFalse(self.project.exists())

    def test_missing_memory_and_duplicate_page_identity_rejected(self):
        memory = self.payload['upstream'].pop('memory')
        with self.assertRaisesRegex(ValueError, 'memory'):
            self.run_import()
        self.payload['upstream']['memory'] = memory
        self.payload['pages'].append(self.payload['pages'][0].copy())
        self.payload['order'].append('stable-page')
        with self.assertRaisesRegex(ValueError, 'identities'):
            self.run_import()

    def test_wrong_audit_baseline_rejected(self):
        record = self.payload['upstream']['audit']
        self.bind(record, json.dumps({'artifact': {'path': record['path'], 'sha256': record['sha256']},
                                     'source_index': {'path': self.payload['upstream']['source_index']['path']}}).encode())
        with self.assertRaisesRegex(ValueError, 'original Bypage baseline'):
            self.run_import()

    def test_copy_audit_only_feedback_cannot_approve_structured_assets(self):
        upstream = self.payload['upstream']
        legacy_hash = hashlib.sha256(Path(upstream['copy']['path']).read_bytes() + b'\n---FACT-AUDIT---\n' +
                                     Path(upstream['audit']['path']).read_bytes()).hexdigest()
        self.bind(upstream['feedback'], json.dumps({'overall_decision': 'approve', 'source_sha256': legacy_hash}).encode())
        with self.assertRaisesRegex(ValueError, 'asset manifest'):
            self.run_import()
        self.assertFalse(self.project.exists())

    def test_rebound_manifest_with_old_feedback_is_rejected(self):
        self.bind(self.payload['upstream']['asset_manifest'], b'changed asset manifest')
        with self.assertRaisesRegex(ValueError, 'asset manifest'):
            self.run_import()
        self.assertFalse(self.project.exists())

    def test_same_asset_id_with_different_page_variants_is_rejected(self):
        variant = {**self.asset, 'path': str(self.root / 'processed.png'),
                   'reference': 'assets/processed.png'}
        self.bind(variant, b'processed variant')
        page = {**self.payload['pages'][0], 'page_key': 'second-page', 'page_number': 8,
                'identity': {'kind': 'explicit', 'value': 'second-page'},
                'content': '![Variant](assets/processed.png)', 'assets': [variant]}
        self.payload['pages'].append(page)
        self.payload['order'].append('second-page')
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                if reverse:
                    self.payload['pages'].reverse()
                    self.payload['order'].reverse()
                with self.assertRaisesRegex(ValueError, 'Ambiguous upstream asset identity original-photo'):
                    self.run_import()
                self.assertFalse(self.project.exists())
                self.assertEqual(list(self.root.glob('.project.bypage-*')), [])
                self.assertEqual(Path(self.asset['path']).read_bytes(), b'pinned image')
                self.assertEqual(Path(variant['path']).read_bytes(), b'processed variant')

    def test_same_page_variants_are_rejected_in_either_order(self):
        variant = {**self.asset, 'path': str(self.root / 'processed.png'),
                   'reference': 'assets/processed.png'}
        self.bind(variant, b'processed variant')
        page = self.payload['pages'][0]
        page['content'] += '\n![Variant](assets/processed.png)'
        for assets in ([self.asset, variant], [variant, self.asset]):
            with self.subTest(first_reference=assets[0]['reference']):
                page['assets'] = assets
                with self.assertRaisesRegex(ValueError, 'Ambiguous upstream asset identity original-photo'):
                    self.run_import()
                self.assertFalse(self.project.exists())
                self.assertEqual(list(self.root.glob('.project.bypage-*')), [])

    def test_ambiguous_variants_preserve_existing_empty_target(self):
        self.project.mkdir()
        variant = {**self.asset, 'path': str(self.root / 'processed.png'),
                   'reference': 'assets/processed.png'}
        self.bind(variant, b'processed variant')
        self.payload['pages'][0]['assets'].append(variant)
        with self.assertRaisesRegex(ValueError, 'Ambiguous upstream asset identity original-photo'):
            self.run_import()
        self.assertTrue(self.project.is_dir())
        self.assertEqual(list(self.project.iterdir()), [])
        self.assertEqual(list(self.root.glob('.project.bypage-*')), [])

    def test_same_asset_id_and_bytes_shared_across_pages(self):
        page = {**self.payload['pages'][0], 'page_key': 'second-page', 'page_number': 8,
                'identity': {'kind': 'explicit', 'value': 'second-page'}}
        self.payload['pages'].append(page)
        self.payload['order'].append('second-page')
        self.run_import()
        assets = json.loads((self.project / '_internal/00_project/source/source_assets.json').read_text())
        content = json.loads((self.project / '_internal/01_content/page_content.json').read_text())
        self.assertEqual(len(assets['assets']), 1)
        self.assertEqual([page['source_assets'] for page in content['pages']],
                         [['original-photo'], ['original-photo']])
        self.assertTrue(all(assets['assets'][0]['normalized_path'] in page['content']
                            for page in content['pages']))
        pinned = (self.project / assets['assets'][0]['normalized_path']).read_bytes()
        self.assertEqual(pinned, b'pinned image')
        self.assertEqual(hashlib.sha256(pinned).hexdigest(), self.asset['sha256'])

    def test_file_binding_rejects_invalid_hash_before_reading(self):
        binding = self.payload['upstream']['memory']
        binding['path'] = str(self.root / 'missing.md')
        binding['sha256'] = 'not-a-sha256'
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            self.run_import()
        self.assertFalse(self.project.exists())

    def test_lexical_and_resolved_environment_aliases_are_rejected(self):
        alias = self.root / '.env-alias'
        alias.symlink_to(self.production)
        self.production.write_text(json.dumps(self.payload))
        with self.assertRaisesRegex(ValueError, 'Environment files'):
            import_bypage(alias, self.project)
        target = self.root / '.env-fixture'
        target.write_bytes(b'synthetic secret; do not read')
        alias = self.root / 'alias.md'
        alias.symlink_to(target)
        self.payload['upstream']['memory']['path'] = str(alias)
        with self.assertRaisesRegex(ValueError, 'Environment files'):
            self.run_import()
        self.assertFalse(self.project.exists())


if __name__ == '__main__':
    unittest.main()
