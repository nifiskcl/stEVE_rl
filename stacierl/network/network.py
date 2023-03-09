from abc import abstractmethod
import torch.nn as nn


import torch


class Network(nn.Module):
    @property
    @abstractmethod
    def n_inputs(self) -> int:
        ...

    @property
    @abstractmethod
    def n_outputs(self) -> int:
        ...

    @property
    @abstractmethod
    def device(self) -> torch.device:
        ...

    @abstractmethod
    def forward(self, obs_batch: torch.Tensor, *args, **kwargs) -> torch.Tensor:
        ...

    @abstractmethod
    def copy(self):
        ...

    @abstractmethod
    def reset(self) -> None:
        ...
