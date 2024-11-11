'''
Date: 2024-11-11 17:44:15
LastEditors: caishaofei-mus1 1744260356@qq.com
LastEditTime: 2024-11-11 19:27:54
FilePath: /MineStudio/minestudio/simulator/minerl/callbacks/rewards.py
'''

from minestudio.simulator.minerl.callbacks.callback import MinecraftCallback

class RewardsCallback(MinecraftCallback):
    
    def __init__(self, reward_cfg):
        super().__init__()
        """
        Examples:
            reward_cfg = [{
                "event": "kill_entity", 
                "identity": "kill sheep or cow", 
                "objects": ["sheep", "cow"], 
                "reward": 1.0, 
                "max_reward_times": 5, 
            }]
        """
        self.reward_cfg = reward_cfg
        self.prev_info = {}
        self.reward_memory = {}
    
    def after_reset(self, sim, obs, info):
        self.prev_info = {}
        self.reward_memory = {}
        return obs, info
    
    def after_step(self, sim, obs, reward, terminated, truncated, info):
        override_reward = 0.
        for reward_info in self.reward_cfg:
            event_type = reward_info['event']
            delta = 0
            for obj in reward_info['objects']:
                delta += self._get_obj_num(info, event_type, obj) - self._get_obj_num(self.prev_info, event_type, obj)
                if delta <= 0:
                    continue
                already_reward_times = self.reward_memory.get(reward_info['identity'], 0)
                if already_reward_times < reward_info['max_reward_times']:
                    override_reward += reward_info['reward']
                    self.reward_memory[reward_info['identity']] = already_reward_times + 1
                break
        self.prev_info = info
        return obs, override_reward, terminated, truncated, info

    def _get_obj_num(self, info, event_type, obj):
        if event_type not in info:
            return 0.
        if obj not in info[event_type]:
            return 0.
        res = info[event_type][obj]
        return res.item() if isinstance(res, np.ndarray) else res 