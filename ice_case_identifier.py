import pandas as pd
import numpy as np
# for testing
import matplotlib.pyplot as plt



def temperature_correction(data,elevation):
    kelvin = 273.15
    temp_std = 288.15
    # density_correction = ((line[self.temp_index]+kelvin)*p_std)/(temp_std*(p_std*((1-self.site_elevation*2.2557e-5)**5.25588)))
    density_correction = ((temp_std/(data['ambient_temperature']+kelvin))*((1-elevation*2.2557e-5)**5.25588))**(1/3)
    ws_correct_noname = data['wind_speed'].mul(density_correction)
    ws_correct = ws_correct_noname.rename('wind_speed_c')
    new_data = pd.merge(left=data, right=ws_correct, left_index=True, right_index=True)
    return new_data
    
    
def reference_dataset(dataset):
    temperature_filter_level = 3.0
    # these can probaably be hardcoded, esp. if ¨"other_manual" can be set from UI.
    reference_dataset_mask = (dataset["normal_operation"] == True) & (dataset["faults"] == False) & (dataset["icing_codes"] == False) & \
                        (dataset["curtailment"] == False) & (dataset["ice_detection"] == False) & (dataset["other_manual"] == False) & \
                        (dataset["ambient_temperature"] >= temperature_filter_level)
    reference_dataset = dataset[reference_dataset_mask]
    return reference_dataset

# print(reference_dataset.head())


def make_pc(reference_dataset):
    # this needs to be settable
    wind_bins = pd.interval_range(start=0, end=20, freq=1)
    # create binning for the dataset based on the corrected wind speed
    binning = pd.cut(reference_dataset['wind_speed_c'],wind_bins)
    binning_r = binning.rename("bin")
    # add bin index for every value in the dataset
    reference_dataset_b = pd.merge(left=reference_dataset, right=binning_r, left_index=True, right_index=True)

    print(reference_dataset_b)
    # group by bin, calculate bunch of statistics for each bin
    # aggregation functions are listed as ('name of result', function)
    pc = reference_dataset_b[["wind_speed_c","output_power","bin"]].groupby('bin',observed=False).agg([
        ('mean', 'mean'),
        ('P10', lambda x: x.quantile(0.1)),
        ('P90', lambda x: x.quantile(0.9)),
        ('std.dev','std'),
        ('max', 'max'),
        ('min', 'min'),
        ('count', 'count')
    ])
    print(pc[[('wind_speed_c','mean'),('output_power','mean'),('output_power','P10'),('output_power','P90')]])
    return pc
    

def ice_stop(dataset):
    # separate the points when the turbine has stopped from the other icing alarms
    # stop alarm power limit 
    stop_limit = 100
    # stop wind limit
    wind_limit = 3
    # Stops are events where we have an icing alarm, but the power is below a certain limit. 
    stop_mask = ((dataset['ice_alarm'] == 1.0) & (dataset['output_power'] <= stop_limit) &\
                (dataset['wind_speed'] >= wind_limit))
    dataset['stops'] = 1.0*stop_mask
    return dataset
    
    

def ice_det(dataset, pc):
    # maximum temperature for icing
    icing_alarm_limit = 1
    # minimum number of cosecutive alarms
    alarm_time_limit = 3
    # minimum wind speed for detection. Should be turbine cut-in wind speed
    minimum_wind_speed  = 3
    # interpoaltion cannot handle NaN
    pc_mask = ~(np.isnan(pc[('wind_speed_c','mean')]))
    # piecewise linear interpolation over the power curves to get the refrence values for alarm creation
    y10 = pc[pc_mask][('output_power','P10')].to_numpy()
    w = pc[pc_mask][('wind_speed_c','mean')].to_numpy()
    y = pc[pc_mask][('output_power','mean')].to_numpy()
    dataset['p10_ref'] = np.interp(dataset['wind_speed_c'].to_numpy(),w,y10)
    dataset['reference_power'] = np.interp(dataset['wind_speed_c'].to_numpy(),w,y)
    
    # Alarm limit need to conver this to (1,0) instead of booleans for the length filter to work.
    dataset['ice_alarm'] = 1.0*((dataset['output_power']<dataset['p10_ref']) & \
                                (dataset['ambient_temperature']<icing_alarm_limit) & \
                                (dataset['wind_speed'] >= minimum_wind_speed))
    
    # Identify changes in the 'alarm' column to segment sequences
    mask = dataset['ice_alarm'] != dataset['ice_alarm'].shift()
    # want group these by event length for length-based filtering
    group = mask.cumsum()

    # Apply transformation only to groups where 'alarm' == 1
    # mask detects where the value changes (from 0 to 1 or vice versa).
    # group assigns a unique group ID to each sequence.
    # groupby(group) groups consecutive values.
    # transform replaces each 1 in a group with the length of that group only if the group starts with 1.
    dataset['ice_alarm_duration'] = dataset.groupby(group)['ice_alarm'].transform(lambda x: len(x) if x.iloc[0] == 1 else x)
    # time filter, require at least 3 consequtive alarms
    dataset['ice_alarm_duration'] = dataset['ice_alarm_duration'].where(dataset['ice_alarm_duration'] >= alarm_time_limit, 0)
    dataset['ice_alarm'] = dataset['ice_alarm'].where(dataset['ice_alarm_duration'] >= alarm_time_limit, 0)
    
    #print(dataset.head())
    # fig, ax = plt.subplots(nrows=2,ncols=1,sharex=True)
    # dataset.plot.line(x='timestamp', y=['output_power','p10_ref','reference_power'],ax=ax[0])
    # dataset.plot.line(x='timestamp', y=['ice_alarm'],ax=ax[1])
    # plt.show()
    return dataset



if __name__ == '__main__':
    full_data = pd.read_csv("cleaned_file_fake_data2 (other_col_names).csv")

    new_wind = temperature_correction(full_data,100)
    print(new_wind.head())
    reference = reference_dataset(new_wind)
    pc = make_pc(reference)
    icing_data = ice_det(new_wind, pc)
    dataset = ice_stop(icing_data)
    fig, ax = plt.subplots(nrows=3,ncols=1,sharex=True)
    dataset.plot.line(x='timestamp', y=['output_power','p10_ref','reference_power'],ax=ax[0])
    dataset.plot.line(x='timestamp', y=['ice_alarm','stops'],ax=ax[1])
    dataset.plot.line(x='timestamp', y='wind_speed', ax=ax[2])
    dataset.plot.line(x='timestamp', y='ambient_temperature', ax=ax[2], secondary_y=True)
    pc.plot(x=('wind_speed_c','mean'), y=[('output_power','mean'),('output_power','P10'),('output_power','P90')])
    ax2 = plt.gca()
    dataset.plot.scatter(x="wind_speed_c",y='output_power',color='gray',alpha=0.1, ax=ax2)
    dataset[dataset['ice_alarm'] == 1].plot.scatter(x="wind_speed_c",y='output_power',color='red',alpha=0.1, ax=ax2)
    plt.show()

# timestamp,wind_speed,ambient_temperature,output_power,normal_operation,wind_direction,pressure,maintenance,faults,curtailment,other_manual,icing_codes,ice_detection,ips_status

# temperature / air density correction
