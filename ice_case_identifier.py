import pandas as pd
import numpy as np
import json
# for testing
from pathlib import Path
import matplotlib.pyplot as plt

class IceLossDetector(pd.DataFrame):
    
    _metadata = ["temperatureCorrectionApplied","parameters","powerCurve","statistics"]
    
    @property
    def _constructor(self):
        return IceLossDetector

    def __finalize__(self, other, method=None):
        for name in self._metadata:
            object.__setattr__(self, name, getattr(other, name, None))
        return self
    
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
        self.powerCurve = None
        self.parameters = {}
        self.statistics = {}
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
    def iceLossAnalysis(cls, fileNameData, fileNameConfig, fileNameOutput, computePowerCurve=True):
        ice_det = cls.importFromCSV(fileNameData)
        ice_det.addParametersFromJSON(fileNameConfig)
        if computePowerCurve:
            ice_det.identifyCleanedDataset()
            ice_det.makePowerCurve()
            ice_det.addExpectedPowerToData()
        ice_det.identifyIceLossPeriods()
        ice_det.computeIcingLosses()
        ice_det.to_csv(fileNameOutput)
        if computePowerCurve:
            ice_det.plotPowerCurve() #optional
        ice_det.plotTimeseries()

    @classmethod
    def importFromCSV(cls, fileName):
        """
        Creates a IceLossDetector from a standard csv file generated from the import module
        
        """
        full_data = pd.read_csv(fileName,index_col=0)
        ice_det = cls.constructFromDataFrame(full_data)
        return ice_det
    
    
    
    @classmethod
    def constructFromDataFrame(cls, df):
        
        if not np.isin(['timestamp', 'wind_speed', 'ambient_temperature', 'output_power',
               'normal_operation', 'wind_direction', 'pressure', 'maintenance',
               'faults', 'curtailment', 'other_manual', 'icing_codes', 'ice_detection',
               'ips_status'],df.columns).all():
            raise ImportError('The provided data does not contain the required columns of the standard file')
            
        ice_det = IceLossDetector(df) 
        if not ice_det.isTenMinuteInterval():
            raise ImportError('Please provide 10-minute data')
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
        
        
    def identifyCleanedDataset(self):
        # these can probaably be hardcoded, esp. if ¨"other_manual" can be set from UI.
        reference_dataset_mask = (self["normal_operation"] == True) &\
                                (self["faults"] == False) & \
                                (self["curtailment"] == False) & \
                                (self["other_manual"] == False) & \
                                (self["ambient_temperature"] >= self.parameters['temperature_filter_level'])
        #TODO add option to remove ice detection and icing code from dataset
        #(self["icing_codes"] == False) & \
        #(self["ice_detection"] == False) & \
        self.loc[:,'cleanedDatasetMask'] = reference_dataset_mask


    def makePowerCurve(self):
        """
        ·         Power curve used to detect icing

                        o    Includes the limits (P10, P90)

                        o    Also sample count per bin

                        o    Some kind of diagnostic of the quality of the power curve (To be implemented)

        """
        self.temperatureCorrection()
        if 'cleanedDatasetMask' not in self.columns:
            self.identifyCleanedDataset()
        reference_dataset = self.loc[self.loc[:,'cleanedDatasetMask'],:]
        # this needs to be settable
        wind_bins = pd.interval_range(start=self.parameters['low_wind_bin'], end=self.parameters['high_wind_bin'], freq=self.parameters['wind_bin_size'])
        # create binning for the dataset based on the corrected wind speed
        binning = pd.cut(reference_dataset['wind_speed_c'],bins=wind_bins)
        binning_r = binning.rename("bin")
        # add bin index for every value in the dataset
        reference_dataset_b = pd.merge(left=reference_dataset, right=binning_r, left_index=True, right_index=True)

        # group by bin, calculate bunch of statistics for each bin
        # aggregation functions are listed as ('name of result', function)
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
        self.powerCurve = pc
        #pc.rename(columns = {"wind_speed_c":"wind_speed"},inplace=True)
        #pc_subset = pc[[('wind_speed','mean'),('output_power','mean'),('output_power','low_quantile'),('output_power','high_quantile'),('output_power','count')]]
        
        # Flatten MultiIndex columns to make refrencing make more sense
        #pc_subset.columns = ['{}_{}'.format(col[0], col[1]) for col in pc_subset.columns]
        # print(pc_subset)
        #return pc_subset
    
    def addExpectedPowerToData(self):
        if self.powerCurve is None:
            AttributeError('The power curve has not been computed, please compute it using makePowerCurve()')
        pc = self.powerCurve
        self.temperatureCorrection()
        # interpoaltion cannot handle NaN
        pc_mask = ~(np.isnan(pc[('wind_speed_c','mean')]))
        # piecewise linear interpolation over the power curves to get the refrence values for alarm creation
        y10 = pc[pc_mask][('output_power','low_quantile')].to_numpy()
        y90 = pc[pc_mask][('output_power','high_quantile')].to_numpy()
        w = pc[pc_mask][('wind_speed_c','mean')].to_numpy()
        y = pc[pc_mask][('output_power','mean')].to_numpy()
        self['low_quantile_ref'] = np.interp(self['wind_speed_c'].to_numpy(),w,y10)
        self['high_quantile_ref'] = np.interp(self['wind_speed_c'].to_numpy(),w,y90)
        self['expected_power'] = np.interp(self['wind_speed_c'].to_numpy(),w,y)

    def identifyIceLossPeriods(self):
        if 'low_quantile_ref' not in self.columns:
            AttributeError('The low quantile reference power is not computed, please compute it using addExpectedPowerToData()')
        # Alarm limit need to conver this to (1,0) instead of booleans for the length filter to work.
        self['iceLossMask'] = 1.0*((self['output_power'] < self['low_quantile_ref']) & \
                                    (self['ambient_temperature'] < self.parameters['icing_alarm_limit']) & \
                                    (self['wind_speed'] >= self.parameters['minimum_wind_speed']) & \
                                    (self["normal_operation"] == True) & \
                                    (self["faults"] == False) & \
                                    #(dataset["icing_codes"] == False) & \
                                    (self["curtailment"] == False) & \
                                    #(dataset["ice_detection"] == False) & \
                                    (self["other_manual"] == False)
                                    ) #TODO change name of column to specify that it is a mask
        
        # Identify changes in the 'alarm' column to segment sequences
        mask = self['iceLossMask'] != self['iceLossMask'].shift()
        # want group these by event length for length-based filtering
        group = mask.cumsum()

        # Apply transformation only to groups where 'alarm' == 1
        # mask detects where the value changes (from 0 to 1 or vice versa).
        # group assigns a unique group ID to each sequence.
        # groupby(group) groups consecutive values.
        # transform replaces each 1 in a group with the length of that group only if the group starts with 1.
        self['ice_alarm_duration'] = self.groupby(group)['iceLossMask'].transform(lambda x: len(x) if x.iloc[0] == 1 else x)
        # time filter, require at least 3 consequtive alarms
        self['ice_alarm_duration'] = self['ice_alarm_duration'].where(self['ice_alarm_duration'] >= self.parameters['alarm_time_limit'], 0)
        self['iceLossMask'] = self['iceLossMask'].where(self['ice_alarm_duration'] >= self.parameters['alarm_time_limit'], 0)
        self['power_deficit'] = (self['expected_power'] - self['output_power'])
        self['production_loss'] = self['power_deficit']/6 # loss in kw * duration of loss (10 minutes) loss in kWh
        #Dataframe with the original input data with additional columns
        #    o    Ice detection, different event classes as separate columns
        #    o    Reference power
        #    o    Ice alarm duration?
        #    o    Icing losses at each timestamp
        
        #print(dataset.head())
        # fig, ax = plt.subplots(nrows=2,ncols=1,sharex=True)
        # dataset.plot.line(x='timestamp', y=['output_power','p10_ref','reference_power'],ax=ax[0])
        # dataset.plot.line(x='timestamp', y=['ice_alarm'],ax=ax[1])
        # plt.show()
        # ToDo:
        # fix the return column names and datatypes, needs to be boolean
        # check what happens with nan values
        self.identifyIceLossOperational()
        self.identifyIceLossStandstill()


    def identifyIceLossStandstill(self):
        if 'iceLossMask' not in self.columns:
            AttributeError('The low quantile reference power is not computed, please compute it using identifyIceLossPeriods()')
        # separate the points when the turbine has stopped from the other icing alarms
        # Stops are events where we have an icing alarm, but the power is below a certain limit. 
        stop_mask = ((self['iceLossMask'] == 1.0) & (self['output_power'] <= self.parameters['stop_limit']) &\
                    (self['wind_speed'] >= self.parameters['minimum_wind_speed']))
        self['iceLossStandstillMask'] = 1.0*stop_mask 

    def identifyIceLossOperational(self):
        if 'iceLossMask' not in self.columns:
            AttributeError('The low quantile reference power is not computed, please compute it using identifyIceLossPeriods()')
        # separate the points when the turbine has stopped from the other icing alarms
        # Stops are events where we have an icing alarm, but the power is below a certain limit. 
        running_mask = ((self['iceLossMask'] == 1.0) & ((self['output_power'] > self.parameters['stop_limit']) |\
                    (self['wind_speed'] < self.parameters['minimum_wind_speed'])))
        self['iceLossOperationalMask'] = 1.0*running_mask 
        
    def identifyIceLossOverProduction(self):
        print('TBD')

    def computeIcingLosses(self):
        if np.isin(['iceLossMask','expected_power'],self.columns).all():
            AttributeError('The icing periods or the expected power are not computed, please compute it using identifyIceLossPeriods() or addExpectedPowerToData()')
        self['icingLosses'] = self['iceLossMask'] * (self['expected_power']-self['output_power']) * 10 / 60 #in kWh at each timestamp
    
    def computeIcingStatistics(self):
        print('TBD')

    def computeProducedEnergy(self,periodStart=None,periodEnd=None):
        print('TBD')

    def computeEnergyIcingLosses(self,periodStart=None,periodEnd=None):
        print('TBD')

    def computeExpectedEnergy(self,periodStart=None,periodEnd=None):
        print('TBD')

    def computeNumberOfIcingEvents(self,periodStart=None,periodEnd=None):
        print('TBD')

    def computeAverageEventDuration(self,periodStart=None,periodEnd=None):
        print('TBD')

    def computeIcingLossesPerClass(self,periodStart=None,periodEnd=None):
        print('TBD')

    #add as many functions as there are statistics to be computed

    def exportOutputStatistics(self):
        print('TBD')

    def exportPowerCurveToCSV(self):
        print('TBD')

    def powerCurveDiagnostic(self):
        print('TBD')

    def computeFullChain(self):
        """
        run the correct sequence of functions and return the dataframe with icign events
        """
        self.temperatureCorrection()
        self.identifyCleanedDataset()
        self.makePowerCurve() #find a way to manually add a power curve, you can skip this step if you have reference power low and high quantile
        self.addExpectedPowerToData()
        self.identifyIceLossPeriods()
        self.computeIcingLosses()

        self.make_statistics()
        #return icing_data

    def plotPowerCurve(self): #TODO add option to add IPS activation and ice detection, add garnish to this function, print to file?
        if self.powerCurve is None:
            AttributeError('The power curve has not been computed, please compute it using makePowerCurve()')
        pc = self.powerCurve
        pc.plot(x=('wind_speed_c','mean'), y=[('output_power','mean'),('output_power','low_quantile'),('output_power','high_quantile')])
        ax2 = plt.gca()
        self.plot.scatter(x="wind_speed_c",y='output_power',color='gray',alpha=0.1, ax=ax2)
        self[self['iceLossMask'] == 1].plot.scatter(x="wind_speed_c",y='output_power',color='red',alpha=0.1, ax=ax2)
        plt.show()
        
    def plotTimeseries(self):
        fig, ax = plt.subplots(nrows=3,ncols=1,sharex=True)
        self.plot.line(y=['output_power','low_quantile_ref','high_quantile_ref','expected_power'],ax=ax[0]) #x=index
        self.plot.line(y=['iceLossOperationalMask','iceLossStandstillMask'],ax=ax[1])
        self.plot.line(y='wind_speed', ax=ax[2])
        self.plot.line(y='ambient_temperature', ax=ax[2], secondary_y=True)
        plt.show()

    def addPowerCurveFromCSV(self,fileName):
        print('TBD')

    def addParametersFromJSON(self, json_fname, turbine_name):
        #TODO 
        #check for validity
        #adapt variable names
        #add missing variables to json
        #adapt to the change in the json for multiple turbines
        try:
            with open(json_fname, 'r') as file:
                data = json.load(file)
        
        except FileNotFoundError:
            print("Error: The file 'data.json' was not found.")
        except json.JSONDecodeError:
            print("Error: Could not decode JSON from the file. Check for valid JSON syntax.")

        
        # for turbine_info in data['turbines_info']:
        #     if turbine_info['Turbine Name'] == turbine_name:
        #         break

        try:
            turbine_info = [b for b in data.get("turbines_info", []) if "Turbine Name" in b and turbine_name in b["Turbine Name"]][0]

            #Might be changed with micheal change of the json format
            self.parameters['turbine_name'] = turbine_info['Filename']
            self.parameters['rated_power'] = turbine_info['Turbine Name']
            self.parameters['hub_height'] = turbine_info['Rated Power [MW]']
            self.parameters['elevation'] = pd.to_numeric(turbine_info['Elevation [m]'],errors='coerce')
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

        except:
            raise ImportError(f'The turbine name {turbine_name} does not exist in the JSON {json_fname}')
        
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
            
    def print_power_curve(self, pc):
        pc.to_csv(f"{self.parameters['turbine_name']}_pc.csv")
        
    def make_statistics(self):
        """
        Statistics of production:
          o    Icing hours / icing as % of year
                 §  Total and per class
          o    Icing losses
                 §  Total and per icing class
          o    Statistics on availability, data coverage etc.
          o    Total energy produced, expected and loss (icing, faults/maintenance, during icing detection, during IPS activation)
          o    Time in each category (icing, faults/maintenance, during icing detection, during IPS activation)
          o    Same but in Dollars or euros (To be implemented)
          o    Number of icing events
        """
        
        # separate the icing events
        reduced_prod_events = self[self['iceLossMask'] == 1]
        stops_events = self[self['iceLossStandstillMask'] == 1]
        icing_events = pd.concat((reduced_prod_events, stops_events))
        
        # total dataset length in hours§
        self.statistics["total_data_hours"] = float(np.round((self.index.max() - self.index.min()).total_seconds() /60 /60 ,0))
        
        # these are not continuous cant count from timestamps
        self.statistics["total_icing_duration"] = float(np.round((1/6)*len(icing_events),0)) # number of lines * 10 minutes / 60 minutes = total hours
        self.statistics["reduced_production_duration"] = float(np.round((1/6)*len(reduced_prod_events),0))
        self.statistics["icing_stop_duration"] = float(np.round((1/6)*len(stops_events),0))
        #icing share is often interesting since its in the ice class.
        self.statistics["total_icing_share"] = float(np.round(len(icing_events) / len(self.index) * 100,2))
        self.statistics["reduced_production_share"] = float(np.round(len(reduced_prod_events) / len(self.index) * 100, 2))
        self.statistics["icing_stop_share"] = float(np.round(len(stops_events) / len(self.index) * 100, 2))
        
        self.statistics["total_production"] = float(np.round((self['output_power']/6).sum(),0))
        self.statistics["total_expected_production"] = float(np.round((self['expected_power']/6).sum(),0))
        self.statistics["total_losses"] = float(np.round(self['production_loss'].sum(),0))
             # total losses in kWh
        self.statistics["total_icing_loss"] = float(np.round(icing_events["production_loss"].sum(),0))
        self.statistics["reduced_production_loss"] = float(np.round(reduced_prod_events["production_loss"].sum(),0))
        self.statistics["icing_stop_loss"] = float(np.round(stops_events["production_loss"].sum(),0))
        # losses in % of AEP
        self.statistics["total_icing_share"] = float(np.round(self.statistics["total_icing_loss"] / self.statistics["total_expected_production"],2))
        self.statistics["reduced_producion_share"] = float(np.round(self.statistics["reduced_production_loss"] / self.statistics["total_expected_production"],2))
        self.statistics["icing_stop_share"] = float(np.round(self.statistics["icing_stop_loss"] / self.statistics["total_expected_production"],2))
        
        # other status variables again, cant count form timestamps so number of hours is number of lines * 1/6:
        # maintenance	faults	curtailment	other_manual	icing_codes	ice_detection	ips_status	cleanedDatasetMask
        self.statistics["maintenance_hours"] = float(np.round((1/6)*len(self[self["maintenance"]==True]),0))
        self.statistics["faults_hours"] = float(np.round((1/6)*len(self[self["faults"]==True]),0))
        self.statistics["curtailment_hours"] = float(np.round((1/6)*len(self[self["curtailment"]==True]),0))
        self.statistics["other_manual_hours"] = float(np.round((1/6)*len(self[self["other_manual"]==True]),0))
        self.statistics["icing_codes_hours"] = float(np.round((1/6)*len(self[self["icing_codes"]==True]),0))
        self.statistics["ice_detection_hours"] = float(np.round((1/6)*len(self[self["ice_detection"]==True]),0))
        self.statistics["ips_status_hours"] = float(np.round((1/6)*len(self[self["ips_status"]==True]),0))
        self.statistics["reference_hours"] = float(np.round((1/6)*len(self[self["cleanedDatasetMask"]==True]),0))
        


    @staticmethod
    def compute_farm_from_json(json_fname):
        """
        Creates a IceLossDetector from a standard csv file generated from the import module
        
        """

        farm_statistics_dict = {}
        # TODO: better handle parent directory that has all the CSV
       
        with open(json_fname, 'r') as file:
            json_settings = json.load(file)

        list_of_turbines = json_settings['turbines_info']

        for turbine_info in list_of_turbines:
            turbine_name = turbine_info['Turbine Name']
            csv_fname = turbine_info['Filename']

            ice_det = IceLossDetector.importFromCSV(Path('app') / 'data' / csv_fname)
            ice_det.addParametersFromJSON(json_fname, turbine_name)
            ice_det.computeFullChain()

            farm_statistics_dict[csv_fname] = ice_det.statistics

        return farm_statistics_dict

        
        
        
if __name__ == '__main__':

    json_path_name = Path('app') / 'data'  / 'settings_fake_data2.csv (26).json'


    farm_stats = IceLossDetector.compute_farm_from_json(json_path_name)
    print(farm_stats)

    
        
        
        
        

if __name__ == '__main__2':
    #possible to add a loop here from the new values of the json file to do an entire wind farm
    #make a constructor for dataframes
    #TODO option to make it year by year, it can be for power curve generation, but also for results (add option to have an annual thing), add option for calendar year or winters (flexible parameter, Jul, Jan, Aug, Sept)
    ice_det = IceLossDetector.importFromCSV("cleaned_file_fake_data2 (other_col_names).csv") #have a constructor that does the whole thing
    ice_det.addParametersFromJSON('settings_fake_data2 (other_col_names).json')
    ice_det.identifyCleanedDataset() #options to activate those functions or not
    ice_det.makePowerCurve()
    ice_det.addExpectedPowerToData()
    ice_det.identifyIceLossPeriods()
    ice_det.computeIcingLosses()
    #TODO add method compute losses: add column with losses in kWh for each timestamp
    #TODO add method compute statistics actual energy production, expected and losses, number of events, average duration, losses per category, start from timo's previous version, no start from scracth
    #TODO add method to evaluate power curve, stats and figures, diagnostic
    # can be formatted into a dictionnary
    ice_det.to_csv('output.csv')
    ice_det.plotPowerCurve() #optional
    ice_det.plotTimeseries()
    
    ice_det.make_statistics()
    print(ice_det.statistics)

    #workflow would be like this
    #jsonFile = 'config.json'
    #turbineTable, generalConfigs = parseConfig(jsonFile)
    #for index, row in turbineTable.iterrows():
    #   print(f'Analysis for {index}')
    #   dataFile = row['fileName']
    #   IceLossDetector.iceLossAnalysis(fileNameData=dataFile, fileNameConfig=jsonFile, fileNameOutput=f'output_{index}.csv', computePowerCurve=True)
