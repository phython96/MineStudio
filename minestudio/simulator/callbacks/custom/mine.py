from minestudio.simulator.callbacks.callback import MinecraftCallback
from minestudio.simulator import MinecraftSim
import json
import uuid
import os
import cv2
from PIL import Image
import random
import numpy as np
from rich import print

class MineblockCallback(MinecraftCallback):
    """
        Use to generate env setting suitable for mining
        Examples:
            config = {
                "event": "mine_block",
                "structure": "village",
                "biomes": ["plains"],
                "time": 1000,
                "weather": "clear",
                "block": "iron_ore",
                "reward": 1.0,
                "inventory": {"iron_ore": 1},
                "main_hand": "minecraft:iron_pickaxe",
                "random_tp_range": 100, 
            }
    """
    def __init__(self, config, openai_client=None, model=None):
        super().__init__()
        self.config = config
        self.prev_info = {}
        self.client = openai_client
        self.model = model
    
    def _fast_reset(self, sim):
        biome = self.config['biome']
        x = np.random.randint(-self.config['random_tp_range'] // 2, self.config['random_tp_range'] // 2)
        z = np.random.randint(-self.config['random_tp_range'] // 2, self.config['random_tp_range'] // 2)

        if self.config['world'] == "nether":
            command = "/setblock ~ ~1 ~ minecraft:nether_portal"
        elif self.config['world'] == "end":
            command = "/setblock ~ ~1 ~ minecraft:end_portal"
        else:
            command = None

        fast_reset_commands = [
            "/effect give @s minecraft:night_vision 99999 1 true",
            "/effect give @s minecraft:water_breathing 99999 1 true",
            "/effect give @s minecraft:fire_resistance 99999 1 true",
            "/gamemode creative"
        ]
        if command is not None:
            fast_reset_commands.append(command)
        fast_reset_commands.extend([
            f"/time set {self.config['time']}",
            f"/weather {self.config['weather']}",
            f"/teleportbiome @a {biome} {x} ~0 {z}"
        ])
        for command in fast_reset_commands:
            obs, _, done, info = sim.env.execute_cmd(command)
        return False

    def after_reset(self, sim, obs, info):
        self.prev_info = {}

        self._fast_reset(sim)

        # do a attack action
        obs, _, _, info = sim.env.execute_cmd("/fill ~ ~ ~ ~1 ~1 ~1 air")

        # dig for {underground} blocks
        obs, _, _, info = sim.env.execute_cmd(f"/fill ~ ~ ~ ~ ~-{self.config['underground']} ~ air")

        # randomly choose facing direction from 0 to 90.0
        facing = int(random.uniform(-90.0, 90.0))
        if self.config['in_air']:
            facing = int(random.uniform(-45.0, 90.0))
        if self.config['underground'] == 0:
            facing = int(random.uniform(-45.0, 45.0))
        obs, _, _, info = sim.env.execute_cmd(f"/tp @s ~ ~-{self.config['underground']} ~ -90 {facing}")

        prev_y = None
        repeat_times = 20
        while (repeat_times > 0 and self.config['underground'] < 0):
            repeat_times -= 1
            for _ in range(5):
                obs, _, _, _, info = sim.step(sim.noop_action())
            # import ipdb; ipdb.set_trace()
            if prev_y is not None and abs(info['player_pos']['y'] - prev_y) < 1:
                break
            prev_y = info['player_pos']['y']
        obs, _, _, info = sim.env.execute_cmd(f"/tp @s ~ ~ ~ -90 {facing}")
        if self.config['generate_block']:
            # place the target block
            if  0 <= facing < 45:
                # randomly choose the y coordinate
                if self.config['in_air']:
                    y = random.choice([-1, 0, 1])
                else:
                    y = random.choice([0, 1])
                if self.config['underground'] == 0:
                    x = random.choice([1, 5])
                else:
                    x = 1
                obs, _, _, info = sim.env.execute_cmd(f"/setblock ~{x} ~{y} ~ {self.config['block']}")
            elif facing >= 45:
                # randomly choose y to be -1 or 0
                y = random.choice([-1, 0])
                if y == -1:
                    obs, _, _, info = sim.env.execute_cmd(f"/setblock ~ ~{y} ~ {self.config['block']}")
                else:
                    obs, _, _, info = sim.env.execute_cmd(f"/setblock ~1 ~{y} ~ {self.config['block']}")
            elif -45 <= facing < 0:
                # randomly choose y coordinate from 0 to 2
                if self.config['in_air']:
                    y = random.choice([0, 1, 2])
                else:
                    y = 0
                if self.config['underground'] == 0:
                    x = random.choice([1, 5])
                else:
                    x = 1
                obs, _, _, info = sim.env.execute_cmd(f"/setblock ~{x} ~{y} ~ {self.config['block']}")
            elif facing < -45:
                # randomly choose y coordinate from 2 to 3
                y = random.choice([2, 3])
                obs, _, _, info = sim.env.execute_cmd(f"/setblock ~1 ~{y} ~ {self.config['block']}")

        # come back to survival mode
        obs, _, _, info = sim.env.execute_cmd("/gamemode survival")

        for slot, item in self.config['armor'].items():
            if item == "":
                continue
            obs, _, _, info = sim.env.execute_cmd(f"/replaceitem entity @s {slot} {item}")

        for block, num in self.config['inventory'].items():
            obs, _, _, info = sim.env.execute_cmd(f"/give @s {block} {num}")

        obs, _, _, _, info = sim.step(sim.noop_action())
        self.prev_info = info.copy()
        # obs, info = sim._wrap_obs_info(obs, info)
        return obs, info
    
    def after_step(self, sim, obs, reward, terminated, truncated, info):
        override_reward = 0.
        event_type = self.config['event']
        block = self.config['block']
        delta = self._get_obj_num(info, event_type, block) - self._get_obj_num(self.prev_info, event_type, block)
        self.prev_info = info.copy()
        if delta <= 0:
            return obs, reward, terminated, truncated, info
        else:
            override_reward = self.config['reward']
            terminated = True
            return obs, override_reward, terminated, truncated, info
        
    def _get_obj_num(self, info, event_type, obj):
        if event_type not in info:
            return 0.
        if obj not in info[event_type].keys():
            return 0.
        res = info[event_type][obj]
        return res.item() if isinstance(res, np.ndarray) else res 

class MineEnvGenerator:
    def __init__(self, vlm_session, sam_session, config_path='./configs', obs_size=(224, 224), action_type="env"):
        self.config_path = config_path
        self.obs_size = obs_size
        self.action_type = action_type
        self.vlm_session = vlm_session
        self.sam_session = sam_session

    def generate_env(self, name = None):
        config_list = os.listdir(self.config_path)
        if name is None:
            name = random.choice(config_list)
        else:
            assert name in config_list, f"Config {name} not found in {self.config_path}"
        config = json.load(open(f'{self.config_path}/{name}'))
        if config is not None:
            config['generate_block'] = True
            config['event'] = "mine_block"
            config['random_tp_range'] = 20
            config['reward'] = 1.0

        sim = MinecraftSim(
            self.obs_size,
            self.action_type,
            callbacks=[
                MineblockCallback(config),
                # PlayCallback(),
            ]
        )

        return sim, name.split('.')[0]
    
    def validate_env(self, sim, name):
        obs, info = sim.reset()
        terminated = False
        obs, reward, terminated, truncated, info = sim.step(sim.noop_action())
        
        # use vision language model to validate the env
        prompt = f"Pinpoint the {name} block. If there is no {name} block, please return 'NONE', else return the coordinates of the {name} block. DO NOT OUTPUT ANYTHING ELSE."

        # get the image
        image = Image.from_array(info['pov'])
        output = self.vlm_session.gen_point(image, prompt)

        if output == "NONE":
            print(f"Validation failed for {name}")
            return False
        else:
            print(f"Validation passed for {name}")
            
            # use SAM to generate mask for the block
            mask = self.sam_session.load_first_frame(info['pov'])
            _, out_obj_ids, out_mask_logits = self.predictor.add_new_prompt(
                frame_idx=0, 
                obj_id=0,
                points=output,
                labels=[1 for _ in range(len(output))],
            )
            obj_mask = (out_mask_logits[0, 0] > 0.0).cpu().numpy()



if __name__ == "__main__":
    from minestudio.simulator import MinecraftSim
    from minestudio.simulator.callbacks import (
        PlayCallback, FastResetCallback
    )
    from openai import OpenAI
    import json
    import os
    from functools import partial

    # load configs from ./configs
    config_list = os.listdir('./configs')

    # randomly sample a config
    name = random.choice(config_list)
    config = json.load(open(f'./configs/{name}'))
    config['generate_block'] = True
    config['event'] = "mine_block"
    config['random_tp_range'] = 20
    config['reward'] = 1.0
    print(name, config)

    env_generator = partial(
        MinecraftSim,
        obs_size=(224, 224),
        action_type="env",
        callbacks=[
            MineblockCallback(config),
            PlayCallback(),
        ]
    )

    sim = env_generator()

    obs, info = sim.reset()
    terminated = False
    while not terminated:
        action = None
        obs, reward, terminated, truncated, info = sim.step(action)