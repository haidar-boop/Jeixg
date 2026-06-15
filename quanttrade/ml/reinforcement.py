"""Reinforcement-learning framework for trading.

Provides a self-contained, Gym-style single-asset trading environment and a
tabular Q-learning agent as a working example. Deep RL agents (DQN/PPO) plug in
via ``stable-baselines3`` against the same :class:`TradingEnv` interface
(lazy-imported; not required).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Discrete action space.
HOLD, BUY, SELL = 0, 1, 2


@dataclass
class StepResult:
    observation: np.ndarray
    reward: float
    done: bool
    info: dict


class TradingEnv:
    """Minimal single-asset trading environment.

    State: a window of recent returns + current position flag.
    Actions: {0: hold, 1: buy/long, 2: sell/flat}.
    Reward: change in mark-to-market portfolio value per step (minus cost).
    """

    def __init__(self, prices: pd.Series, window: int = 5,
                 transaction_cost: float = 0.0005, starting_cash: float = 10_000.0) -> None:
        self.prices = prices.reset_index(drop=True)
        self.window = window
        self.transaction_cost = transaction_cost
        self.starting_cash = starting_cash
        self.action_space_n = 3
        self.reset()

    def reset(self) -> np.ndarray:
        self.t = self.window
        self.cash = self.starting_cash
        self.shares = 0.0
        self.position = 0  # 0 flat, 1 long
        self._prev_value = self.starting_cash
        return self._obs()

    def _obs(self) -> np.ndarray:
        window = self.prices.iloc[self.t - self.window:self.t]
        rets = window.pct_change().fillna(0.0).to_numpy()
        return np.append(rets, float(self.position))

    def _value(self) -> float:
        return self.cash + self.shares * self.prices.iloc[self.t]

    def step(self, action: int) -> StepResult:
        price = self.prices.iloc[self.t]
        cost = 0.0
        if action == BUY and self.position == 0:
            self.shares = self.cash / price
            cost = self.cash * self.transaction_cost
            self.cash = 0.0 - cost
            self.position = 1
        elif action == SELL and self.position == 1:
            proceeds = self.shares * price
            cost = proceeds * self.transaction_cost
            self.cash += proceeds - cost
            self.shares = 0.0
            self.position = 0

        self.t += 1
        done = self.t >= len(self.prices) - 1
        value = self._value()
        reward = value - self._prev_value
        self._prev_value = value
        return StepResult(self._obs(), float(reward), done,
                          {"value": value, "position": self.position})


class QLearningAgent:
    """Tabular Q-learning over discretised observations."""

    def __init__(self, n_actions: int = 3, bins: int = 6, alpha: float = 0.1,
                 gamma: float = 0.95, epsilon: float = 0.1, seed: int = 0) -> None:
        self.n_actions = n_actions
        self.bins = bins
        self.alpha = alpha
        self.gamma = gamma
        self.epsilon = epsilon
        self.q: dict[tuple, np.ndarray] = {}
        self._rng = np.random.default_rng(seed)

    def _key(self, obs: np.ndarray) -> tuple:
        # Discretise returns into sign buckets; keep position flag exact.
        disc = np.clip((obs[:-1] * 100).astype(int), -self.bins, self.bins)
        return (*disc.tolist(), int(obs[-1]))

    def act(self, obs: np.ndarray, explore: bool = True) -> int:
        if explore and self._rng.random() < self.epsilon:
            return int(self._rng.integers(self.n_actions))
        q = self.q.get(self._key(obs))
        return int(np.argmax(q)) if q is not None else HOLD

    def learn(self, obs, action, reward, next_obs) -> None:
        key, nkey = self._key(obs), self._key(next_obs)
        q = self.q.setdefault(key, np.zeros(self.n_actions))
        nq = self.q.setdefault(nkey, np.zeros(self.n_actions))
        q[action] += self.alpha * (reward + self.gamma * nq.max() - q[action])

    def train(self, env: TradingEnv, episodes: int = 50) -> list[float]:
        """Train on the env, returning the per-episode total reward curve."""
        history: list[float] = []
        for _ in range(episodes):
            obs = env.reset()
            done, total = False, 0.0
            while not done:
                action = self.act(obs)
                result = env.step(action)
                self.learn(obs, action, result.reward, result.observation)
                obs = result.observation
                total += result.reward
                done = result.done
            history.append(total)
        return history
