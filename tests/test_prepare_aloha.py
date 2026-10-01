"""Preparation rejects incompatible assets before writing or loading tensor libraries."""

import json
from pathlib import Path
import tempfile
import unittest

from robot_agent.prepare_aloha import migrate, source_config


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / 'original'
        self.source.mkdir()
        self.config = {
            'type': 'act', 'chunk_size': 100, 'n_action_steps': 100,
            'n_obs_steps': 1, 'use_amp': False, 'temporal_ensemble_coeff': None,
            'input_features': {
                'observation.images.top': {'type': 'VISUAL', 'shape': [3, 480, 640]},
                'observation.state': {'type': 'STATE', 'shape': [14]}},
            'output_features': {'action': {'type': 'ACTION', 'shape': [14]}},
            'device': 'cuda', 'pretrained_backbone_weights': 'IMAGENET1K_V1'}
        self.save_config()
        (self.source / 'model.safetensors').write_bytes(b'fixture; not real tensors')

    def save_config(self):
        (self.source / 'config.json').write_text(json.dumps(self.config))

    def test_local_overrides_preserve_original(self):
        before = (self.source / 'config.json').read_text()
        result = source_config(self.source)
        self.assertEqual(result['device'], 'cpu')
        self.assertIsNone(result['pretrained_backbone_weights'])
        self.assertEqual((self.source / 'config.json').read_text(), before)

    def test_incompatible_configuration_does_not_create_destination(self):
        self.config['chunk_size'] = 50
        self.save_config()
        target = self.root / 'migration'
        with self.assertRaisesRegex(ValueError, 'unsupported ACT configuration'):
            migrate(self.source, target)
        self.assertFalse(target.exists())

    def test_missing_tensors_does_not_create_destination(self):
        (self.source / 'model.safetensors').unlink()
        target = self.root / 'migration'
        with self.assertRaisesRegex(ValueError, 'tensors missing'):
            migrate(self.source, target)
        self.assertFalse(target.exists())

    def test_wrong_camera_mapping_is_rejected(self):
        self.config['input_features']['observation.images.top']['shape'] = [3, 240, 320]
        self.save_config()
        with self.assertRaisesRegex(ValueError, 'feature mapping'):
            source_config(self.source)

    def test_existing_destination_is_preserved(self):
        target = self.root / 'migration'
        target.mkdir()
        sentinel = target / 'operator-data'
        sentinel.write_text('keep')
        with self.assertRaises(FileExistsError):
            migrate(self.source, target)
        self.assertEqual(list(target.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_text(), 'keep')


if __name__ == '__main__':
    unittest.main()
