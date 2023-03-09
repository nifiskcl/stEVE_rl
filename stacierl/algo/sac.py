from typing import List
import logging
import numpy as np
import torch
import torch.nn.functional as F
from .algo import Algo
from .sacmodel import SACModel
from ..replaybuffer import Batch


class SAC(Algo):
    def __init__(
        self,
        model: SACModel,
        n_actions: int,
        gamma: float = 0.99,
        tau: float = 0.005,
        reward_scaling: float = 1,
        action_scaling: float = 1,
        exploration_action_noise: float = 0.25,
    ):
        super().__init__()
        self.logger = logging.getLogger(self.__module__)
        # HYPERPARAMETERS
        self.n_actions = n_actions
        self.gamma = gamma
        self.tau = tau
        self.exploration_action_noise = exploration_action_noise
        # Model
        self._model = model

        # REST
        self.reward_scaling = reward_scaling
        self.action_scaling = action_scaling

        self.device = torch.device("cpu")
        self.update_step = 0

        # ENTROPY TEMPERATURE
        self.alpha = torch.ones(1)
        self.target_entropy = -torch.ones(1) * n_actions

    @property
    def model(self) -> SACModel:
        return self._model

    def get_exploration_action(self, flat_state: np.ndarray) -> np.ndarray:
        action = self.model.get_play_action(flat_state, evaluation=False)
        action += np.random.normal(0, self.exploration_action_noise)
        return action

    def get_eval_action(self, flat_state: np.ndarray) -> np.ndarray:
        action = self.model.get_play_action(flat_state, evaluation=True)
        return action * self.action_scaling

    def update(self, batch: Batch) -> List[float]:

        (all_states, actions, rewards, dones, padding_mask) = batch
        # actions /= self.action_scaling

        all_states = all_states.to(dtype=torch.float32, device=self.device)
        actions = actions.to(dtype=torch.float32, device=self.device)
        rewards = rewards.to(dtype=torch.float32, device=self.device)
        dones = dones.to(dtype=torch.float32, device=self.device)

        if padding_mask is not None:
            padding_mask = padding_mask.to(dtype=torch.float32, device=self.device)

        seq_length = actions.shape[1]
        states = torch.narrow(all_states, dim=1, start=0, length=seq_length)

        # use all_states for next_actions and next_log_pi for proper hidden_state initilaization
        next_actions, next_log_pi = self.model.get_update_action(all_states)
        next_q1, next_q2 = self.model.get_target_q_values(all_states, next_actions)
        next_q_target = torch.min(next_q1, next_q2) - self.alpha * next_log_pi
        # only use next_state for next_q_target
        next_q_target = torch.narrow(next_q_target, dim=1, start=1, length=seq_length)
        expected_q = rewards + (1 - dones) * self.gamma * next_q_target

        curr_q1, curr_q2 = self.model.get_q_values(states, actions)
        if padding_mask is not None:
            expected_q *= padding_mask
            curr_q1 *= padding_mask
            curr_q2 *= padding_mask

        q1_loss = F.mse_loss(curr_q1, expected_q.detach())
        q2_loss = F.mse_loss(curr_q2, expected_q.detach())

        self.model.q1_update_zero_grad()
        q1_loss.backward()
        self.model.q1_update_step()

        self.model.q2_update_zero_grad()
        q2_loss.backward()
        self.model.q2_update_step()

        new_actions, log_pi = self.model.get_update_action(states)

        q1, q2 = self.model.get_q_values(states, new_actions)
        min_q = torch.min(q1, q2)

        if padding_mask is not None:
            min_q *= padding_mask
            log_pi *= padding_mask

        policy_loss = (self.alpha * log_pi - min_q).mean()

        self.model.policy_update_zero_grad()
        policy_loss.backward()
        self.model.policy_update_step()

        self.model.update_target_q(self.tau)

        alpha_loss = (
            self.model.log_alpha * (-log_pi - self.target_entropy).detach()
        ).mean()
        self.model.alpha_update_zero_grad()
        alpha_loss.backward()
        self.model.alpha_update_step()

        self.alpha = self.model.log_alpha.exp()

        self.update_step += 1
        return [
            q1_loss.detach().cpu().numpy(),
            q2_loss.detach().cpu().numpy(),
            policy_loss.detach().cpu().numpy(),
        ]

    def lr_scheduler_step(self) -> None:
        super().lr_scheduler_step()
        self.model.q1_scheduler_step()
        self.model.q2_scheduler_step()
        self.model.policy_scheduler_step()

    def to(self, device: torch.device):
        super().to(device)
        self.alpha = self.alpha.to(device)
        self.target_entropy = self.target_entropy.to(device)
        self.model.to(device)

    def reset(self) -> None:
        self.model.reset()

    def close(self):
        self.model.close()

    def copy_play_only(self):
        return self.__class__(
            self.model.copy_play_only(),
            self.n_actions,
            self.gamma,
            self.tau,
            self.reward_scaling,
            self.action_scaling,
            self.exploration_action_noise,
        )
