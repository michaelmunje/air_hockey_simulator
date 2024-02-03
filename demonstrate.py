import cv2
import numpy as np
import time
from airhockey2d import AirHockey2D
from render import AirHockeyRenderer
import argparse
import yaml
import os

class Demonstrator:
    def __init__(self, air_hockey_cfg):
        """
        Initializes the Demonstrator class.

        Creates an instance of the AirHockeyBox2D class with specified parameters,
        an instance of the AirHockeyRenderer class, and sets the keyboard scheme.

        Parameters:
        None

        Returns:
        None
        """
        self.air_hockey = AirHockey2D.from_dict(air_hockey_cfg['air_hockey'])
        self.renderer = AirHockeyRenderer(self.air_hockey)
        self.keyboard_scheme = 'wasd'
        self.print_reward = air_hockey_cfg['print_reward']
    
    def demonstrate(self):
        """
        Performs the demonstration of the air hockey game.

        Captures the frame from the renderer, displays it, and waits for user input.
        Based on the keyboard scheme, determines the action to be taken.
        If the orientation is vertical, adjusts the action accordingly.

        Parameters:
        None

        Returns:
        action (numpy.array): The action to be taken in the game.
        """
        action = np.array([0,0])
        frame = self.renderer.get_frame()
        cv2.imshow('Air Hockey 2D Demonstration',frame)
        key = cv2.waitKey(5)
        if self.keyboard_scheme == 'qweasdzxc':
            if key == ord('k'):
                action = -1
            elif key == ord('q'):
                action = np.array([-1,-1])
            elif key == ord('w'):
                action = np.array([-1,0])
            elif key == ord('e'):
                action = np.array([-1,1])
            elif key == ord('a'):
                action = np.array([0,-1])
            elif key == ord('s'):
                action = np.array([0,0])
            elif key == ord('d'):
                action = np.array([0,1])
            elif key == ord('z'):
                action = np.array([1,-1])
            elif key == ord('x'):
                action = np.array([1,0])
            elif key == ord('c'):
                action = np.array([1,1])
        elif self.keyboard_scheme == 'wasd':
            if key == ord('w'):
                action = np.array([-1,0])
            elif key == ord('a'):
                action = np.array([0,-1])
            elif key == ord('s'):
                action = np.array([1,0])
            elif key == ord('d'):
                action = np.array([0,1])
        else:
            raise ValueError("Invalid keyboard scheme")
        if self.renderer.orientation == 'vertical':
            action = np.array([action[1], -action[0]])
        return action
        
    def run(self):
        """
        Runs the air hockey demonstration.

        Iterates through a loop, capturing user input and updating the game state.
        Prints the frames per second (fps) every 1000 iterations.
        Resets the game state every 300 iterations.

        Parameters:
        None

        Returns:
        None
        """
        start = time.time()
        for i in range(1000000):
            if i % 1000 == 0:
                print("fps", 1000 / (time.time() - start))
                start = time.time()
            action = self.demonstrate()
            _, rew, _, _, _ = self.air_hockey.step(action)
            if self.print_reward:
                print("reward: ", rew)
            if i % 300 == 0:
                self.air_hockey.reset()
                
    def play_against_agent(self, policy):
        """
        Plays the air hockey game against an agent.

        Iterates through a loop, capturing user input and updating the game state.
        Prints the frames per second (fps) every 1000 iterations.
        Resets the game state every 300 iterations.

        Parameters:
        policy (function): The policy function of the agent.

        Returns:
        None
        """
        obs, _ = self.air_hockey.reset()
        start = time.time()
        for i in range(1000000):
            if i % 1000 == 0:
                print("fps", 1000 / (time.time() - start))
                start = time.time()
            action = self.demonstrate()
            policy_obs = -1 * obs # since policy is on the opposite side now
            other_action = policy.predict(policy_obs, deterministic=True)[0]
            (_, obs), _, _, _, _ = self.air_hockey.step(action, other_action)
            if i % 300 == 0:
                self.air_hockey.reset()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Demonstrate the air hockey game.')
    parser.add_argument('--cfg', type=str, default=None, help='Path to the configuration file.')
    args = parser.parse_args()
    if args.cfg is None:
        # Then our default path is demonstrate.yaml in the config file
        dir_path = os.path.dirname(os.path.realpath(__file__))
        air_hockey_cfg_fp = os.path.join(dir_path, 'configs', 'demonstrate.yaml')
    else:
        air_hockey_cfg_fp = args.cfg
    with open(air_hockey_cfg_fp, 'r') as f:
        air_hockey_cfg = yaml.safe_load(f)

    demonstrator = Demonstrator(air_hockey_cfg)
    demonstrator.run()
    cv2.destroyAllWindows()