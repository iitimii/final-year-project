import os
import time
from datetime import datetime
import gymnasium as gym
import numpy as np
import torch
from stable_baselines3 import PPO, SAC
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.callbacks import EvalCallback, StopTrainingOnRewardThreshold, StopTrainingOnNoModelImprovement
from stable_baselines3.common.evaluation import evaluate_policy

from gym_pybullet_drones.utils.Logger import Logger
from gym_pybullet_drones.envs.HoverAviary import HoverAviary
from gym_pybullet_drones.utils.utils import sync
from gym_pybullet_drones.utils.enums import ObservationType, ActionType

from envs.WaypointsRLAviary import WaypointsAviary

DEFAULT_GUI = True
DEFAULT_RECORD_VIDEO = False
DEFAULT_OUTPUT_FOLDER = 'results'
DEFAULT_COLAB = False

DEFAULT_OBS = ObservationType('kin') # 'kin' or 'rgb'
DEFAULT_ACT = ActionType('one_d_rpm') # 'rpm' or 'pid' or 'vel' or 'one_d_rpm' or 'one_d_pid'
DEFAULT_AGENTS = 2
DEFAULT_MA = False


def run(multiagent=DEFAULT_MA, output_folder=DEFAULT_OUTPUT_FOLDER, gui=DEFAULT_GUI, plot=True, colab=DEFAULT_COLAB, record_video=DEFAULT_RECORD_VIDEO):
    filename = os.path.join(output_folder, 'save-'+datetime.now().strftime("%m.%d.%Y_%H.%M.%S"))
    if not os.path.exists(filename):
        os.makedirs(filename+'/')

    train_env = make_vec_env(WaypointsAviary,
                                 env_kwargs=dict(obs=DEFAULT_OBS, act=DEFAULT_ACT),
                                 n_envs=1,
                                 seed=0
                                 )
    
    eval_env = WaypointsAviary(obs=DEFAULT_OBS, act=DEFAULT_ACT)

    #### Check the environment's spaces ########################
    print('[INFO] Action space:', train_env.action_space)
    print('[INFO] Observation space:', train_env.observation_space)

    model = PPO('MlpPolicy', train_env, verbose=1)
    # model = SAC('MlpPolicy', train_env)

    #### Target cumulative rewards (problem-dependent) ##########
    if DEFAULT_ACT == ActionType.ONE_D_RPM:
        target_reward = 474.15
    else:
        target_reward = 467.

    callback_on_best = StopTrainingOnRewardThreshold(reward_threshold=target_reward,
                                                     verbose=1)
    
    eval_callback = EvalCallback(eval_env,
                                 callback_on_new_best=callback_on_best,
                                 verbose=1,
                                 best_model_save_path=filename+'/',
                                 log_path=filename+'/',
                                 eval_freq=int(1000),
                                 deterministic=True,
                                 render=False)
    
    model.learn(total_timesteps=int(1e7),
                callback=eval_callback,
                log_interval=100)
    
    model.save(filename+'/final_model.zip')
    print(filename)

    #### Print training progression ############################
    with np.load(filename+'/evaluations.npz') as data:
        for j in range(data['timesteps'].shape[0]):
            print(str(data['timesteps'][j])+","+str(data['results'][j][0]))

    input("Press Enter to continue...")

    if os.path.isfile(filename+'/best_model.zip'):
        path = filename+'/best_model.zip'
    else:
        print("[ERROR]: no model under the specified path", filename)
    model = PPO.load(path)
    # model = SAC.load(path)

    test_env = HoverAviary(gui=gui,
                               obs=DEFAULT_OBS,
                               act=DEFAULT_ACT,
                               record=record_video)
    test_env_nogui = HoverAviary(obs=DEFAULT_OBS, act=DEFAULT_ACT)

    logger = Logger(logging_freq_hz=int(test_env.CTRL_FREQ),
                num_drones=DEFAULT_AGENTS if multiagent else 1,
                output_folder=output_folder,
                colab=colab
                )

    mean_reward, std_reward = evaluate_policy(model,
                                              test_env_nogui,
                                              n_eval_episodes=10
                                              )
    print("\n\n\nMean reward ", mean_reward, " +- ", std_reward, "\n\n")

    obs, info = test_env.reset(seed=42, options={})
    start = time.time()

    for i in range((test_env.EPISODE_LEN_SEC+2)*test_env.CTRL_FREQ):
        action, _states = model.predict(obs, deterministic=True)

        obs, reward, terminated, truncated, info = test_env.step(action)
        obs2 = obs.squeeze()
        act2 = action.squeeze()
        print("Obs:", obs, "\tAction", action, "\tReward:", reward, "\tTerminated:", terminated, "\tTruncated:", truncated)

        if DEFAULT_OBS == ObservationType.KIN:
            logger.log(drone=0,
                timestamp=i/test_env.CTRL_FREQ,
                state=np.hstack([obs2[0:3],
                                    np.zeros(4),
                                    obs2[3:15],
                                    act2
                                    ]),
                control=np.zeros(12)
                )
            
            test_env.render()
            print(terminated)
            sync(i, start, test_env.CTRL_TIMESTEP)
            if terminated:
                obs = test_env.reset(seed=42, options={})

    test_env.close()

    if plot and DEFAULT_OBS == ObservationType.KIN:
        logger.plot()



if __name__ == "__main__":
    run()