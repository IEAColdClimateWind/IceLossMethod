import pandas as pd
import numpy as np
# for testing
import matplotlib.pyplot as plt

class IceLossDetector:
    def __init__(self,dataframe):
        """
        These are default values for the ice detector
        Initialization neds now a default dataframe with hardcoded column titles.
        Idea is to use this internally to claulate the actual icign events and then ahve a separate method in the front
        To generate the dataframe
        
        """
        # original dataframe
        self.dataframe = dataframe
        # site speciffics:
        self.elevation = 100
        
        # binning settings
        self.low_wind_bin = 0
        self.high_wind_bin = 20
        self.wind_bin_size = 1
        
        # power curve limits
        self.low_quantile = 0.1
        self.high_quantile = 0.9
        
        
        # temperature limits
        # filter level for reference dataset making
        self.temperature_filter_level = 3 
        # icing alarm temperature level
        self.icing_alarm_limit = 1
        # other limits
        # numebr of consecutive events needed to trigger icing alarm
        self.alarm_time_limit = 3
        # minimum wind speed for ice dwetection, should be at least at turbine cut-in
        self.minimum_wind_speed = 3
        # power limit to determine if turbine has stopped
        self.stop_limit = 100
        
        

    def temperature_correction(self, data):
        kelvin = 273.15
        temp_std = 288.15
        # density_correction = ((line[self.temp_index]+kelvin)*p_std)/(temp_std*(p_std*((1-self.site_elevation*2.2557e-5)**5.25588)))
        density_correction = ((temp_std/(data['ambient_temperature']+kelvin))*((1-self.elevation*2.2557e-5)**5.25588))**(1/3)
        ws_correct_noname = data['wind_speed'].mul(density_correction)
        ws_correct = ws_correct_noname.rename('wind_speed_c')
        new_data = pd.merge(left=data, right=ws_correct, left_index=True, right_index=True)
        return new_data
        
        
    def reference_dataset(self, dataset):
        # these can probaably be hardcoded, esp. if ¨"other_manual" can be set from UI.
        reference_dataset_mask = (dataset["normal_operation"] == True) &\
                                (dataset["faults"] == False) & \
                                (dataset["icing_codes"] == False) & \
                                (dataset["curtailment"] == False) & \
                                (dataset["ice_detection"] == False) & \
                                (dataset["other_manual"] == False) & \
                                (dataset["ambient_temperature"] >= self.temperature_filter_level)
        reference_dataset = dataset[reference_dataset_mask]
        return reference_dataset

    # print(reference_dataset.head())


    def make_pc(self, reference_dataset):
        # this needs to be settable
        wind_bins = pd.interval_range(start=self.low_wind_bin, end=self.high_wind_bin, freq=self.wind_bin_size)
        # create binning for the dataset based on the corrected wind speed
        binning = pd.cut(reference_dataset['wind_speed_c'],wind_bins)
        binning_r = binning.rename("bin")
        # add bin index for every value in the dataset
        reference_dataset_b = pd.merge(left=reference_dataset, right=binning_r, left_index=True, right_index=True)

        # print(reference_dataset_b)
        # group by bin, calculate bunch of statistics for each bin
        # aggregation functions are listed as ('name of result', function)
        pc = reference_dataset_b[["wind_speed_c","output_power","bin"]].groupby('bin',observed=False).agg([
            ('mean', 'mean'),
            ('P10', lambda x: x.quantile(self.low_quantile)),
            ('P90', lambda x: x.quantile(self.high_quantile)),
            ('std.dev','std'),
            ('max', 'max'),
            ('min', 'min'),
            ('count', 'count')
        ])
        # print(pc[[('wind_speed_c','mean'),('output_power','mean'),('output_power','P10'),('output_power','P90')]])
        return pc
        

    def ice_stop(self, dataset):
        # separate the points when the turbine has stopped from the other icing alarms
        # Stops are events where we have an icing alarm, but the power is below a certain limit. 
        stop_mask = ((dataset['ice_alarm'] == 1.0) & (dataset['output_power'] <= self.stop_limit) &\
                    (dataset['wind_speed'] >= self.minimum_wind_speed))
        dataset['stops'] = 1.0*stop_mask
        return dataset
        
        

    def power_curve_ice_detection(self, dataset, pc):
        # interpoaltion cannot handle NaN
        pc_mask = ~(np.isnan(pc[('wind_speed_c','mean')]))
        # piecewise linear interpolation over the power curves to get the refrence values for alarm creation
        y10 = pc[pc_mask][('output_power','P10')].to_numpy()
        w = pc[pc_mask][('wind_speed_c','mean')].to_numpy()
        y = pc[pc_mask][('output_power','mean')].to_numpy()
        dataset['p10_ref'] = np.interp(dataset['wind_speed_c'].to_numpy(),w,y10)
        dataset['reference_power'] = np.interp(dataset['wind_speed_c'].to_numpy(),w,y)
        
        # Alarm limit need to conver this to (1,0) instead of booleans for the length filter to work.
        dataset['ice_alarm'] = 1.0*((dataset['output_power'] < dataset['p10_ref']) & \
                                    (dataset['ambient_temperature'] < self.icing_alarm_limit) & \
                                    (dataset['wind_speed'] >= self.minimum_wind_speed) & \
                                    (dataset["normal_operation"] == True) & \
                                    (dataset["faults"] == False) & \
                                    (dataset["icing_codes"] == False) & \
                                    (dataset["curtailment"] == False) & \
                                    (dataset["ice_detection"] == False) & \
                                    (dataset["other_manual"] == False)
                                    )
        
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
        dataset['ice_alarm_duration'] = dataset['ice_alarm_duration'].where(dataset['ice_alarm_duration'] >= self.alarm_time_limit, 0)
        dataset['ice_alarm'] = dataset['ice_alarm'].where(dataset['ice_alarm_duration'] >= self.alarm_time_limit, 0)
        
        #print(dataset.head())
        # fig, ax = plt.subplots(nrows=2,ncols=1,sharex=True)
        # dataset.plot.line(x='timestamp', y=['output_power','p10_ref','reference_power'],ax=ax[0])
        # dataset.plot.line(x='timestamp', y=['ice_alarm'],ax=ax[1])
        # plt.show()
        # ToDo:
        # fix the return column names and datatypes, needs to be boolean
        return dataset
    
    
    
    def detect_icing_events(self):
        """
        run the correct sequence of functions and return the dataframe with icign events
        """
        temperature_corrected_data = self.temperature_correction(self.dataframe)
        reference = self.reference_dataset(temperature_corrected_data)
        pc = self.make_pc(reference)
        power_drops = self.power_curve_ice_detection(temperature_corrected_data, pc)
        icing_data = self.ice_stop(power_drops)
        return icing_data
    
    def make_power_curve(self):
        """
        make the refrence dataset and return the power curve for plotting etc.
        
        """
        temperature_corrected_data = self.temperature_correction(self.dataframe)
        reference = self.reference_dataset(temperature_corrected_data)
        pc = self.make_pc(reference)
        return pc



if __name__ == '__main__':
    full_data = pd.read_csv("cleaned_file_fake_data2 (other_col_names).csv")
    ice_det = IceLossDetector(full_data) 
    dataset = ice_det.detect_icing_events()
    pc = ice_det.make_power_curve()
    dataset.to_csv('output.csv')
    print(pc)
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
