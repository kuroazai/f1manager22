



# set percentage the overral difference between softest and hardest compound of 3 tyre choices in tyre life
tyre_life_diff = 0.5
# set percentage the overral difference between softest and hardest compound of 3 tyre choices in tyre performance
tyre_perf_diff = 0.75
# set baseline tyre life and performance
tyre_life = 1.5
tyre_perf = 2
drs = 1.5   # set drs multiplier



for i in range(5):
    tyre_life = tyre_life - (tyre_life_diff / 3)
    tyre_perf = tyre_perf - (tyre_perf_diff/ 3)
    print(tyre_life, tyre_perf)
