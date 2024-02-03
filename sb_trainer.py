from stable_baselines3 import PPO 
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.logger import Figure
from matplotlib import pyplot as plt
from airhockey2d import AirHockey2D
import numpy as np
import argparse
import yaml
import os


def train_air_hockey_model(air_hockey_cfg):
    """
    Train an air hockey paddle model using stable baselines.

    This script loads the configuration file, creates an AirHockey2D environment,
    wraps the environment with necessary components, trains the model,
    and saves the trained model and environment statistics.
    """
    
    air_hockey_params = air_hockey_cfg['air_hockey']
    env = AirHockey2D.from_dict(air_hockey_params)

    def wrap_env(env):
        wrapped_env = Monitor(env) # needed for extracting eprewmean and eplenmean
        wrapped_env = DummyVecEnv([lambda: wrapped_env]) # Needed for all environments (e.g. used for multi-processing)
        wrapped_env = VecNormalize(wrapped_env) # probably something to try when tuning
        return wrapped_env

    env = wrap_env(env)
    model = PPO("MlpPolicy", env, verbose=1, tensorboard_log=air_hockey_cfg['tb_log_dir'])
    model.learn(total_timesteps=air_hockey_cfg['n_training_steps'],
                tb_log_name=air_hockey_cfg['tb_log_name'], 
                progress_bar=True)
    model.save(air_hockey_cfg['model_save_filepath'])
    env.save(air_hockey_cfg['vec_normalize_save_filepath'])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Demonstrate the air hockey game.')
    parser.add_argument('--cfg', type=str, default=None, help='Path to the configuration file.')
    args = parser.parse_args()
    if args.cfg is None:
        dir_path = os.path.dirname(os.path.realpath(__file__))
        air_hockey_cfg_fp = os.path.join(dir_path, 'configs', 'train_ppo.yaml')
    else:
        air_hockey_cfg_fp = args.cfg
    with open(air_hockey_cfg_fp, 'r') as f:
        air_hockey_cfg = yaml.safe_load(f)
    train_air_hockey_model(air_hockey_cfg)