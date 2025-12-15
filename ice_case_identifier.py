import pandas as pd
import numpy as np
import json
# for testing
from pathlib import Path
import matplotlib.pyplot as plt

class IceLossDetector(pd.DataFrame):
    
    #TODO add description of all meta data
    _metadata = ["temperatureCorrectionApplied","parameters","powerCurve","statistics"]
    
    #------------- Constructors and assosiated functions -------------------------------
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
        self.parameters['file_name'] = None
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
        ice_det = cls.constructFromDataFrame(full_data)
        return ice_det
    
    @classmethod
    def constructFromDataFrame(cls, df):
        
        if not np.isin(['wind_speed', 'ambient_temperature', 'output_power', #'timestamp', 
               'normal_operation', 'wind_direction', 'pressure', 'maintenance',
               'faults', 'curtailment', 'other_manual', 'icing_codes', 'ice_detection',
               'ips_status'],df.columns).all():
            raise ImportError('The provided data does not contain the required columns of the standard file')
            
        ice_det = IceLossDetector(df) 
        if not ice_det.isTenMinuteInterval():
            raise ImportError('Please provide 10-minute data')
        ice_det.retimeToTenMinute()
        return ice_det
    
    #------------- Helper methods for constructors --------------
    #TODO check if relevant to put those as helper functions
    
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
        
    #------------------- Parameter handling methods -----------------------------
    def addParametersFromJSON(self, json_fname):
        #TODO check for validity, adapt variable names, add missing variables to json, adapt to the change in the json for multiple turbines
        self.parameters = readJsonParameters(json_fname)
    
            
    def saveParametersToJSON(self, json_fname):
        # Determine turbine name
        turbineName = self.parameters.get("turbine_name", "unnamed_turbine")

        # Build full JSON dictionary
        data = {
            "columns": {
                "Timestamp": "Timestamp",
                "Wind speed": "Wind speed [m/s]",
                "Ambient temperature": "Ambient temperature [C]",
                "Output Power": "output power [kW]",
                "Normal Operation": "Status"
            },
            "parameters": {
                "unit_wind_speed": None,
                "unit_power": None,
                "unit_temperature": None,
                "normal_operation_key": "OK"
            },
            "optional_columns": {
                "meteorological": {
                    "Wind direction": {"column": None, "unit": None},
                    "Pressure": {"column": None, "unit": None}
                },
                "operation": {
                    "Maintenance": {"column": None, "key": None},
                    "Faults": {"column": None, "key": None},
                    "Curtailment": {"column": None, "key": None},
                    "Other manual": {"column": None, "key": None}
                },
                "icing": {
                    "Icing codes": {"column": None, "key": None},
                    "Ice detection": {"column": None, "key": None},
                    "IPS status": {"column": None, "key": None}
                }
            },
            "turbines_info":
                {
                    "Filename": self.parameters.get("file_name", "no_file_name"),
                    "Turbine Name": turbineName,
                    "Rated Power [MW]": float(self.parameters.get("rated_power", 0) or 0),
                    "Elevation [m]": float(self.parameters.get("elevation", 100) or 100),
                    "Hub Height [m]": float(self.parameters.get("hub_height", 80) or 80)
                }
            ,
            "power_curve_options": {
                "temperature_threshold_C": float(self.parameters.get("temperature_filter_level", 0)),
                "output_path": "output/power_curve",
                "lower_limit_percent": float(self.parameters.get("low_quantile", 0)) * 100,
                "upper_limit_percent": float(self.parameters.get("high_quantile", 0)) * 100,
                "binning": {
                    "min": float(self.parameters.get("low_wind_bin", 0)),
                    "max": float(self.parameters.get("high_wind_bin", 30)),
                    "step": float(self.parameters.get("wind_bin_size", 1))
                }
            }
        }

        # Save JSON file
        with open(json_fname, "w") as file:
            json.dump(data, file, indent=4)
            
        return data    
    
    #----------------- Power curve related methods -------------------------
    
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
        
    def exportPowerCurveToCSV(self,fileName=None,recompute=False):
        if fileName is None:
            fileName = f"{self.parameters['turbine_name']}_pc.csv"
        if (self.powerCurve is None) | recompute:
            self.makePowerCurve()
        self.powerCurve.to_csv(fileName,index_label=False)
        
    def import_power_curve(self,fileName):
        newPowerCurve = pd.read_csv(fileName, header=[0, 1], index_col=0)
        required_cols = [
            ('wind_speed_c', 'mean'),
            ('wind_speed_c', 'low_quantile'),
            ('wind_speed_c', 'high_quantile'),
            ('wind_speed_c', 'std.dev'),
            ('wind_speed_c', 'max'),
            ('wind_speed_c', 'min'),
            ('wind_speed_c', 'count'),
            ('output_power', 'mean'),
            ('output_power', 'low_quantile'),
            ('output_power', 'high_quantile'),
            ('output_power', 'std.dev'),
            ('output_power', 'max'),
            ('output_power', 'min'),
            ('output_power', 'count')
        ]
        if not pd.MultiIndex.from_tuples(required_cols).isin(newPowerCurve.columns).all():
            raise ImportError('The provided power curve does not match the column names of the standard file')
        if not (['(0, 1]', '(1, 2]', '(2, 3]', '(3, 4]', '(4, 5]', '(5, 6]', '(6, 7]',
               '(7, 8]', '(8, 9]', '(9, 10]', '(10, 11]', '(11, 12]', '(12, 13]',
               '(13, 14]', '(14, 15]', '(15, 16]', '(16, 17]', '(17, 18]', '(18, 19]',
               '(19, 20]', '(20, 21]', '(21, 22]', '(22, 23]', '(23, 24]', '(24, 25]',
               '(25, 26]', '(26, 27]', '(27, 28]', '(28, 29]', '(29, 30]'] ==newPowerCurve.index).all():
            raise ImportError('The provided power curve does not match the index names of the standard file')
        newPowerCurve.index = pd.Categorical(newPowerCurve.index, categories=newPowerCurve.index.unique(), ordered=True)
        self.powerCurve = newPowerCurve

    def powerCurveDiagnostic(self):
        #TODO write this function, to identify faulty power curves, define metrics
        print('TBD')
    
    #----------------- Icing period identification methods ---------------------------
        
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
        self.computeIcingLosses()
        #Dataframe with the original input data with additional columns
        #    o    Ice detection, different event classes as separate columns
        #    o    Reference power
        #    o    Ice alarm duration?
        #    o    Icing losses at each timestamp
        
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
        #TODO write this function
        print('TBD')
        
    #----------------- Icing computation methods ---------------------------

    def computeIcingLosses(self):
        if np.isin(['iceLossMask','expected_power'],self.columns).all():
            AttributeError('The icing periods or the expected power are not computed, please compute it using identifyIceLossPeriods() or addExpectedPowerToData()')
        #self['power_deficit'] = (self['expected_power'] - self['output_power'])
        self['production_loss'] = (self['expected_power'] - self['output_power']) * 10/60 # loss in kw * duration of loss (10 minutes) loss in kWh
        self['icingLosses'] = self['iceLossMask'] * (self['expected_power']-self['output_power']) * 10 / 60 #in kWh at each timestamp

    def computeProducedEnergy(self,periodStart=None,periodEnd=None):
        if (periodStart is not None) and (periodEnd is not None):
            return float(np.round((self.loc[(self.index>=periodStart)&(self.index<=periodEnd),'output_power']*10/60).sum(),0))
        else:
            return float(np.round((self['output_power']/6).sum(),0))

    def computeTotalIcingLosses(self,periodStart=None,periodEnd=None):
        if (periodStart is not None) and (periodEnd is not None):
            return float(np.round((self.loc[(self.index>=periodStart)&(self.index<=periodEnd),'icingLosses']).sum(),0))
        else:
            return float(np.round((self['icingLosses']).sum(),0))
        
    def computeTotalLosses(self,periodStart=None,periodEnd=None):
        if (periodStart is not None) and (periodEnd is not None):
            return float(np.round((self.loc[(self.index>=periodStart)&(self.index<=periodEnd),'production_loss']).sum(),0))
        else:
            return float(np.round((self['production_loss']).sum(),0))
    
    def computeTotalIcingReducedProductionLosses(self,periodStart=None,periodEnd=None):
        if (periodStart is not None) and (periodEnd is not None):
            return float(np.round(
                (self['icingLosses']*self['iceLossOperationalMask'])
                 .loc[(self.index>=periodStart)&(self.index<=periodEnd),:].sum(),0))
        else:
            return float(np.round((self['icingLosses']*self['iceLossOperationalMask']).sum(),0))
        
    def computeTotalIcingStandstillLosses(self,periodStart=None,periodEnd=None):
        if (periodStart is not None) and (periodEnd is not None):
            return float(np.round(
                (self['icingLosses']*self['iceLossStandstillMask'])
                 .loc[(self.index>=periodStart)&(self.index<=periodEnd),:].sum(),0))
        else:
            return float(np.round((self['icingLosses']*self['iceLossStandstillMask']).sum(),0))

    def computeExpectedEnergy(self,periodStart=None,periodEnd=None):
        if (periodStart is not None) and (periodEnd is not None):
            return float(np.round((self.loc[(self.index>=periodStart)&(self.index<=periodEnd),'expected_power']*10/60).sum(),0))
        else:
            return float(np.round((self['expected_power']/6).sum(),0))

    def computeNumberOfIcingEvents(self,periodStart=None,periodEnd=None):
        #TODO write this function, it is currently in computeIcingStatistics, find a way that fimple values are not computed many times
        print('TBD')

    def computeAverageEventDuration(self,periodStart=None,periodEnd=None):
        #TODO write this function, it is currently in computeIcingStatistics, find a way that fimple values are not computed many times
        print('TBD')

    #TODO add as many functions as there are statistics to be computed
    
    def computeIcingStatistics(self):
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
        
        if 'iceLossMask' not in self.columns:
            self.identifyIceLossPeriods()
        
        # separate the icing events
        reduced_prod_events = self[self['iceLossMask'] == 1]
        stops_events = self[self['iceLossStandstillMask'] == 1]
        icing_events = pd.concat((reduced_prod_events, stops_events))
        
        # total dataset length in hours§
        self.statistics["total_data_hours"]            = float(np.round((self.index.max() - self.index.min()).total_seconds() /60 /60 ,0))
        
        # these are not continuous cant count from timestamps
        self.statistics["total_icing_duration"]        = float(np.round((1/6)*len(icing_events),0)) # number of lines * 10 minutes / 60 minutes = total hours
        self.statistics["reduced_production_duration"] = float(np.round((1/6)*len(reduced_prod_events),0))
        self.statistics["icing_stop_duration"]         = float(np.round((1/6)*len(stops_events),0))
        #icing share is often interesting since its in the ice class.
        self.statistics["total_icing_share"]           = float(np.round(len(icing_events) / len(self.index) * 100,2))
        self.statistics["reduced_production_share"]    = float(np.round(len(reduced_prod_events) / len(self.index) * 100, 2))
        self.statistics["icing_stop_share"]            = float(np.round(len(stops_events) / len(self.index) * 100, 2))
        # energy in kWh
        self.statistics["total_production"]          = self.computeProducedEnergy()         #float(np.round((self['output_power']/6).sum(),0))
        self.statistics["total_expected_production"] = self.computeExpectedEnergy()         #float(np.round((self['expected_power']/6).sum(),0))
        self.statistics["total_losses"]              = self.computeTotalLosses()            #float(np.round(self['production_loss'].sum(),0))
        self.statistics["total_icing_loss"]          = self.computeTotalIcingLosses()       #float(np.round(icing_events["production_loss"].sum(),0))
        self.statistics["reduced_production_loss"]   = self.computeTotalIcingReducedProductionLosses() #float(np.round(reduced_prod_events["production_loss"].sum(),0))
        self.statistics["icing_stop_loss"]           = self.computeTotalIcingStandstillLosses() #float(np.round(stops_events["production_loss"].sum(),0))
        # losses in % of AEP
        self.statistics["total_icing_share"]         = float(np.round(self.statistics["total_icing_loss"] / 
                                                                      self.statistics["total_expected_production"],2))
        self.statistics["reduced_producion_share"]   = float(np.round(self.statistics["reduced_production_loss"] / 
                                                                      self.statistics["total_expected_production"],2))
        self.statistics["icing_stop_share"]          = float(np.round(self.statistics["icing_stop_loss"] /
                                                                      self.statistics["total_expected_production"],2))
        
        # other status variables again, cant count form timestamps so number of hours is number of lines * 1/6:
        # maintenance	faults	curtailment	other_manual	icing_codes	ice_detection	ips_status	cleanedDatasetMask
        self.statistics["maintenance_hours"]   = float(np.round((1/6)*len(self[self["maintenance"]       ==True]),0))
        self.statistics["faults_hours"]        = float(np.round((1/6)*len(self[self["faults"]            ==True]),0))
        self.statistics["curtailment_hours"]   = float(np.round((1/6)*len(self[self["curtailment"]       ==True]),0))
        self.statistics["other_manual_hours"]  = float(np.round((1/6)*len(self[self["other_manual"]      ==True]),0))
        self.statistics["icing_codes_hours"]   = float(np.round((1/6)*len(self[self["icing_codes"]       ==True]),0))
        self.statistics["ice_detection_hours"] = float(np.round((1/6)*len(self[self["ice_detection"]     ==True]),0))
        self.statistics["ips_status_hours"]    = float(np.round((1/6)*len(self[self["ips_status"]        ==True]),0))
        self.statistics["reference_hours"]     = float(np.round((1/6)*len(self[self["cleanedDatasetMask"]==True]),0))
        
    def exportStatistics(self,fileName=None,recompute=False):
        if fileName is None:
            fileName = ice_det.parameters['turbine_name']+'_statistics.csv'
        if (len(self.statistics) == 0) | recompute:
            self.computeIcingStatistics()
        pd.Series(self.statistics).to_csv(fileName,header=None)
        
    #---------------- Full flow computation methods --------------------------

    def computeFullChain(self):
        """
        run the correct sequence of functions and return the dataframe with icign events
        """
        self.temperatureCorrection()
        self.identifyCleanedDataset()
        self.makePowerCurve() #TODO find a way to manually add a power curve, you can skip this step if you have reference power low and high quantile
        self.addExpectedPowerToData()
        self.identifyIceLossPeriods()
        self.computeIcingLosses()

        self.computeIcingStatistics()
        #return icing_data
        
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
        
    #------------------------------ Plotting methods --------------------------------------
    
    def plotPowerCurve(self): #TODO add option to add IPS activation and ice detection, add garnish to this function, print to file?
        if self.powerCurve is None:
            AttributeError('The power curve has not been computed, please compute it using makePowerCurve()')
        pc = self.powerCurve
        pc.plot(x=('wind_speed_c','mean'), y=[('output_power','mean'),('output_power','low_quantile'),('output_power','high_quantile')],label=['mean','low_quantile','high_quantile'])
        ax2 = plt.gca()
        self.plot.scatter(x="wind_speed_c",y='output_power',color='gray',alpha=0.1, ax=ax2,label='All points')
        self[self['iceLossMask'] == 1].plot.scatter(x="wind_speed_c",y='output_power',color='red',alpha=0.1, ax=ax2, label='Icing losses')
        ax2.set_title(f"Power curve: {self.parameters['turbine_name']}")
        plt.tight_layout()
        plt.show()
        
    def plotTimeseries(self): #TODO add option to add IPS activation and ice detection, add garnish to this function, print to file?
        fig, ax = plt.subplots(nrows=3,ncols=1,sharex=True,figsize=[12,8])
        self.plot.line(y=['output_power','low_quantile_ref','high_quantile_ref','expected_power'],ax=ax[0]) #x=index
        self.plot.line(y=['iceLossOperationalMask','iceLossStandstillMask'],ax=ax[1])
        self.plot.line(y='wind_speed', ax=ax[2])
        self.plot.line(y='ambient_temperature', ax=ax[2], secondary_y=True)
        ax[0].set_title(f"Timeseries: {self.parameters['turbine_name']}")
        plt.tight_layout()
        plt.show()
        
    #------------------ Static Methods -----------------------

    @staticmethod
    def compute_wind_farm(windFarmCsv,jsonFileName=None,customColNamesDict=None):
        """
        Generates the icing statistics from a standard json file that imports csv files generated from the import module
        
        """

        farm_statistics_dict = {}
        # TODO: better handle parent directory that has all the CSV
       
        if jsonFileName is None:
            #if no json file is provided, create a standard one
            jsonFileName = 'defaultParameters.json'
            parameters = IceLossDetector.create_default_json_parameter_file(jsonFileName)
            
        readJsonParameters(jsonFileName)
        windFarmDF = readWindFarmDFFromCSV(windFarmCsv,customColNamesDict=customColNamesDict)

        for row in windFarmDF.itertuples(index=False):
            turbine_name = row.turbine_name
            csv_fname = row.file_name

            ice_det = IceLossDetector.importFromCSV(Path('app') / 'data' / csv_fname)
            ice_det.addParametersFromJSON(jsonFileName)
            ice_det.parameters.update(row._asdict())
            ice_det.computeFullChain()

            farm_statistics_dict[csv_fname] = ice_det.statistics

        return farm_statistics_dict

    @staticmethod
    def load_wind_farm(windFarmCsv,jsonFileName=None,customColNamesDict=None):
        """
        Creates a dictionnary of IceLossDetector objects from a standard json file that imports csv files generated from the import module
        
        """

        farm_dict = {}
        if jsonFileName is None:
            #if no json file is provided, create a standard one
            jsonFileName = 'defaultParameters.json'
            parameters = IceLossDetector.create_default_json_parameter_file(jsonFileName)
            
        readJsonParameters(jsonFileName)
        windFarmDF = readWindFarmDFFromCSV(windFarmCsv,customColNamesDict=customColNamesDict)

        for row in windFarmDF.itertuples(index=False):
            turbine_name = row.turbine_name
            csv_fname = row.file_name

            ice_det = IceLossDetector.importFromCSV(Path('app') / 'data' / csv_fname)
            ice_det.addParametersFromJSON(jsonFileName)
            ice_det.parameters.update(row._asdict())
            #ice_det.computeFullChain()

            farm_dict[turbine_name] = ice_det

        return farm_dict

    @staticmethod      
    def create_default_json_parameter_file(json_fname):
        #create empty object to get default values
        defaultParameters = IceLossDetector().saveParametersToJSON(json_fname)
        return defaultParameters


#--------- Utility functions that can only be called from the class --------------

def readWindFarmDFFromCSV(windFarmCsv,customColNamesDict=None):
    windFarmDF = pd.read_csv(windFarmCsv)
    if customColNamesDict is not None:
        windFarmDF.rename(inplace=True,mapper=customColNamesDict)
    if not np.isin(['file_name', 'turbine_name', 'rated_power','hub_height', 'elevation'],windFarmDF.columns).all():
        raise ImportError('The wind farm csv does not contain the required columns of the standard format')
    return windFarmDF

def readJsonParameters(json_fname):
    try:
        with open(json_fname, 'r') as file:
            data = json.load(file)
    
    except FileNotFoundError:
        print("Error: The file 'data.json' was not found.")
    except json.JSONDecodeError:
        print("Error: Could not decode JSON from the file. Check for valid JSON syntax.")

    try:
        parameters = {}
        turbine_info = data.get("turbines_info", [])

        #Might be changed with micheal change of the json format
        parameters['turbine_name'] = turbine_info.get("turbine_name","unnamed_turbine")
        parameters['file_name'] = turbine_info.get('file_name','no_file_name')
        parameters['rated_power'] = pd.to_numeric(turbine_info.get('rated_power',None),errors='coerce')
        parameters['hub_height'] = pd.to_numeric(turbine_info.get('hub_height',80),errors='coerce')
        parameters['elevation'] = pd.to_numeric(turbine_info.get('elevation',100),errors='coerce')
        if np.isnan(parameters['elevation']):
            parameters['elevation'] = 100
            
        #change the json syntax to mach the parameter names
        parameters['low_wind_bin'] = data['power_curve_options']['binning']['min']
        parameters['high_wind_bin']= data['power_curve_options']['binning']['max']
        parameters['wind_bin_size'] = data['power_curve_options']['binning']['step']
        
        # power curve limits
        parameters['low_quantile'] = data['power_curve_options']['lower_limit_percent']/100
        parameters['high_quantile'] = data['power_curve_options']['upper_limit_percent']/100
        
        # temperature limits
        parameters['temperature_filter_level'] = data['power_curve_options']['temperature_threshold_C']
        parameters['icing_alarm_limit'] = 1 #To Be added
        
        # other limits
        parameters['alarm_time_limit'] = 3 #To Be added
        parameters['minimum_wind_speed'] = 3 #To Be added, give clearer name
        parameters['stop_limit'] = 100 #To Be added, give clearer name
        
        return parameters

    except:
        raise ImportError('Issue in the importation of the parameters')


#--------------- Main functions -----------------------------
        
if __name__ == '__main__':

    json_path_name = Path('app') / 'data'  / 'settings_new_format.json'


    farm_stats = IceLossDetector.compute_wind_farm('windFarmImport.csv',jsonFileName=json_path_name)
    print(farm_stats)

if __name__ == '__main__2':
    #possible to add a loop here from the new values of the json file to do an entire wind farm
    #make a constructor for dataframes
    #TODO option to make it year by year, it can be for power curve generation, but also for results (add option to have an annual thing), add option for calendar year or winters (flexible parameter, Jul, Jan, Aug, Sept)
    json_path_name = Path('app') / 'data'  / 'settings_new_format.json'
    ice_det = IceLossDetector.importFromCSV("cleaned_file_fake_data2 (other_col_names).csv") #have a constructor that does the whole thing
    ice_det.addParametersFromJSON(json_path_name)
    ice_det.identifyCleanedDataset() #options to activate those functions or not
    ice_det.makePowerCurve()
    ice_det.addExpectedPowerToData()
    ice_det.identifyIceLossPeriods()
    ice_det.computeIcingLosses()
    # can be formatted into a dictionnary
    ice_det.to_csv('output.csv')
    ice_det.plotPowerCurve() #optional
    ice_det.plotTimeseries()
    
    ice_det.computeIcingStatistics()
    print(ice_det.statistics)
