import pandas as pd
import numpy as np
import json
# for testing
import matplotlib.pyplot as plt

class IceLossDetector(pd.DataFrame):
    
    _metadata = ["temperatureCorrectionApplied","parameters"]
    
    @property
    def _constructor(self):
        return IceLossDetector
    
    def __init__(self, *args, **kwargs):
        """
        These are default values for the ice detector
        Initialization neds now a default dataframe with hardcoded column titles.
        Idea is to use this internally to claulate the actual icign events and then ahve a separate method in the front
        To generate the dataframe
        
        """
        # initialize the DataFrame part
        super().__init__(*args, **kwargs)
        
        self.temperatureCorrectionApplied = False
        self.parameters = {}
        # site specifics
        self.parameters['turbine_name'] = 'unnamed turbine'
        self.parameters['rated_power'] = None #somewhere else in the code, when making the power curve check if None and replace value with max from PC
        self.parameters['hub_height'] = 80 #necessary?
        self.parameters['elevation'] = 100 #put to None? and handle it differently if not provided?
        
        # binning settings
        self.parameters['low_wind_bin'] = 0
        self.parameters['high_wind_bin']= 20
        self.parameters['wind_bin_size'] = 1
        
        # power curve limits
        self.parameters['low_quantile'] = 0.1
        self.parameters['high_quantile'] = 0.9
        
        # temperature limits
        self.parameters['temperature_filter_level'] = 3 
        self.parameters['icing_alarm_limit'] = 1
        
        # other limits
        self.parameters['alarm_time_limit'] = 3
        self.parameters['minimum_wind_speed'] = 3
        self.parameters['stop_limit'] = 100
        
    @classmethod
    def importFromCSV(cls, fileName):
        """
        Creates a IceLossDetector from a standard csv file generated from the import module
        
        """
        full_data = pd.read_csv(fileName,index_col=0)
        if not np.isin(['timestamp', 'wind_speed', 'ambient_temperature', 'output_power',
               'normal_operation', 'wind_direction', 'pressure', 'maintenance',
               'faults', 'curtailment', 'other_manual', 'icing_codes', 'ice_detection',
               'ips_status'],full_data.columns).all():
            ImportError('The provided CSV does not contain the required columns of the standard file')
            
        ice_det = IceLossDetector(full_data) 
        if not ice_det.isTenMinuteInterval():
            ImportError('Please provide 10-minute data')
        ice_det.retimeToTenMinute()
        return ice_det
        
    
    def isTenMinuteInterval(self):
        if not isinstance(self.index, pd.DatetimeIndex):
            self.index = pd.to_datetime(self.index)
        diffs = self.index.to_series().diff().dropna()
        mostFreq = diffs.mode()[0]
        return mostFreq == pd.Timedelta(minutes=10)
     
    def retimeToTenMinute(self):
        step = pd.Timedelta(minutes=10) 
        first = self.index.min()
        last = self.index.max()
        binStart = first + ((self.index - first) // step) * step
        out = self.groupby(binStart).mean(numeric_only=True).sort_index()
        lastBin = first + ((last - first) // step) * step
        fullIndex = pd.date_range(start=first, end=lastBin, freq=step)
        out = out.reindex(fullIndex)
        out.index.name = self.index.name
        return out                 

    def temperatureCorrection(self):
        if not self.temperatureCorrectionApplied:
            kelvin = 273.15
            temp_std = 288.15
            # density_correction = ((line[self.temp_index]+kelvin)*p_std)/(temp_std*(p_std*((1-self.site_elevation*2.2557e-5)**5.25588)))
            density_correction = ((temp_std/(self['ambient_temperature']+kelvin))*((1-self.parameters['elevation']*2.2557e-5)**5.25588))**(1/3)
            ws_correct_noname = self['wind_speed'].mul(density_correction)
            ws_correct = ws_correct_noname.rename('wind_speed_c')
            self.loc[:,'wind_speed_c'] = ws_correct
            self.temperatureCorrectionApplied =True
        #new_data = pd.merge(left=self, right=ws_correct, left_index=True, right_index=True)
        #return new_data
        
        
    def identifyReferenceDataset(self):
        # these can probaably be hardcoded, esp. if ¨"other_manual" can be set from UI.
        reference_dataset_mask = (self["normal_operation"] == True) &\
                                (self["faults"] == False) & \
                                (self["curtailment"] == False) & \
                                (self["other_manual"] == False) & \
                                (self["ambient_temperature"] >= self.parameters['temperature_filter_level'])
        #add option to remove ice detection and icing code from dataset
        #(self["icing_codes"] == False) & \
        #(self["ice_detection"] == False) & \
        self.loc[:,'referenceDatasetMask'] = reference_dataset_mask
        #reference_dataset = dataset[reference_dataset_mask]
        #return reference_dataset

    # print(reference_dataset.head())


    def makePowerCurve(self):
        self.temperatureCorrection()
        if 'referenceDatasetMask' not in self.columns:
            self.identifyReferenceDataset()
        reference_dataset = self.loc[self.loc[:,'referenceDatasetMask'],:]
        # this needs to be settable
        wind_bins = pd.interval_range(start=self.parameters['low_wind_bin'], end=self.parameters['high_wind_bin'], freq=self.parameters['wind_bin_size'])
        # create binning for the dataset based on the corrected wind speed
        binning = pd.cut(reference_dataset['wind_speed_c'],wind_bins)
        binning_r = binning.rename("bin")
        # add bin index for every value in the dataset
        reference_dataset_b = pd.merge(left=reference_dataset, right=binning_r, left_index=True, right_index=True)

        # print(reference_dataset_b)
        # group by bin, calculate bunch of statistics for each bin
        # aggregation functions are listed as ('name of result', function)
        # ToDo: change P10, P90 to something meaningful
        pc = reference_dataset_b[["wind_speed_c","output_power","bin"]].groupby('bin',observed=False).agg([
            ('mean', 'mean'),
            ('low_quantile', lambda x: x.quantile(self.parameters['low_quantile'])),
            ('high_quantile', lambda x: x.quantile(self.parameters['high_quantile'])),
            ('std.dev','std'),
            ('max', 'max'),
            ('min', 'min'),
            ('count', 'count')
        ])
        # print(pc[[('wind_speed_c','mean'),('output_power','mean'),('output_power','P10'),('output_power','P90')]])
        return pc
        

    def identifyIceStop(self):
        # separate the points when the turbine has stopped from the other icing alarms
        # Stops are events where we have an icing alarm, but the power is below a certain limit. 
        stop_mask = ((self['ice_alarm'] == 1.0) & (self['output_power'] <= self.parameters['stop_limit']) &\
                    (self['wind_speed'] >= self.parameters['minimum_wind_speed']))
        self['stops'] = 1.0*stop_mask
        #return dataset
        
    def addReferencePowerToData(self, pc):
        self.temperatureCorrection()
        # interpoaltion cannot handle NaN
        pc_mask = ~(np.isnan(pc[('wind_speed_c','mean')]))
        # piecewise linear interpolation over the power curves to get the refrence values for alarm creation
        y10 = pc[pc_mask][('output_power','low_quantile')].to_numpy()
        w = pc[pc_mask][('wind_speed_c','mean')].to_numpy()
        y = pc[pc_mask][('output_power','mean')].to_numpy()
        self['low_quantile_ref'] = np.interp(self['wind_speed_c'].to_numpy(),w,y10)
        self['reference_power'] = np.interp(self['wind_speed_c'].to_numpy(),w,y)

    def powerCurveIceDetection(self):
        # Alarm limit need to conver this to (1,0) instead of booleans for the length filter to work.
        self['ice_alarm'] = 1.0*((self['output_power'] < self['low_quantile_ref']) & \
                                    (self['ambient_temperature'] < self.parameters['icing_alarm_limit']) & \
                                    (self['wind_speed'] >= self.parameters['minimum_wind_speed']) & \
                                    (self["normal_operation"] == True) & \
                                    (self["faults"] == False) & \
                                    #(dataset["icing_codes"] == False) & \
                                    (self["curtailment"] == False) & \
                                    #(dataset["ice_detection"] == False) & \
                                    (self["other_manual"] == False)
                                    )
        
        # Identify changes in the 'alarm' column to segment sequences
        mask = self['ice_alarm'] != self['ice_alarm'].shift()
        # want group these by event length for length-based filtering
        group = mask.cumsum()

        # Apply transformation only to groups where 'alarm' == 1
        # mask detects where the value changes (from 0 to 1 or vice versa).
        # group assigns a unique group ID to each sequence.
        # groupby(group) groups consecutive values.
        # transform replaces each 1 in a group with the length of that group only if the group starts with 1.
        self['ice_alarm_duration'] = self.groupby(group)['ice_alarm'].transform(lambda x: len(x) if x.iloc[0] == 1 else x)
        # time filter, require at least 3 consequtive alarms
        self['ice_alarm_duration'] = self['ice_alarm_duration'].where(self['ice_alarm_duration'] >= self.parameters['alarm_time_limit'], 0)
        self['ice_alarm'] = self['ice_alarm'].where(self['ice_alarm_duration'] >= self.parameters['alarm_time_limit'], 0)
        
        #print(dataset.head())
        # fig, ax = plt.subplots(nrows=2,ncols=1,sharex=True)
        # dataset.plot.line(x='timestamp', y=['output_power','p10_ref','reference_power'],ax=ax[0])
        # dataset.plot.line(x='timestamp', y=['ice_alarm'],ax=ax[1])
        # plt.show()
        # ToDo:
        # fix the return column names and datatypes, needs to be boolean
        #return dataset
    
    
    
    def computeFullChain(self):
        """
        run the correct sequence of functions and return the dataframe with icign events
        """
        self.temperatureCorrection()
        self.identifyReferenceDataset()
        pc = self.makePowerCurve()
        self.addReferencePowerToData(pc)
        self.powerCurveIceDetection()
        self.identifyIceStop()
        #return icing_data

    def plotPowerCurve(self,pc):
        pc.plot(x=('wind_speed_c','mean'), y=[('output_power','mean'),('output_power','low_quantile'),('output_power','high_quantile')])
        ax2 = plt.gca()
        self.plot.scatter(x="wind_speed_c",y='output_power',color='gray',alpha=0.1, ax=ax2)
        self[self['ice_alarm'] == 1].plot.scatter(x="wind_speed_c",y='output_power',color='red',alpha=0.1, ax=ax2)
        plt.show()
        
    def plotTimeseries(self):
        fig, ax = plt.subplots(nrows=3,ncols=1,sharex=True)
        self.plot.line(y=['output_power','low_quantile_ref','reference_power'],ax=ax[0]) #x=index
        self.plot.line(y=['ice_alarm','stops'],ax=ax[1])
        self.plot.line(y='wind_speed', ax=ax[2])
        self.plot.line(y='ambient_temperature', ax=ax[2], secondary_y=True)
        plt.show()

    def addParametersFromJSON(self,fileName):
        #TODO 
        #check for validity
        #adapt variable names
        #add missing variables to json
        #adapt to the change in the json for multiple turbines
        try:
            with open(fileName, 'r') as file:
                data = json.load(file)
            #print(data)
            #print(type(data))
        except FileNotFoundError:
            print("Error: The file 'data.json' was not found.")
        except json.JSONDecodeError:
            print("Error: Could not decode JSON from the file. Check for valid JSON syntax.")
        
        #Might be changed with micheal change of the json format
        self.parameters['turbine_name'] = data['turbine_info']['name']
        self.parameters['rated_power'] = data['turbine_info']['rated_power_kW']
        self.parameters['hub_height'] = data['turbine_info']['hub_height_m']
        self.parameters['elevation'] = pd.to_numeric(data['turbine_info']['elevation_m'],errors='coerce')
        if np.isnan(self.parameters['elevation']):
            self.parameters['elevation'] = 100
            
        #change the json syntax to mach the parameter names
        self.parameters['low_wind_bin'] = data['power_curve_options']['binning']['min']
        self.parameters['high_wind_bin']= data['power_curve_options']['binning']['max']
        self.parameters['wind_bin_size'] = data['power_curve_options']['binning']['step']
        
        # power curve limits
        self.parameters['low_quantile'] = data['power_curve_options']['lower_limit_percent']/100
        self.parameters['high_quantile'] = data['power_curve_options']['upper_limit_percent']/100
        
        # temperature limits
        self.parameters['temperature_filter_level'] = data['power_curve_options']['temperature_threshold_C']
        self.parameters['icing_alarm_limit'] = 1 #To Be added
        
        # other limits
        self.parameters['alarm_time_limit'] = 3 #To Be added
        self.parameters['minimum_wind_speed'] = 3 #To Be added, give clearer name
        self.parameters['stop_limit'] = 100 #To Be added, give clearer name
        
    def addParametersManually(self,low_wind_bin=None,high_wind_bin=None,wind_bin_size=None,low_quantile=None,high_quantile=None,temperature_filter_level=None,icing_alarm_limit=None,alarm_time_limit=None,minimum_wind_speed=None,stop_limit=None):
        if low_wind_bin is not None:
            self.parameters['low_wind_bin'] = low_wind_bin
        if high_wind_bin is not None:
            self.parameters['high_wind_bin']= high_wind_bin
        if wind_bin_size is not None:
            self.parameters['wind_bin_size'] = wind_bin_size
        
        # power curve limits
        if low_quantile is not None:
            self.parameters['low_quantile'] = low_quantile
        if high_quantile is not None:
            self.parameters['high_quantile'] = high_quantile
        
        # temperature limits
        if temperature_filter_level is not None:
            self.parameters['temperature_filter_level'] = temperature_filter_level
        if icing_alarm_limit is not None:
            self.parameters['icing_alarm_limit'] = icing_alarm_limit
        
        # other limits
        if alarm_time_limit is not None:
            self.parameters['alarm_time_limit'] = alarm_time_limit
        if minimum_wind_speed is not None:
            self.parameters['minimum_wind_speed'] = minimum_wind_speed
        if stop_limit is not None:
            self.parameters['stop_limit'] = stop_limit

if __name__ == '__main__':
    #possible to add a loop here from the new values of the json file to do an entire wind farm
    ice_det = IceLossDetector.importFromCSV("cleaned_file_fake_data2 (other_col_names).csv")
    ice_det.addParametersFromJSON('settings_fake_data2 (other_col_names).json')
    ice_det.identifyReferenceDataset()
    pc = ice_det.makePowerCurve()
    ice_det.addReferencePowerToData(pc)
    ice_det.powerCurveIceDetection()
    ice_det.identifyIceStop()
    ice_det.to_csv('output.csv')
    print(pc)
    ice_det.plotPowerCurve(pc)
    ice_det.plotTimeseries()
