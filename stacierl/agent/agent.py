from abc import ABC, abstractmethod
from typing import List
from dataclasses import dataclass
import torch.multiprocessing as mp
import gymnasium as gym
import torch

from ..replaybuffer.replaybuffer import Episode
from ..util import ConfigHandler
from ..algo import Algo
from ..replaybuffer import ReplayBuffer


@dataclass
class EpisodeCounter:
    heatup: int = 0
    exploration: int = 0
    evaluation: int = 0
    lock = mp.Lock()

    def __iadd__(self, other):
        self.heatup += other.heatup
        self.exploration += other.exploration
        self.evaluation += other.evaluation
        return self


@dataclass
class StepCounter:
    heatup: int = 0
    exploration: int = 0
    evaluation: int = 0
    update: int = 0
    lock = mp.Lock()

    def __iadd__(self, other):
        self.heatup += other.heatup
        self.exploration += other.exploration
        self.evaluation += other.evaluation
        self.update += other.update
        return self


class StepCounterShared(StepCounter):
    # pylint: disable=super-init-not-called
    def __init__(self):
        self._heatup: mp.Value = mp.Value("i", 0)
        self._exploration: mp.Value = mp.Value("i", 0)
        self._evaluation: mp.Value = mp.Value("i", 0)
        self._update: mp.Value = mp.Value("i", 0)

    @property
    def heatup(self) -> int:
        return self._heatup.value

    @heatup.setter
    def heatup(self, value: int) -> int:
        self._heatup.value = value

    @property
    def exploration(self) -> int:
        return self._exploration.value

    @exploration.setter
    def exploration(self, value: int) -> int:
        self._exploration.value = value

    @property
    def evaluation(self) -> int:
        return self._evaluation.value

    @evaluation.setter
    def evaluation(self, value: int) -> int:
        self._evaluation.value = value

    @property
    def update(self) -> int:
        return self._update.value

    @update.setter
    def update(self, value: int) -> int:
        self._update.value = value

    def __iadd__(self, other):
        self._heatup.value = self._heatup.value + other.heatup
        self._exploration.value = self._exploration.value + other.exploration
        self._evaluation.value = self._evaluation.value + other.evaluation
        self._update.value = self._update.value + other.update
        return self


class EpisodeCounterShared(EpisodeCounter):
    # pylint: disable=super-init-not-called
    def __init__(self):
        self._heatup: mp.Value = mp.Value("i", 0)
        self._exploration: mp.Value = mp.Value("i", 0)
        self._evaluation: mp.Value = mp.Value("i", 0)

    @property
    def heatup(self) -> int:
        return self._heatup.value

    @heatup.setter
    def heatup(self, value: int) -> int:
        self._heatup.value = value

    @property
    def exploration(self) -> int:
        return self._exploration.value

    @exploration.setter
    def exploration(self, value: int) -> int:
        self._exploration.value = value

    @property
    def evaluation(self) -> int:
        return self._evaluation.value

    @evaluation.setter
    def evaluation(self, value: int) -> int:
        self._evaluation.value = value

    def __iadd__(self, other):
        self._heatup.value = self._heatup.value + other.heatup
        self._exploration.value = self._exploration.value + other.exploration
        self._evaluation.value = self._evaluation.value + other.evaluation
        return self


class Agent(ABC):
    step_counter: StepCounter
    episode_counter: EpisodeCounter
    algo: Algo
    env_train: gym.Env
    env_eval: gym.Env
    replay_buffer: ReplayBuffer

    @abstractmethod
    def heatup(self, steps: int = None, episodes: int = None) -> List[Episode]:
        ...

    @abstractmethod
    def explore(self, steps: int = None, episodes: int = None) -> List[Episode]:
        ...

    @abstractmethod
    def update(self, steps) -> List[List[float]]:
        ...

    @abstractmethod
    def evaluate(self, steps: int = None, episodes: int = None) -> List[Episode]:
        ...

    @abstractmethod
    def close(self) -> None:
        ...

    def save_config(self, file_path: str):
        confighandler = ConfigHandler()
        confighandler.save_config(self, file_path)

    def save_checkpoint(self, file_path) -> None:
        confighandler = ConfigHandler()
        algo_dict = confighandler.object_to_config_dict(self.algo)
        replay_dict = confighandler.object_to_config_dict(self.replay_buffer)
        checkpoint_dict = {
            "algo": {
                "network": self.algo.state_dicts_network(),
                "config": algo_dict,
            },
            "replay_buffer": {"config": replay_dict},
            "steps": {
                "heatup": self.step_counter.heatup,
                "exploration": self.step_counter.exploration,
                "update": self.step_counter.update,
                "evaluation": self.step_counter.evaluation,
            },
            "episodes": {
                "heatup": self.episode_counter.heatup,
                "exploration": self.episode_counter.exploration,
                "evaluation": self.episode_counter.evaluation,
            },
        }

        torch.save(checkpoint_dict, file_path)

    def load_checkpoint(self, file_path: str) -> None:
        checkpoint = torch.load(file_path)

        state_dicts_network = checkpoint["algo"]["network"]
        self.algo.load_state_dicts_network(state_dicts_network)

        self.step_counter.heatup = checkpoint["steps"]["heatup"]
        self.step_counter.exploration = checkpoint["steps"]["exploration"]
        self.step_counter.evaluation = checkpoint["steps"]["evaluation"]
        self.step_counter.update = checkpoint["steps"]["update"]

        self.episode_counter.heatup = checkpoint["episodes"]["heatup"]
        self.episode_counter.exploration = checkpoint["episodes"]["exploration"]
        self.episode_counter.evaluation = checkpoint["episodes"]["evaluation"]
