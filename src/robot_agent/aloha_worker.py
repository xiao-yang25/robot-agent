"""Pinned ACT candidate worker: receives observations, never owns an environment."""

import os
import socket
import sys
import time

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN'] = '1'
os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '0'

from robot_harness._transport import Channel, integer


def main():
    channel = Channel(socket.socket(fileno=int(sys.argv[1])), binary=True)
    try:
        import numpy as np
        import torch
        from lerobot.policies.act.configuration_act import ACTConfig
        from lerobot.policies.act.modeling_act import ACTPolicy
        from lerobot.policies.factory import make_pre_post_processors
        checkpoint, device = sys.argv[2:4]
        if device not in ('mps', 'cpu') or (device == 'mps' and not torch.backends.mps.is_available()):
            raise RuntimeError('requested device unavailable; no fallback')
        torch.set_num_threads(4)
        torch.manual_seed(0)
        cfg = ACTConfig.from_pretrained(checkpoint)
        cfg.device = device
        if cfg.chunk_size != 100 or cfg.n_action_steps != 100 or cfg.use_amp or cfg.temporal_ensemble_coeff is not None:
            raise ValueError('unqualified ACT configuration')
        policy = ACTPolicy.from_pretrained(checkpoint, config=cfg, strict=True).eval()
        pre, post = make_pre_post_processors(policy_cfg=cfg, pretrained_path=checkpoint,
            preprocessor_overrides={'device_processor': {'device': device}})
        episode = None
        channel.queue({'kind': 'ready'})
        while True:
            for message in channel.pump():
                if message.get('kind') == 'close':
                    return
                if message.get('kind') != 'predict':
                    raise ValueError('unexpected request')
                count = integer(message.get('count'), 'count', 1, 100)
                observation = message['observation']
                if observation['image'] != {'shape': [480, 640, 3], 'dtype': 'uint8', 'camera': 'top'}:
                    raise ValueError('invalid image description')
                frame = np.frombuffer(message['_payload'], dtype=np.uint8).reshape(480, 640, 3)
                joints = np.asarray(observation['joints'], dtype=np.float32)
                if joints.shape != (14,) or not np.isfinite(joints).all():
                    raise ValueError('invalid joints')
                identity = message['identity']
                key = (identity['session'], observation['epoch'])
                if key != episode:
                    policy.reset()
                    episode = key
                with torch.inference_mode():
                    batch = pre({'observation.images.top': torch.from_numpy(frame.copy()).permute(2, 0, 1).float() / 255.,
                                 'observation.state': torch.from_numpy(joints.copy())})
                    actions = post(policy.predict_action_chunk(batch)).squeeze(0).cpu().numpy()
                if actions.shape != (100, 14) or not np.isfinite(actions).all():
                    raise ValueError('invalid model output')
                channel.queue({'kind': 'prediction', 'identity': identity,
                               'actions': actions[:count].tolist()})
            time.sleep(0.002)
    except (EOFError, BrokenPipeError, ConnectionResetError):
        pass
    finally:
        channel.close()


if __name__ == '__main__':
    main()
