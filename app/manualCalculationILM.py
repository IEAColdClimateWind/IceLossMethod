# -*- coding: utf-8 -*-
"""
Created on Thu Dec 18 15:40:49 2025

@author: PatriceRoberge
"""

from pathlib import Path
from app.ice_case_identifier import IceLossDetector
DATA_DIR_MANAL = Path(__file__).resolve().parent / 'data'

if __name__ == '__main__2':

    json_path_name = DATA_DIR_MANAL / 'settings_new_format.json'
    farm_stats = IceLossDetector.compute_wind_farm(DATA_DIR_MANAL / 'windFarmImport.csv', jsonFileName=json_path_name)
    print(farm_stats)



if __name__ == '__main__':
    #possible to add a loop here from the new values of the json file to do an entire wind farm
    #make a constructor for dataframes
    #TODO option to make it year by year, it can be for power curve generation, but also for results (add option to have an annual thing), add option for calendar year or winters (flexible parameter, Jul, Jan, Aug, Sept)
    json_path_name = DATA_DIR_MANAL / 'settings_new_format.json'
    ice_det = IceLossDetector.importFromCSV(DATA_DIR_MANAL / "cleaned_file_fake_data2 (other_col_names).csv") #have a constructor that does the whole thing
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
    ice_det.exportPowerCurveToCSV()
    
    ice_det.computeIcingStatistics()
    print(ice_det.statistics)