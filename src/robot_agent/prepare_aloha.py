"""Explicit public download or offline local migration; never uploads or overwrites."""

import argparse
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

REPOSITORY = 'lerobot/act_aloha_sim_transfer_cube_human'
REVISION = 'ba73b2766f1371cdc133ca4efb97eb090d744625'
FILES = ('config.json', 'train_config.json', 'model.safetensors', 'README.md')


def source_config(source):
    config = json.loads((source / 'config.json').read_text())
    expected = {'type': 'act', 'chunk_size': 100, 'n_action_steps': 100,
                'n_obs_steps': 1, 'use_amp': False, 'temporal_ensemble_coeff': None}
    if any(config.get(key) != value for key, value in expected.items()):
        raise ValueError('unsupported ACT configuration')
    if config.get('input_features') != {
            'observation.images.top': {'type': 'VISUAL', 'shape': [3, 480, 640]},
            'observation.state': {'type': 'STATE', 'shape': [14]}} or config.get('output_features') != {
                'action': {'type': 'ACTION', 'shape': [14]}}:
        raise ValueError('unsupported ACT feature mapping')
    if not (source / 'model.safetensors').is_file():
        raise ValueError('original model tensors missing')
    return {**config, 'device': 'cpu', 'pretrained_backbone_weights': None}


def download(output):
    os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN'] = '1'
    from huggingface_hub import snapshot_download
    output.mkdir(parents=True, exist_ok=False)
    snapshot_download(repo_id=REPOSITORY, revision=REVISION, allow_patterns=list(FILES),
                      local_dir=output, token=False)
    print(f'Original assets saved to {output}; migration is a separate command.')


def migrate(source, output):
    # Validate and reserve a fresh destination before loading large tensor libraries.
    config = source_config(source)
    output.mkdir(parents=True, exist_ok=False)
    stage, checkpoint = output / 'migration-input', output / 'checkpoint'
    stage.mkdir()
    (stage / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
    (stage / 'model.safetensors').symlink_to(source / 'model.safetensors')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN'] = '1'
    import torch
    from huggingface_hub import ModelCard
    from lerobot.processor import migrate_policy_normalization
    from lerobot.processor.migrate_policy_normalization import (
        extract_normalization_stats, remove_normalization_layers)
    from safetensors.torch import load_file
    # Upstream card validation uses a remote Hub request even for local migration.
    # Disable only that publishing-metadata request, preserving tensor conversion.
    with patch.object(sys, 'argv', ['migrate_policy_normalization', '--pretrained-path',
                                  str(stage), '--output-dir', str(checkpoint)]), \
            patch.object(ModelCard, 'validate', return_value=None):
        migrate_policy_normalization.main()
    tensors = load_file(str(source / 'model.safetensors'))
    expected = remove_normalization_layers(tensors)
    actual = load_file(str(checkpoint / 'model.safetensors'))
    if set(expected) != set(actual) or any(not torch.equal(expected[k], actual[k]) for k in expected):
        raise ValueError('migration changed learned tensor keys or values')
    stats = extract_normalization_stats(tensors)
    if set(stats) != {'observation.images.top', 'observation.state', 'action'}:
        raise ValueError('unsupported normalization features')
    for feature, values in stats.items():
        for kind in ('mean', 'std'):
            if kind not in values or not torch.isfinite(values[kind]).all():
                raise ValueError(f'invalid normalization measurement: {feature}/{kind}')
        if not (values['std'] >= 0).all():
            raise ValueError('negative normalization deviation')
    report = {'status': 'passed', 'learned_tensors_equal': True,
              'learned_tensor_count': len(actual), 'normalization_features': sorted(stats),
              'source': str(source), 'checkpoint': str(checkpoint), 'uploaded': False,
              'config_overrides': {'device': 'cpu', 'pretrained_backbone_weights': None},
              'model_card_remote_validation': 'disabled for local offline migration'}
    (output / 'migration-check.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    get = commands.add_parser('download')
    get.add_argument('--output', type=Path, required=True)
    convert = commands.add_parser('migrate')
    convert.add_argument('--source', type=Path, required=True)
    convert.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'download':
        download(args.output.resolve())
    else:
        migrate(args.source.resolve(), args.output.resolve())


if __name__ == '__main__':
    main()
