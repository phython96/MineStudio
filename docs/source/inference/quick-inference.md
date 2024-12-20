<!--
 * @Date: 2024-12-02 21:23:42
 * @LastEditors: muzhancun muzhancun@126.com
 * @LastEditTime: 2024-12-14 01:10:23
 * @FilePath: /MineStudio/docs/source/inference/quick-inference.md
-->

Here is a minimal example of how to use the inference framework:

```python
import ray
from minestudio.inference import EpisodePipeline, MineGenerator, InfoBaseFilter

from functools import partial
from minestudio.models import load_vpt_policy
from minestudio.simulator import MinecraftSim

if __name__ == '__main__':
    ray.init()
    env_generator = partial(
        MinecraftSim, 
        obs_size = (128, 128), 
        preferred_spawn_biome = "forest", 
    ) # generate the environment
    agent_generator = partial(
        load_vpt_policy,
        model_path = # provide the path to the model
        weights_path = # provide the path to the weights
    ) # generate the agent
    worker_kwargs = dict(
        env_generator = env_generator, 
        agent_generator = agent_generator,
        num_max_steps = 12000, # provide the maximum number of steps
        num_episodes = 2, # provide the number of episodes for each worker
        tmpdir = "./output",
        image_media = "h264",
    ) # provide the worker kwargs
    pipeline = EpisodePipeline(
        episode_generator = MineGenerator(
            num_workers = 8, # the number of workers
            num_gpus = 0.25, # the number of gpus
            max_restarts = 3, # the maximum number of restarts for failed workers
            **worker_kwargs, 
        ),
        episode_filter = InfoBaseFilter(
            key = "mine_block",
            val = "diamond_ore",
            num = 1,
        ), # InfoBaseFilter will label episodes mine more than 1 diamond_ore
    )
    summary = pipeline.run()
    print(summary)
```