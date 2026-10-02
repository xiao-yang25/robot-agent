"""CI-only camera/action sink. No dynamics, contacts, reward or robot claim."""
from types import SimpleNamespace
import numpy as np


class Environment:
    def __init__(self):
        self.unwrapped = self
        self._env = self
        self.physics = SimpleNamespace(
            data=SimpleNamespace(time=0., qpos=np.zeros(14), qvel=np.zeros(14),
                                 ctrl=np.zeros(14), contact=[], ncon=0),
            free=lambda: None)

    def observation(self):
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        image[0, 0, 0] = self.steps % 256
        return {'pixels': {'top': image}, 'agent_pos': self.physics.data.ctrl.copy()}

    def reset(self, seed=None):
        self.steps = 0
        self.physics.data.time = 0.
        self.physics.data.ctrl[:] = 0
        return self.observation(), {}

    def step(self, action):
        self.steps += 1
        self.physics.data.time = self.steps * .02
        self.physics.data.ctrl[:] = action
        return SimpleNamespace(observation=self.observation(), reward=0)

    def _format_raw_obs(self, observation):
        return observation

    def close(self):
        pass


def make(name, **options):
    if name != 'gym_aloha/AlohaTransferCube-v0':
        raise ValueError('unexpected environment')
    return Environment()
