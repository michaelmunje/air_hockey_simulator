from Box2D.b2 import world
from Box2D import (b2CircleShape, b2FixtureDef, b2LoopShape, b2PolygonShape,
                   b2_dynamicBody, b2_staticBody, b2Filter, b2Vec2)
from gymnasium import Env
import numpy as np
import random
from gymnasium.spaces import Box
from gymnasium import spaces
from typing import Union


class AirHockey2D(Env):
    def __init__(self,
                 num_paddles, 
                 num_pucks, 
                 num_blocks, 
                 num_obstacles, 
                 num_targets, 
                 absorb_target, 
                 length, 
                 width,
                 puck_radius, 
                 paddle_radius, 
                 reward_type, 
                 max_force_timestep, 
                 n_training_steps,
                 force_scaling, 
                 paddle_damping, 
                 render_size, 
                 wall_bumping_rew,
                 terminate_on_out_of_bounds, 
                 terminate_on_enemy_goal, 
                 truncate_rew,
                 goal_max_x_velocity, 
                 goal_min_y_velocity, 
                 goal_max_y_velocity,
                 render_masks=False, 
                 max_timesteps=1000, 
                 gravity=-5, 
                 paddle_density=1,
                 puck_density=0.25,
                 max_paddle_vel=1.5,
                 time_frequency=20):

        # task specific params
        self.num_pucks = num_pucks
        self.num_blocks = num_blocks
        self.num_obstacles = num_obstacles
        self.num_targets = num_targets
        
        self.max_timesteps = max_timesteps
        self.current_timestep = 0
        self.n_training_steps = n_training_steps
        self.n_timesteps_so_far = 0
        
        # termination conditions
        self.terminate_on_out_of_bounds = terminate_on_out_of_bounds
        self.terminate_on_enemy_goal = terminate_on_enemy_goal

        # physics / world params
        self.length, self.width = length, width
        self.num_paddles = num_paddles
        self.paddle_radius = paddle_radius
        self.puck_radius = puck_radius
        self.max_force_timestep = max_force_timestep
        self.time_frequency = time_frequency
        self.time_per_step = 1 / self.time_frequency
        self.force_scaling = force_scaling
        self.absorb_target = absorb_target
        self.paddle_damping = paddle_damping
        self.gravity = gravity
        self.puck_min_height = (-length / 2) + (length / 3)
        self.paddle_max_height = 0
        self.block_min_height = 0
        self.max_speed_start = width
        self.min_speed_start = -width
        self.paddle_density = paddle_density
        self.puck_density = puck_density
        # these assume 2d, in 3d since we have height it would be higher mass
        self.paddle_mass = self.paddle_density * np.pi * self.paddle_radius ** 2
        self.puck_mass = self.puck_density * np.pi * self.puck_radius ** 2

        # these 2 will depend on the other parameters
        self.max_paddle_vel = max_paddle_vel # m/s. This will be dependent on the robot arm
        # compute maximum force based on max paddle velocity
        max_a = self.max_paddle_vel / self.time_per_step
        max_f = self.paddle_mass * max_a
        # assume maximum force transfer
        puck_max_a = max_f / self.puck_mass
        self.max_puck_vel = puck_max_a * self.time_per_step
        self.world = world(gravity=(0, self.gravity), doSleep=True) # gravity is negative usually

        # box2d visualization params (but the visualization is done in the Render file)
        self.ppm = render_size / self.width
        self.render_width = int(render_size)
        self.render_length = int(self.ppm * self.length)
        self.render_masks = render_masks
        
        # reward function
        self.goal_conditioned = True if 'goal' in reward_type else False
        self.goal_radius_type = 'home'
        self.goal_min_x_velocity = -goal_max_x_velocity
        self.goal_max_x_velocity = goal_max_x_velocity
        self.goal_min_y_velocity = goal_min_y_velocity
        self.goal_max_y_velocity = goal_max_y_velocity
        self.reward_type = reward_type
        self.multiagent = num_paddles == 2
        self.truncate_rew = truncate_rew
        self.wall_bumping_rew = wall_bumping_rew
        
        self.table_x_min = -self.width / 2
        self.table_x_max = self.width / 2
        self.table_y_min = -self.length / 2
        self.table_y_max = self.length / 2
        
        self.initialize_spaces()
        
        self.metadata = {}
        
        # creating the ground -- need to only call once! otherwise it can be laggy
        self.ground_body = self.world.CreateBody(
            shapes=b2LoopShape(vertices=[(self.table_x_min, self.table_y_min),
                                         (self.table_x_min, self.table_y_max), 
                                         (self.table_x_max, self.table_y_max),
                                         (self.table_x_max, self.table_y_min)]),
        )
        self.reset()

    def initialize_spaces(self):
        # setup observation / action / reward spaces
        low = np.array([self.table_x_min, self.table_y_min, -self.max_paddle_vel, -self.max_paddle_vel, 
                        self.table_x_min, self.table_y_min, -self.max_puck_vel, -self.max_puck_vel])

        high = np.array([self.table_x_max, self.table_y_max, self.max_paddle_vel, self.max_paddle_vel, 
                         self.table_x_max, self.table_y_max, self.max_puck_vel, self.max_puck_vel])
        
        if not self.goal_conditioned:
            self.observation_space = Box(low=low, high=high, shape=(8,), dtype=float)
        else:
            
            if self.reward_type == 'goal_position':
                # y, x
                goal_low = np.array([0, self.table_x_min])#, -self.max_paddle_vel, self.max_paddle_vel])
                goal_high = np.array([self.table_y_max, self.table_x_max])#, self.max_paddle_vel, self.max_paddle_vel])
                
                self.observation_space = spaces.Dict(dict(
                    observation=Box(low=low, high=high, shape=(8,), dtype=float),
                    desired_goal=Box(low=goal_low, high=goal_high, shape=(2,), dtype=float),
                    achieved_goal=Box(low=goal_low, high=goal_high, shape=(2,), dtype=float)
                ))
            
            elif self.reward_type == 'goal_position_velocity':
                goal_low = np.array([0, self.table_x_min, -self.max_puck_vel, -self.max_puck_vel])
                goal_high = np.array([self.table_y_max, self.table_x_max, self.max_puck_vel, self.max_puck_vel])
                self.observation_space = spaces.Dict(dict(
                    observation=Box(low=low, high=high, shape=(8,), dtype=float),
                    desired_goal=Box(low=goal_low, high=goal_high, shape=(4,), dtype=float),
                    achieved_goal=Box(low=goal_low, high=goal_high, shape=(4,), dtype=float)
                ))
            
            self.min_goal_radius = self.width / 16
            self.max_goal_radius = self.width / 4
        self.action_space = Box(low=-1, high=1, shape=(2,), dtype=np.float32) # 2D action space
        self.reward_range = Box(low=0, high=1) # need to make sure rewards are between 0 and 1

    @staticmethod
    def from_dict(state_dict):
        return AirHockey2D(**state_dict)

    def reset(self, 
              seed=None, 
              ego_goal_pos=None,
              alt_goal_pos=None,
              object_state_dict=None, 
              type_instance_dict=None, 
              max_count_dict=None):

        if seed is None:
            seed = np.random.randint(10e8)
        np.random.seed(seed)

        if hasattr(self, "object_dict"):
            for body in self.object_dict.values():
                self.world.DestroyBody(body)

        if type(self.gravity) == list:
            self.world.gravity = (0, np.random.uniform(low=self.gravity[0], high=self.gravity[1]))

        self.n_timesteps_so_far += self.current_timestep
        self.current_timestep = 0

        self.paddles = dict()
        self.pucks = dict()
        self.blocks = dict()
        self.obstacles = dict()
        self.targets = dict()

        self.paddle_attrs = None
        self.target_attrs = None

        self.set_goals(self.goal_radius_type, ego_goal_pos, alt_goal_pos)

        self.create_world_objects()
        
        # get initial observation
        obs = self.get_current_observation()
        
        if not self.goal_conditioned:
            return obs, {}
        else:
            return {"observation": obs, "desired_goal": self.get_desired_goal(), "achieved_goal": self.get_achieved_goal()}, {}

    def get_achieved_goal(self):
        if self.reward_type == 'goal_position':
            # numpy array containing puck position and vel
            position = self.pucks[self.puck_names[0]][0].position
            # velocity = self.pucks[self.puck_names[0]][0].linearVelocity
            # return np.array([position[0], position[1], velocity[0], velocity[1]])
            position = np.array([position[1], position[0]])
            return position.astype(float)
        elif self.reward_type == 'goal_position_velocity':
            position = self.pucks[self.puck_names[0]][0].position
            velocity = self.pucks[self.puck_names[0]][0].linearVelocity
            return np.array([position[1], position[0], velocity[0], velocity[1]])
        else:
            raise ValueError("Invalid reward type for goal conditioned environment. " +
                             "Should be goal_position or goal_position_velocity.")
    
    def get_desired_goal(self):
        position = self.ego_goal_pos
        if self.reward_type == 'goal_position':
            return position.astype(float)
        elif self.reward_type == 'goal_position_velocity':
            velocity = self.ego_goal_vel
            return np.array([position[1], position[0], velocity[0], velocity[1]])
        else:
            raise ValueError("Invalid reward type for goal conditioned environment. " +
                             "Should be goal_position or goal_position_velocity.")
    
    def compute_reward(self, achieved_goal, desired_goal, info):
        # if not vectorized, convert to vector
        single = len(achieved_goal.shape) == 1
        if single:
            achieved_goal = achieved_goal.reshape(1, -1)
            desired_goal = desired_goal.reshape(1, -1)
        if self.goal_conditioned:
            if achieved_goal.shape[1] == 2:
                # return euclidean distance between the two points
                dist = np.linalg.norm(achieved_goal[:, :2] - desired_goal[:, :2], axis=1)
                
                # make this way faster?
                # p = 0.5
                
                # reward = -np.power(np.dot(np.abs(achieved_goal - desired_goal), np.array([1, 1]),), p)
                
                # print(achieved_goal)
                # print(desired_goal)
                
                # # also return float from [0, 1] 0 being far 1 being the point
                # # use sigmoid function because being closer is much more important than being far
                sigmoid_scale = 2
                radius = self.ego_goal_radius
                reward_raw = 1 - (dist / radius) #self.max_goal_rew_radius * radius)
                reward_mask = dist >= radius
                reward_raw[reward_mask] = 0 # numerical stability, we will make these 0 later
                reward = 1 / (1 + np.exp(-reward_raw * sigmoid_scale))
                reward[reward_mask] = 0
                # if dist >= self.max_goal_rew_radius, 
                # reward = reward.astype(float)
            else:
                # return euclidean distance between the two points
                dist = np.linalg.norm(achieved_goal[:, :2] - desired_goal[:, :2], axis=1)
                # compute angle between velocities
                denom = np.linalg.norm(achieved_goal[:, 2:], axis=1) * np.linalg.norm(desired_goal[:, 2:], axis=1) + 1e-8
                vel_cos = np.sum(achieved_goal[:, 2:] * desired_goal[:, 2:], axis=1) / denom
                
                # numerical stability
                vel_cos = np.clip(vel_cos, -1, 1)
                vel_angle = np.arccos(vel_cos)
                # mag difference
                mag_diff = np.linalg.norm(achieved_goal[:, 2:] - desired_goal[:, 2:], axis=1)
                
                # # also return float from [0, 1] 0 being far 1 being the point
                # # use sigmoid function because being closer is much more important than being far
                sigmoid_scale = 2
                radius = self.ego_goal_radius
                reward_raw = 1 - (dist / radius)#self.max_goal_rew_radius * radius)
                
                mask = dist >= radius
                reward_raw[mask] = 0 # numerical stability, we will make these 0 later
                reward = 1 / (1 + np.exp(-reward_raw * sigmoid_scale))
                reward_mask = dist >= radius
                reward[reward_mask] = 0
                position_reward = reward

                vel_mag_reward = 1 - mag_diff / self.max_paddle_vel
                
                reward_mask = position_reward == 0
                norm_cos_sim = (vel_cos + 1) / 2
                vel_angle_reward = norm_cos_sim
                vel_angle_reward[reward_mask] = 0
                vel_mag_reward[reward_mask] = 0
                vel_reward = (vel_angle_reward + vel_mag_reward) / 2
                
                # reward = (position_reward + vel_reward + vel_mag_reward) / 3
                reward = 0.5 * position_reward + vel_reward
            if single:
                reward = reward[0]
            return reward
        else:
            return self.get_reward(False, False, False, False, self.ego_goal_pos, self.ego_goal_radius)

    def get_current_observation(self):
        ego_paddle_x_pos = self.paddles['paddle_ego'][0].position[0]
        ego_paddle_y_pos = self.paddles['paddle_ego'][0].position[1]
        ego_paddle_x_vel = self.paddles['paddle_ego'][0].linearVelocity[0]
        ego_paddle_y_vel = self.paddles['paddle_ego'][0].linearVelocity[1]
        puck_x_pos = self.pucks[self.puck_names[0]][0].position[0]
        puck_y_pos = self.pucks[self.puck_names[0]][0].position[1]
        puck_x_vel = self.pucks[self.puck_names[0]][0].linearVelocity[0]
        puck_y_vel = self.pucks[self.puck_names[0]][0].linearVelocity[1]

        if not self.multiagent:
            # if not self.goal_conditioned:
            obs = np.array([ego_paddle_x_pos, ego_paddle_y_pos, ego_paddle_x_vel, ego_paddle_y_vel, puck_x_pos, puck_y_pos, puck_x_vel, puck_y_vel])
            # else:
            #     obs = np.array([ego_paddle_x_pos, ego_paddle_y_pos, puck_x_pos, puck_y_pos, puck_x_vel, puck_y_vel,
            #                     self.ego_goal_pos[0], self.ego_goal_pos[1], self.ego_goal_radius])
        else:
            alt_paddle_x_pos = self.paddles['paddle_alt'][0].position[0]
            alt_paddle_y_pos = self.paddles['paddle_alt'][0].position[1]
            alt_paddle_x_vel = self.paddles['paddle_alt'][0].linearVelocity[0]
            alt_paddle_y_vel = self.paddles['paddle_alt'][0].linearVelocity[1]
            
            # if not self.goal_conditioned:
            obs_ego = np.array([ego_paddle_x_pos, ego_paddle_y_pos, ego_paddle_x_vel, ego_paddle_y_vel,  puck_x_pos, puck_y_pos, puck_x_vel, puck_y_vel])
            obs_alt = np.array([-alt_paddle_x_pos, -alt_paddle_y_pos, alt_paddle_x_vel, alt_paddle_y_vel, -puck_x_pos, -puck_y_pos, -puck_x_vel, -puck_y_vel])
            # else:
            #     obs_ego = np.array([ego_paddle_x_pos, ego_paddle_y_pos, puck_x_pos, puck_y_pos, puck_x_vel, puck_y_vel,
            #                         self.ego_goal_pos[0], self.ego_goal_pos[1], self.ego_goal_radius])
            #     obs_alt = np.array([-alt_paddle_x_pos, -alt_paddle_y_pos, -puck_x_pos, -puck_y_pos, -puck_x_vel, -puck_y_vel,
            #                         -self.alt_goal_pos[0], -self.alt_goal_pos[1], self.alt_goal_radius])
            obs = (obs_ego, obs_alt)
        return obs
    
    def set_goals(self, goal_radius_type, ego_goal_pos=None, alt_goal_pos=None):
        if self.goal_conditioned:
            if goal_radius_type == 'fixed':
                # ego_goal_radius = np.random.uniform(low=self.min_goal_radius, high=self.max_goal_radius)
                base_radius = (self.min_goal_radius + self.max_goal_radius) / 2 * (0.75)
                # linearly decrease radius, should start off at 3*base_radius then decrease to base_radius
                ratio = 2 * (1 - self.n_timesteps_so_far / self.n_training_steps) + 1
                ego_goal_radius = ratio * base_radius
                if self.multiagent:
                    alt_goal_radius = ego_goal_radius      
                self.ego_goal_radius = ego_goal_radius
                if self.multiagent:
                    self.alt_goal_radius = alt_goal_radius
            elif goal_radius_type == 'home':
                self.ego_goal_radius = 0.16 * self.width
                if self.multiagent:
                    self.alt_goal_radius = 0.16 * self.width
            if ego_goal_pos is None:
                min_x = self.table_x_min + self.ego_goal_radius
                max_x = self.table_x_max - self.ego_goal_radius
                min_y = 0 + self.ego_goal_radius
                max_y = self.length / 2 - self.ego_goal_radius
                self.ego_goal_pos = np.random.uniform(low=(min_y, min_x), high=(max_y, max_x))
                
                min_x_vel = self.goal_min_x_velocity
                max_x_vel = self.goal_max_x_velocity
                min_y_vel = self.goal_min_y_velocity
                max_y_vel = self.goal_max_y_velocity
                
                self.ego_goal_vel = np.random.uniform(low=(min_x_vel, min_y_vel), high=(max_x_vel, max_y_vel))
                
                if self.multiagent:
                    self.alt_goal_pos = np.random.uniform(low=(-self.length / 2, self.table_x_min), high=(0, self.table_x_max))
            else:
                self.ego_goal_pos = ego_goal_pos
                if self.multiagent:
                    self.alt_goal_pos = alt_goal_pos
        else:
            self.ego_goal_pos = None
            self.ego_goal_radius = None
            self.alt_goal_pos = None
            self.alt_goal_radius = None
                
    def create_world_objects(self):
        for i in range(self.num_pucks):
            # rad = max(0.25, np.random.rand() * (self.width/ 8))
            # rad = self.table_x_max0
            name, puck_attrs = self.create_puck(i, min_height=self.puck_min_height)
            self.pucks[name] = puck_attrs

        for i in range(self.num_blocks):
            name, block_attrs = self.create_block_type(i, name_type = "Block", dynamic=False, min_height = self.block_min_height)
            self.blocks[name] = block_attrs

        for i in range(self.num_obstacles): # could replace with arbitary polygons
            name, obs_attrs = self.create_block_type(i, name_type = "Obstacle", angle=np.random.rand() * np.pi, dynamic = False, color=(0, 127, 127), min_height = self.block_min_height)
            self.obstacles[name] = obs_attrs

        for i in range(self.num_targets):
            name, target_attrs = self.create_block_type(i, name_type = "Target", color=(255, 255, 0))
            self.targets[name] = target_attrs
        
        if not self.multiagent:
            name, paddle_attrs = self.create_paddle(i, name="paddle_ego", density=self.paddle_density, ldamp=self.paddle_damping, color=(0, 255, 0), max_height=self.paddle_max_height)
            self.paddles[name] = paddle_attrs
        else:
            name_home, paddle_ego_attrs = self.create_paddle(i=i, name="paddle_ego", density=2, ldamp=self.paddle_damping, color=(0, 255, 0), max_height=self.paddle_max_height, 
                                             home_paddle=True)
            name_other, paddle_other_attrs = self.create_paddle(i=i, name="paddle_alt", density=2, ldamp=self.paddle_damping, color=(0, 255, 0), max_height=self.paddle_max_height, 
                                             home_paddle=False)
            self.paddles[name_home] = paddle_ego_attrs
            self.paddles[name_other] = paddle_other_attrs
            
        # names and object dict
        self.puck_names = list(self.pucks.keys())
        self.puck_names.sort()
        self.paddle_names = list(self.paddles.keys())
        self.block_names = list(self.blocks.keys())
        self.block_names.sort()
        self.obstacle_names = list(self.obstacles.keys())
        self.obstacle_names.sort()
        self.target_names = list(self.targets.keys())
        self.target_names.sort()
        self.object_dict = {**{name: self.pucks[name][0] for name in self.pucks.keys()},
                            **{name: self.paddles[name][0] for name in self.paddles.keys()},
                             **{name: self.blocks[name][0] for name in self.blocks.keys()},
                             **{name: self.targets[name][0] for name in self.targets.keys()},
                             **{name: self.obstacles[name][0] for name in self.obstacles.keys()},
                             }

    def create_paddle(self, i, 
                        name=None, 
                        color=(127, 127, 127), 
                        density=10, 
                        vel=None, 
                        pos=None, 
                        ldamp=1, 
                        collidable=True, 
                        min_height=0, 
                        max_height=60,
                        home_paddle=True):
        if not self.multiagent:
            if pos is None:
                pos = (0, -self.length / 2 + 0.01) # start at home region
            # below code is for a random position
            # if pos is None: pos = ((np.random.rand() - 0.5) * 2 * (self.table_x_max), 
            #                        max(min_height,-self.length / 2) + (np.random.rand() * ((min(max_height,self.length / 2)) - (max(min_height,-self.length / 2)))))
        else:
            if pos is None: 
                if home_paddle:
                    pos = (0, -self.length / 2 + 0.01)
                else:
                    pos = (0, self.length / 2 - 0.01)
                    
        if vel is None: 
            vel = (np.random.rand() * (self.max_speed_start - self.min_speed_start) + self.min_speed_start,
                   np.random.rand() * (self.max_speed_start - self.min_speed_start) + self.min_speed_start)
        radius = self.paddle_radius
        paddle = self.world.CreateDynamicBody(
            fixtures=b2FixtureDef(
                shape=b2CircleShape(radius=radius),
                density=self.paddle_density,
                restitution = 1.0,
                filter=b2Filter (maskBits=1,
                                 categoryBits=1 if collidable else 0)),
            bullet=True,
            position=pos,
            # linearVelocity=0.0,
            linearDamping=ldamp
        )
        color =  color # randomize color
        default_paddle_name = "paddle" + str(i)
        paddle.gravityScale = 0
        return ((default_paddle_name, (paddle, color)) if name is None else (name, (paddle, color)))

    # puck = bouncing ball
    def create_puck(self, i, 
                        name=None, 
                        color=(127, 127, 127), 
                        radius=-1,
                        vel=None, 
                        pos=None, 
                        ldamp=2, 
                        collidable=True,
                        min_height=-30,
                        max_height=30):
        if not self.multiagent:
            # then we want it to start at the top, which is max_height, 0
            if pos is None: 
                x_pos = np.random.uniform(low=-self.width / 3, high=self.width / 3) # doesnt spawn at edges
                # (np.random.rand() - 0.5) * 2 * (self.table_x_max)
                pos = (x_pos,
                       min(max_height, self.length / 2) - 0.01)
        else: 
            if pos is None: 
                pos = ((np.random.rand() - 0.5) * 2 * (self.table_x_max), 
                       max(min_height,-self.length / 2) + (np.random.rand() * ((min(max_height,self.length / 2)) - (max(min_height,-self.length / 2)))))
        # print(name, pos, min_height, max_height)
        if not self.multiagent:
            if vel is None: 
                vel = (2 * np.random.rand() * (self.max_speed_start - self.min_speed_start) + self.min_speed_start,
                       -0.7)
                # with 1/4th p, add x vel
                if np.random.rand() < 0.25:
                    (-1,
                     2 * np.random.rand() * (self.max_speed_start - self.min_speed_start) + self.min_speed_start)
                else:
                    (-1, 0)
        else:
            if vel is None: 
                vel = (np.random.rand() * (self.max_speed_start - self.min_speed_start) + self.min_speed_start,
                       10 * np.random.rand() * (self.max_speed_start - self.min_speed_start) + self.min_speed_start)
        if radius < 0: 
            # radius = max(1, np.random.rand() * (self.width/ 2))
            # radius = self.width / 5.325
            radius = self.puck_radius
        puck = self.world.CreateDynamicBody(
            fixtures=b2FixtureDef(
                shape=b2CircleShape(radius=radius),
                density=self.puck_density,
                restitution = 1.0,
                filter=b2Filter (maskBits=1,
                                 categoryBits=1 if collidable else 0)),
            bullet=True,
            position=pos,
            linearVelocity=vel,
            linearDamping=ldamp
        )
        color =  color # randomize color
        puck_name = "puck" + str(i)
        return ((puck_name, (puck, color)) if name is None else (name, (puck, color)))

    def create_block_type(self, i, name=None,name_type=None, color=(127, 127, 127), width=-1, height=-1, vel=None, pos=None, dynamic=True, angle=0, angular_vel=0, fixed_rotation=False, collidable=True, min_height=-30):
        if pos is None: pos = ((np.random.rand() - 0.5) * 2 * (self.table_x_max), min_height + (np.random.rand() * (self.length - (min_height + self.length / 2))))
        if vel is None: vel = ((np.random.rand() - 0.5) * 2 * (self.width),(np.random.rand() - 0.5) * 2 * (self.length))
        if not dynamic: vel = np.zeros((2,))
        if width < 0: width = max(0.75, np.random.rand() * 3)
        if height < 0: height = max(0.5, np.random.rand())
        # TODO: possibly create obstacles of arbitrary shape
        vertices = [([-width / 2, -height / 2]), ([width / 2, -height / 2]), ([width / 2, height / 2]), ([-width / 2, height / 2])]
        block_name  = name_type # Block, Obstacle, Target

        fixture = b2FixtureDef(
            shape=b2PolygonShape(vertices=vertices),
            density=1,
            restitution=0.1,
            filter=b2Filter (maskBits=1,
                                 categoryBits=1 if collidable else 0),
        )

        body = self.world.CreateBody(type=b2_dynamicBody if dynamic else b2_staticBody,
                                    position=pos,
                                    linearVelocity=vel,
                                    angularVelocity=angular_vel,
                                    angle=angle,
                                    fixtures=fixture,
                                    fixedRotation=fixed_rotation,
                                    )
        color =  color # randomize color
        block_name = block_name + str(i)
        return (block_name if name is None else name), (body, color)
    
    # def convert_to_box2d_coords(self, x, y):
    #     return (x, -y)

    def has_finished(self, multiagent=False):
        truncated = False
        terminated = False
        puck_within_alt_home = False
        puck_within_home = False

        if self.current_timestep > self.max_timesteps:
            terminated = True
        else:
            if self.terminate_on_out_of_bounds and self.paddles['paddle_ego'][0].position[1] > 0: 
                truncated = True

        # confusing, but we need to swap x and y for this function
        bottom_center_point = np.array([-self.length / 2, 0])
        top_center_point = np.array([self.length / 2, 0])
        puck_within_home = self.is_within_home_region(bottom_center_point, self.pucks[self.puck_names[0]][0])
        puck_within_alt_home = self.is_within_home_region(top_center_point, self.pucks[self.puck_names[0]][0])
        
        if self.terminate_on_enemy_goal:
            if not terminated and puck_within_home:
                truncated = True

        if multiagent:
            terminated = terminated or truncated or puck_within_alt_home or puck_within_home
            truncated = False

        puck_within_ego_goal = False
        puck_within_alt_goal = False

        if self.goal_conditioned:
            if self.is_within_goal_region(self.ego_goal_pos, self.pucks[self.puck_names[0]][0], self.ego_goal_radius):
                puck_within_ego_goal = True
            if multiagent:
                if self.is_within_goal_region(self.alt_goal_pos, self.pucks[self.puck_names[0]][0], self.alt_goal_radius):
                    puck_within_alt_goal = True

        return terminated, truncated, puck_within_home, puck_within_alt_home, puck_within_ego_goal, puck_within_alt_goal
    
    def get_goal_region_reward(self, point, body, radius, discrete=True) -> float:
        point = np.array([point[1], point[0]])
        dist = np.linalg.norm(body.position - point)
        
        if discrete:
            return 1.0 if dist < radius else 0.0
        # also return float from [0, 1] 0 being far 1 being the point
        # use sigmoid function because being closer is much more important than being far
        sigmoid_scale = 2
        reward_raw = 1 - (dist / radius)
        reward = 1 / (1 + np.exp(-reward_raw * sigmoid_scale))
        reward = 0 if dist >= radius else reward
        return reward

    def get_home_region_reward(self, point, body, discrete=True) -> float:
        # this is for the two base regions of each side of the eboard
        # TODO: this may need to be tuned :) let's provide a rough estimate of where the goal is
        # 90 / 560 = 0.16 <- normalized dist in pixels
        return self.get_goal_region_reward(point, body, 0.16 * self.width, discrete=discrete)
    
    def is_within_goal_region(self, point, body, radius) -> bool:
        point = np.array([point[1], point[0]])
        dist = np.linalg.norm(body.position - point)
        return dist < radius
    
    def is_within_home_region(self, point, body) -> bool:
        return self.is_within_goal_region(point, body, 0.16 * self.width)

    def get_reward(self, hit_a_puck, puck_within_home, 
                       puck_within_alt_home, puck_within_goal,
                       goal_pos, goal_radius):
        if self.reward_type == 'goal_discrete':
            return self.get_goal_region_reward(goal_pos, self.pucks[self.puck_names[0]][0], 
                                                 goal_radius, discrete=True)
        elif self.reward_type == 'goal_position' or self.reward_type == 'goal_position_velocity':
            # return self.get_goal_region_reward(goal_pos, self.pucks[self.puck_names[0]][0], 
            #                                      goal_radius, discrete=False)
            return self.compute_reward(self.get_achieved_goal(), self.get_desired_goal(), {})
        elif self.reward_type == 'puck_height':
            reward = self.pucks[self.puck_names[0]][0].position[1]
            # min acceptable reward is 0 height and above
            reward = max(reward, 0)
            # let's normalize reward w.r.t. the top half length of the table
            # aka within the range [0, self.length / 2]
            max_rew = self.length / 2
            min_rew = 0
            reward = (reward - min_rew) / (max_rew - min_rew)
            return reward
        elif self.reward_type == 'puck_vel':
        # reward for positive velocity towards the top of the board
            reward = self.pucks[self.puck_names[0]][0].linearVelocity[1]
            
            max_rew = 2 # estimated max vel
            min_rew = 0  # min acceptable good velocity
            
            if reward < min_rew:
                return 0
            
            reward = min(reward, max_rew)
            reward = (reward - min_rew) / (max_rew - min_rew)
            return reward
        elif self.reward_type == 'puck_touch':
            reward = 1 if hit_a_puck else 0
            return reward
        elif self.reward_type == 'alt_home':
            reward = 1 if puck_within_alt_home else 0
            return reward
        else:
            raise ValueError("Invalid reward type defined in config.")
    
    def get_joint_reward(self, ego_hit_a_puck, alt_hit_a_puck, 
                         puck_within_ego_home, puck_within_alt_home,
                         puck_within_ego_goal, puck_within_alt_goal) -> tuple[float, float]:
        ego_reward = self.get_reward(ego_hit_a_puck, puck_within_ego_home, 
                                     puck_within_alt_home, puck_within_ego_goal,
                                     self.ego_goal_pos, self.ego_goal_radius)
        alt_reward = self.get_reward(alt_hit_a_puck, puck_within_alt_home,
                                     puck_within_ego_home, puck_within_alt_goal,
                                     self.alt_goal_pos, self.alt_goal_radius)
        return ego_reward, alt_reward
    
    def step(self, action, other_action=None, time_step=0.018):
        if not self.multiagent:
            obs, reward, is_finished, truncated, info = self.single_agent_step(action, time_step)
            if not self.goal_conditioned:
                return obs, reward, is_finished, truncated, info
            else:
                return {"observation": obs, "desired_goal": self.get_desired_goal(), "achieved_goal": self.get_achieved_goal()}, reward, is_finished, truncated, info
        else:
            return self.multi_step(action, time_step)

    # 20 hz timestep
    def single_agent_step(self, action, return_dict=True) -> tuple[np.ndarray, float, bool, bool, dict]:
        # action is delta position
        # let's use simple time-optimal control to figure out the force to apply
        delta_pos = np.array([action[0], action[1]])
        
        # first let's determine velocity
        vel = delta_pos / self.time_per_step
        vel_mag = np.linalg.norm(vel)
        vel_unit = vel / (vel_mag + 1e-8)

        if vel_mag > self.max_paddle_vel:
            vel = vel_unit * self.max_paddle_vel

        force = self.paddles['paddle_ego'][0].mass * vel / self.time_per_step
        force_mag = np.linalg.norm(force)
        force_unit = force / (force_mag + 1e-8)
        if force_mag > self.max_force_timestep:
            force = force_unit * self.max_force_timestep
            
        force = force.astype(float)
        # force = self.force_scaling * self.paddles['paddle_ego'][0].mass * np.array((action[0], action[1])).astype(float)
        if self.paddles['paddle_ego'][0].position[1] > 0: 
            force[1] = min(self.force_scaling * self.paddles['paddle_ego'][0].mass * action[1], 0)
        if 'paddle_ego' in self.paddles: 
            self.paddles['paddle_ego'][0].ApplyForceToCenter(force, True)

        # make it easier to turn around
        vel = np.array([self.paddles['paddle_ego'][0].linearVelocity[0], self.paddles['paddle_ego'][0].linearVelocity[1]])
        vel_mag = np.linalg.norm(vel)
        vel_unit = vel / (vel_mag + 1e-8)
        
        
        force = np.array(force).astype(float)
        force_mag = np.linalg.norm(force)
        force_unit_vec = force / (force_mag + 1e-8)

        # small negative reward for changing direction
        cosine_sim = np.dot(vel_unit, force_unit_vec) / (np.linalg.norm(vel_unit) * np.linalg.norm(force_unit_vec) + 1e-8)
        norm_cosine_sim = (cosine_sim + 1) / 2
        max_change_dir_rew = -0.05
        direction_rew = max_change_dir_rew * (1 - norm_cosine_sim)
        
        
        # if force_mag > 0:
        #     force_unit_vec = force / (force_mag + 1e-8)
        #     result = force_unit_vec * vel_mag / 4 # Don't transfer everything
        #     self.paddles['paddle_ego'][0].linearVelocity = b2Vec2(result[0], result[1])
            
        # keep velocity at a maximum value
        if vel_mag > self.max_paddle_vel:
            self.paddles['paddle_ego'][0].linearVelocity = b2Vec2(vel[0] / vel_mag * self.max_paddle_vel, vel[1] / vel_mag * self.max_paddle_vel)

        wall_rew = 0.0
        # determine if going to bump into wall
        if self.wall_bumping_rew != 0:
            bump_left = self.paddles['paddle_ego'][0].position[0] < self.table_x_min + self.paddle_radius
            bump_right = self.paddles['paddle_ego'][0].position[0] > self.table_x_max - self.paddle_radius
            bump_top = self.paddles['paddle_ego'][0].position[1] > self.length / 2 - self.paddle_radius
            bump_bottom = self.paddles['paddle_ego'][0].position[1] < -self.length / 2 + self.paddle_radius
            if bump_left or bump_right or bump_top or bump_bottom:
                wall_rew = self.wall_bumping_rew

        self.world.Step(self.time_per_step, 10, 10)
        contacts, contact_names = self.get_contacts()
        hit_a_puck = self.respond_contacts(contact_names)
        # hacky way of determing if puck was hit below TODO: fix later!
        hit_a_puck = np.any(contacts) # check if any are true
        is_finished, truncated, puck_within_home, puck_within_alt_home, puck_within_goal, _ = self.has_finished()
        if not truncated:
            reward = self.get_reward(hit_a_puck, puck_within_home, 
                                     puck_within_alt_home, puck_within_goal,
                                     self.ego_goal_pos, self.ego_goal_radius)
        else:
            reward = self.truncate_rew
        reward += wall_rew
        reward += direction_rew
        self.current_timestep += 1
        
        obs = self.get_current_observation()
        return obs, reward, is_finished, truncated, {}
    
    def multi_step(self, joint_action):
        action_ego, action_alt = joint_action
        force_ego = self.force_scaling * self.paddles['paddle_ego'][0].mass * np.array((action_ego[0], action_ego[1])).astype(float)
        force_alt = self.force_scaling * self.paddles['paddle_alt'][0].mass * np.array((action_alt[0], action_alt[1])).astype(float)
        
        # legacy code snippet
        if self.paddles['paddle_ego'][0].position[1] > 0: 
            force_ego[1] = min(self.force_scaling * self.paddles['paddle_ego'][0].mass * action_ego[1], 0)
        if self.paddles['paddle_alt'][0].position[1] < 0: 
            force_alt[1] = min(self.force_scaling * self.paddles['paddle_alt'][0].mass * action_alt[1], 0)

        self.paddles['paddle_ego'][0].ApplyForceToCenter(force_ego, True)
        self.paddles['paddle_alt'][0].ApplyForceToCenter(force_alt, True)

        self.world.Step(self.time_per_step, 10, 10)
        contacts, contact_names = self.get_contacts()
        hit_a_puck = self.respond_contacts(contact_names)
        
        # hacky way of determing if puck was hit below TODO: fix later!
        hit_a_puck = np.any(contacts) # check if any are true
        
        # TODO: fix later!
        ego_hit_a_puck = hit_a_puck
        alt_hit_a_puck = hit_a_puck
        
        is_finished, truncated, puck_within_home, puck_within_alt_home, puck_within_ego_goal, puck_within_alt_goal = self.has_finished(multiagent=True)
        ego_reward, alt_reward = self.get_joint_reward(ego_hit_a_puck, alt_hit_a_puck, 
                                                       puck_within_home, puck_within_alt_home, 
                                                       puck_within_ego_goal, puck_within_alt_goal)
        self.current_timestep += 1

        obs_ego, obs_alt = self.get_current_observation()

        return (obs_ego, obs_alt), (ego_reward, alt_reward), is_finished, truncated, {}

    def get_contacts(self):
        contacts = list()
        shape_pointers = ([self.paddles[bn][0] for bn in self.paddle_names]  + \
                         [self.pucks[bn][0] for bn in self.puck_names] + [self.blocks[pn][0] for pn in self.block_names] + \
                         [self.obstacles[pn][0] for pn in self.obstacle_names] + [self.targets[pn][0] for pn in self.target_names])
        names = self.paddle_names + self.puck_names + self.block_names + self.obstacle_names + self.target_names
        # print(list(self.object_dict.keys()))
        contact_names = {n: list() for n in names}
        for bn in names:
            all_contacts = np.zeros(len(shape_pointers)).astype(bool)
            for contact in self.object_dict[bn].contacts:
                if contact.contact.touching:
                    contact_bool = np.array([(contact.other == bp and contact.contact.touching) for bp in shape_pointers])
                    contact_names[bn] += [sn for sn, bp in zip(names, shape_pointers) if (contact.other == bp)]
                else:
                    contact_bool = np.zeros(len(shape_pointers)).astype(bool)
                all_contacts += contact_bool
            contacts.append(all_contacts)
        return np.stack(contacts, axis=0), contact_names

    def respond_contacts(self, contact_names):
        hit_a_puck = list()
        for tn in self.target_names:
            for cn in contact_names[tn]: 
                if cn.find("puck") != -1:
                    hit_a_puck.append(cn)
        if self.absorb_target:
            for cn in hit_a_puck:
                self.world.DestroyBody(self.object_dict[cn])
                del self.object_dict[cn]
        return hit_a_puck # TODO: record a destroyed flag