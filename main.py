import sqlite3
import os
import json
import enum
import config as cfg
import argparse
import pickle
from conredis import ConRedis

class DBConnector:
    def __init__(self, db_path):
        self.db_path = db_path
        self.cur, self.conn = self.connect()

    def connect(self):
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        return cur, con

    def execute_many(self, query, values):
        return self.cur.executemany(query, values)

    def execute(self, query):
        return self.cur.execute(query).fetchall()

    def execute_value(self, query, value):
        return self.cur.execute(query, value)

    def commit(self):
        self.conn.commit()
        self.close_connection()

    def close_connection(self):
        self.cur.close()
        self.conn.close()


class DriverStats(enum.Enum):

    Cornering = 2
    Braking = 3
    Control = 4

    Smoothness = 5
    Adaptability = 6
    Overtaking = 7

    Defence = 8
    Acceleration = 9
    Accuracy = 10

class SeasonChanger(DBConnector):
    race_perf_table: str = 'Parts_RaceSimConstants'
    tyres_table: str = 'Tyres'
    drivers_table: str = 'Staff_DriverData'
    drivers_stats: str = 'Staff_PerformanceStats'
    teams_finances: str = 'Finance_TeamBalance'
    engine_manufacturers: str = 'Parts_Enum_EngineManufacturers'
    design_stats: str = 'Parts_DesignStatValues'
    track_perf: str = 'Races_TeamPerformance'

    def __init__(self, db_path: str, base_tyre_life: int, base_perf: int, tyre3set_perf_diff: float, tyre3set_life_diff: float, dirty_air: float, drs: float, slipstream: float, f1_cfg=cfg):
        super().__init__(db_path)
        self.base_tyre_life = base_tyre_life
        self.base_perf = base_perf
        self.tyre3set_perf_diff = tyre3set_perf_diff
        self.tyre3set_life_diff = tyre3set_life_diff
        self.dirty_air = dirty_air
        self.drs = drs
        self.slipstream = slipstream
        self.f1_cfg = cfg

    def get_tyre_life(self):
        query = 'SELECT Durability FROM tyres LIMIT 5;'
        return self.execute(query)

    def set_tyre_life(self, values: list):
        query = f'UPDATE {self.tyres_table} SET Durability = ? WHERE Type = ?;'
        for i, value in enumerate(values):
            params = (value, i)
            self.execute_value(query, params)

    def get_tyre_performance(self):
        query = 'SELECT grip FROM tyres LIMIT 5;'
        return self.execute(query)

    def set_tyre_performance(self, values: list):
        query = f'UPDATE {self.tyres_table} SET grip = ? WHERE Type = ?;'
        values.reverse()
        for i, value in enumerate(values):
            params = (value, i )
            self.execute_value(query, params)

    def get_dirty_air(self, base_params: str) -> dict:
        columns = ','.join([x for x in base_params['dirty_air']])
        query = f'SELECT {columns} FROM {self.race_perf_table}'
        query_results = self.execute(query)
        return query_results

    def set_dirty_air(self, base_params: dict):
        for x in base_params['dirty_air']:
            query = f'UPDATE {self.race_perf_table} SET {x} = ?;'
            value = base_params['dirty_air'][x]
            self.execute_value(query, (value,))

    def get_drs(self,):
        query = f"SELECT MaxDRSTopSpeedMultiplier FROM {self.race_perf_table};"
        return self.execute(query)

    def set_drs(self):
        # set drs multiplier
        query = f"UPDATE {self.race_perf_table} SET MaxDRSTopSpeedMultiplier = ?;"
        value = str(self.drs)
        self.execute_value(query, (value,))
        # set acceleration multiplier
        query = f"UPDATE {self.race_perf_table} SET MaxDRSAccelerationMultiplier = ?;"
        value = str(self.drs * 1.05)
        print("Accerellation set", value)
        self.execute_value(query, (value,))
        # set acceleration multiplier
        query = f"UPDATE {self.race_perf_table} SET MinDRSAccelerationMultiplier = ?;"
        value = str(1)
        self.execute_value(query, (value,))

    def get_slipstream(self):
        query = f"SELECT DirtyAirStraightSpeedMultiplier FROM {self.race_perf_table};"
        return self.execute(query)

    def set_slipstream(self):
        query = f'UPDATE {self.race_perf_table} SET DirtyAirStraightSpeedMultiplier = ?;'
        value = str(self.slipstream)
        self.execute_value(query, (value,))
        print("Slipstream set")

    def set_temp_increase_rate(self, base_params):
        query = f'UPDATE {self.tyres_table} SET TempIncRate = ? WHERE Type = ?;'
        for i in range(5):
            params = (base_params['TempIncRate'] + (i / 20), i)
            self.cur.execute(query, params)

    def set_temp_decrease_rate(self, base_params):
        query = f'UPDATE {self.tyres_table} SET TempDecRate = ? WHERE Type = ?;'
        for i in range(5):
            params = (base_params['TempDecRate'] + (i / 25), i)
            self.cur.execute(query, params)

    def set_min_extreme_wear(self, base_params):
        query = f'UPDATE {self.tyres_table} SET MinExtremeWear = ? WHERE Type = ?;'
        for i in range(5):
            params = (base_params['MinExtremeWear'] + (i / 30), i)
            self.cur.execute(query, params)

    def set_max_extreme_wear(self, base_params):
        query = f'UPDATE {self.tyres_table} SET MaxExtremeWear = ? WHERE Type = ?;'
        for i in range(5):
            params = (base_params['MaxExtremeWear'] + (i / 100), i)
            self.cur.execute(query, params)

    def set_min_optimal_wear(self, base_params):
        query = f'UPDATE {self.tyres_table} SET MinOptimalWear = ? WHERE Type = ?;'
        for i in range(5):
            params = (base_params['MinOptimalWear'] + (i / 30), i)
            self.cur.execute(query, params)

    def set_max_optimal_wear(self, base_params):
        query = f'UPDATE {self.tyres_table} SET MaxOptimalWear = ? WHERE Type = ?;'
        for i in range(5):
            params = (base_params['MaxOptimalWear'] + (i / 100), i)
            self.cur.execute(query, params)

    def set_min_optimal_grip(self, base_params):
        query = f'UPDATE {self.tyres_table} SET MinOptimalGrip = ? WHERE Type = ?;'
        for i in range(5):
            params = (base_params['MinOptimalGrip'] + (i / 7.5), i)
            self.cur.execute(query, params)

    def set_max_optimal_grip(self, base_params):
        query = f'UPDATE {self.tyres_table} SET MaxOptimalGrip = ? WHERE Type = ?;'
        for i in range(5):
            params = (base_params['MaxOptimalGrip'] + (i / 10), i)
            self.cur.execute(query, params)

    def set_min_extreme_grip(self, base_params):
        query = f'UPDATE {self.tyres_table} SET MinExtremeGrip = ? WHERE Type = ?;'
        for i in range(5):
            params = (base_params['MinExtremeGrip'] + (i / 20), i)
            self.cur.execute(query, params)

    def set_max_extreme_grip(self, base_params):
        query = f'UPDATE {self.tyres_table} SET MaxExtremeGrip = ? WHERE Type = ?;'
        for i in range(5):
            params = (base_params['MaxExtremeGrip'] + (i / 15), i)
            self.cur.execute(query, params)

    def set_tyre_tempswear(self, base_params):
        columns = ' = ?, '.join([x for x in base_params])
        values = tuple([base_params[x] for x in base_params])
        query = f"UPDATE {self.tyres_table} SET {columns} = ?;"
        self.execute_many(query, [values])

    def calculate_tyre_life(self):
        perf_range = self.tyre3set_life_diff
        base_modifier = self.base_tyre_life
        perf_mult = perf_range / 3
        values = [base_modifier]
        for i in range(1,5):
            values.append(base_modifier - (perf_mult * i))
        self.set_tyre_life(values)
        print("Tyre life values set")

    def calculate_tyre_performance(self):
        perf_range = self.tyre3set_perf_diff
        base_modifier = self.base_perf
        perf_mult = perf_range / 3
        values = [base_modifier]
        for i in range(1,5):
            values.append(base_modifier - (perf_mult * i))
        self.set_tyre_performance(values)
        print("Tyre performance values set")

    def calculate_dirty_air(self):
        perf_range = self.dirty_air
        if not perf_range > 0:
            print('Performance range must be greater than 0')
            return None
        base_params = {'dirty_air': {'DirtyAirLowSpeedMultiplier': 0.98, 'DirtyAirMediumSpeedMultiplier': 0.98, 'DirtyAirHighSpeedMultiplier': 0.98}}
        # Calculate the total ratio of the speed categories
        total_ratio = sum(base_params['dirty_air'].values())

        # Calculate the reduction amount for each speed category while maintaining their ratios
        low_speed_reduction = base_params['dirty_air']['DirtyAirLowSpeedMultiplier'] / total_ratio * perf_range
        medium_speed_reduction = base_params['dirty_air']['DirtyAirMediumSpeedMultiplier'] / total_ratio * perf_range
        high_speed_reduction = base_params['dirty_air']['DirtyAirHighSpeedMultiplier'] / total_ratio * perf_range

        # Reduce the values of the speed categories by the calculated amounts while maintaining their ratios
        if perf_range > 0:
            base_params['dirty_air']['DirtyAirLowSpeedMultiplier'] -= low_speed_reduction
            base_params['dirty_air']['DirtyAirMediumSpeedMultiplier'] -= medium_speed_reduction
            base_params['dirty_air']['DirtyAirHighSpeedMultiplier'] -= high_speed_reduction
        else:
            base_params['dirty_air']['DirtyAirLowSpeedMultiplier'] += low_speed_reduction
            base_params['dirty_air']['DirtyAirMediumSpeedMultiplier'] += medium_speed_reduction
            base_params['dirty_air']['DirtyAirHighSpeedMultiplier'] += high_speed_reduction
        self.set_dirty_air(base_params)
        print("Dirty air values set")

    def calculate_tyre_tempswear(self):
        base_params = {'TempIncRate': ARGS.temp_inc_rate, 'TempDecRate':ARGS.temp_dec_rate, 'MinExtremeWear': ARGS.min_extreme_wear, 'MaxExtremeWear': ARGS.max_extreme_wear,
                       'MinOptimalWear': ARGS.min_optimal_wear, 'MaxOptimalWear': ARGS.max_optimal_wear, 'MinOptimalGrip': ARGS.min_optimal_grip, 'MaxOptimalGrip': ARGS.max_optimal_grip,
                       'MinExtremeGrip': ARGS.min_extreme_grip, 'MaxExtremeGrip': ARGS.max_extreme_grip}

        self.set_tyre_tempswear(base_params)
        # tyre wear increases when in extreme temp range
        self.set_max_extreme_wear(base_params)
        self.set_min_extreme_wear(base_params)
        # tyre wear decreases when in extreme temp range
        self.set_max_optimal_wear(base_params)
        self.set_min_optimal_wear(base_params)
        # tyre grip increases when in optimal temp range
        self.set_max_optimal_grip(base_params)
        self.set_min_optimal_grip(base_params)
        # grip falls off when tyres is overheating
        self.set_max_extreme_grip(base_params)
        self.set_min_extreme_grip(base_params)
        # tyres heat up faster and cool down faster depending on tyre compound
        self.set_temp_increase_rate(base_params)
        self.set_temp_decrease_rate(base_params)
        print("Tyre tempswear values set")


    def set_driver_data(self):
        # mapping guide
        driver_stat_dict = dict(DriverStats.__members__)

        # load  json
        dir = os.path.join(os.getcwd(), 'drivers', 'F1_22.json')
        with open(dir, 'r') as f:
            data = json.load(f)

        for x in data:

            _id = f'[DriverCode_{x["ID"].lower().capitalize()}]'
            # get driver StaffID  from drivers_table
            query = f"SELECT StaffID FROM {self.drivers_table} WHERE DriverCode = ?;"
            staff_id = self.execute_value(query, (_id,)).fetchone()[0]
            stats = dict(list(x.items())[2:])

            for y in stats:
                y = y.capitalize()
                query = f"UPDATE {self.drivers_stats} SET Val = ? WHERE StaffID = ? and StatID = ? ;"
                value = stats[y.lower()]
                stat_id = driver_stat_dict[y].value
                self.execute_value(query, (value, staff_id, stat_id))

        print("Driver stats set")

    def team_cash_infusion(self):
        # jeff bezos and elon musk decide to give each team half a billion dollars
        query = f"UPDATE {self.teams_finances} SET Balance = Balance + 500000000;"
        self.execute(query)
        print("Team cash infusion complete")

    def calculate_tyre_strategy(self):
        # TODO: Offset pitstop strategy by tyre duraiton lap

        pass

    def equal_engines(self):
        # from engine manufacturers table select EngineDesignID
        query = f"SELECT EngineDesignID FROM {self.engine_manufacturers};"
        engine_design_ids = self.execute(query)
        print('engine ids', engine_design_ids)
        # set engine stats in parts_design table
        # from engine manufacturers table select ErsDesignID
        query = f"SELECT ErsDesignID FROM {self.engine_manufacturers};"
        ers_design_ids = self.execute(query)
        print('ers ids', ers_design_ids)
        # from engine manufacturers table select gearboxDesignID
        query = f"SELECT GearboxDesignID FROM {self.engine_manufacturers};"
        gearbox_design_ids = self.execute(query)
        print('gearbox ids', gearbox_design_ids)
        # from engine manufacturers table select FuelDesignID

        base_unit_value = 100
        base_value = 1000
        for i, x in enumerate(engine_design_ids):
            query = "SELECT DesignID, StatID, Value, UnitValue FROM Parts_DesignStatValues WHERE DesignID = ? "
            result = self.execute_value(query, (x[0],)).fetchall()
            for j, y in enumerate(result):
                # update UnitValue in Parts_DesignStatValues where DesignID = ? and StatID = ?
                query = f"UPDATE {self.design_stats} SET UnitValue = ? WHERE DesignID = ? and StatID = ?;"
                self.execute_value(query, (base_unit_value, result[j][0], result[j][1]))
                # update Value in Parts_DesignStatValues where DesignID = ? and StatID = ?
                query = f"UPDATE {self.design_stats} SET Value = ? WHERE DesignID = ? and StatID = ?;"
                self.execute_value(query, (base_value, result[j][0], result[j][1]))

        for i, x in enumerate(ers_design_ids):
            query = "SELECT DesignID, StatID, Value, UnitValue FROM Parts_DesignStatValues WHERE DesignID = ? "
            result = self.execute_value(query, (x[0],)).fetchall()
            for j, y in enumerate(result):
                # update UnitValue in Parts_DesignStatValues where DesignID = ? and StatID = ?
                query = f"UPDATE {self.design_stats} SET UnitValue = ? WHERE DesignID = ? and StatID = ?;"
                self.execute_value(query, (base_unit_value, result[j][0], result[j][1]))
                # update Value in Parts_DesignStatValues where DesignID = ? and StatID = ?
                query = f"UPDATE {self.design_stats} SET Value = ? WHERE DesignID = ? and StatID = ?;"
                self.execute_value(query, (base_value, result[j][0], result[j][1]))

        for i, x in enumerate(ers_design_ids):
            query = "SELECT DesignID, StatID, Value, UnitValue FROM Parts_DesignStatValues WHERE DesignID = ? "
            result = self.execute_value(query, (x[0],)).fetchall()
            for j, y in enumerate(result):
                # update UnitValue in Parts_DesignStatValues where DesignID = ? and StatID = ?
                query = f"UPDATE {self.design_stats} SET UnitValue = ? WHERE DesignID = ? and StatID = ?;"
                self.execute_value(query, (base_unit_value, result[j][0], result[j][1]))
                # update Value in Parts_DesignStatValues where DesignID = ? and StatID = ?
                query = f"UPDATE {self.design_stats} SET Value = ? WHERE DesignID = ? and StatID = ?;"
                self.execute_value(query, (base_value, result[j][0], result[j][1]))


    def equal_stats(self):
        # teams will start with a baseline equal car will be affected by development team
        base_unit_value = 25
        base_value = 250
        # update UnitValue Parts_DesignStatValues SET UnitValue = 90 ;
        query = f"UPDATE {self.design_stats} SET UnitValue = ?;"
        self.execute_value(query, (base_unit_value,))
        # update Value Parts_DesignStatValues SET Value = 950 ;
        query = f"UPDATE {self.design_stats} SET Value = ?;"
        self.execute_value(query, (base_value,))
        print("Stats equalised")

    def equal_track_stats(self):
        query = f"UPDATE {self.track_perf} SET Straights = 1.0;"
        self.execute(query)
        query = f"UPDATE {self.track_perf} SET SlowCorners = 1.0;"
        self.execute(query)
        query = f"UPDATE {self.track_perf} SET FastCorners = 1.0;"
        self.execute(query)
        query = f"UPDATE {self.track_perf} SET MediumCorners = 1.0;"
        self.execute(query)
        print("Track stats equalised")


def pack_object(obj):
    return pickle.dumps(obj)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='F1 2021 Season Changer')
    parser.add_argument('--save', type=str, default='autosave.sav', help='the name of the save to extract from and overwrite')
    parser.add_argument('--base_tl', type=float, default=0.95, help='base tyre life')
    parser.add_argument('--base_perf', type=float, default=1.0, help='base tyre performance')
    parser.add_argument('--tperf_diff', type=float, default=0.40, help='base tyre performance')
    parser.add_argument('--tlife_diff', type=float, default=0.25, help='tyre performance difference between 3 set of tyres')
    parser.add_argument('--dirty_air', type=float, default=0.2, help='dirty air performance reduction')

    parser.add_argument('--temp_inc_rate', type=float, default=2, help='tyre temperature increase rate')
    parser.add_argument('--temp_dec_rate', type=float, default=0.01, help='tyre temperature decrease rate')

    parser.add_argument('--min_extreme_wear', type=float, default=0.4, help='min tyre wear in extreme temp range')
    parser.add_argument('--max_extreme_wear', type=float, default=0.6, help='max tyre wear in extreme temp range')
    parser.add_argument('--min_optimal_wear', type=float, default=0.15, help='min tyre wear in optimal temp range')
    parser.add_argument('--max_optimal_wear', type=float, default=0.30, help='max tyre wear in optimal temp range')
    parser.add_argument('--min_optimal_grip', type=float, default=0.65, help='min tyre grip in optimal temp range')
    parser.add_argument('--max_optimal_grip', type=float, default=0.85, help='max tyre grip in optimal temp range')
    parser.add_argument('--min_extreme_grip', type=float, default=0.45, help='min tyre grip in extreme temp range')
    parser.add_argument('--max_extreme_grip', type=float, default=0.70, help='max tyre grip in extreme temp range')
    parser.add_argument('--load_season', type=str, default=None, help='load a previous instance you created from redis')
    parser.add_argument('--save_season', type=str, default=None, help='save the current instance to redis')

    parser.add_argument('--drs', type=float, default=1.0005, help='Drs performance')
    parser.add_argument('--slipstream', type=float, default=1.0, help='slipstream performance')
    ARGS = parser.parse_args()

    # save folder location
    save_folder = cfg.save_folder
    db_dir = os.path.join(save_folder, 'result', 'main.db')

    # conredis
    redis = ConRedis()

    #xAranaktu script to unpack to extract autosave
    script_dir = os.path.join(os.getcwd(), 'utils', 'script.py')
    result_dir = os.path.join(save_folder, 'result')
    autosave_dir = os.path.join(save_folder, 'autosave.sav')
    os_cmd = f'python "{script_dir}" --operation unpack --input "{autosave_dir}" --result "{result_dir}"'
    os.system(os_cmd)
    print("Unpacked autosave")

    # example load from redis
    if ARGS.load_season is not None:
        season_v1 = redis.retrieve_object_from_redis('season_v1')
    else:
        # example
        season_v1 = SeasonChanger(db_path=db_dir,
                                  base_tyre_life=ARGS.base_tl,
                                  base_perf=ARGS.base_perf,
                                  tyre3set_perf_diff=ARGS.tperf_diff,
                                  tyre3set_life_diff=ARGS.tlife_diff,
                                  dirty_air=ARGS.dirty_air,
                                  drs=ARGS.drs,
                                  slipstream=ARGS.slipstream,)

    # # calculate new values and assign them to the database
    season_v1.equal_stats()
    season_v1.equal_track_stats()
    season_v1.equal_engines()
    season_v1.calculate_dirty_air()
    season_v1.calculate_tyre_performance()
    season_v1.calculate_tyre_life()
    season_v1.calculate_tyre_tempswear()
    season_v1.set_drs()
    season_v1.set_slipstream()
    season_v1.set_driver_data()
    season_v1.team_cash_infusion()
    season_v1.commit()
    print("Committed changes")
    # # TODO: save season object to redis that can be later loaded if you need to roll back
    if ARGS.save_season is not None:
        redis.dump_object_to_redis('season_v1', season_v1)
    print("Saved season object to redis")
    # #xAranaktu script to pack back to save
    os_cmd = f'python "{script_dir}" --operation repack --result "{autosave_dir}" --input {result_dir}'
    os.system(os_cmd)
    print("Done repacking, have fun!")