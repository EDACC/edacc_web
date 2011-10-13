"""
    edacc.configurator_view
    --------------------

    This module defines the view which shows configuration details.
    
    :copyright: (c) 2011 by Melanie Handel.
    :license: MIT, see LICENSE for details.
"""

from edacc import utils, models, constants
import time

configuration = {}
 #classify in Categories
def classify(values, categories):
    valueDict = {}    
    for vl in range(len(categories)): 
        valueDict[categories[vl]] = vl
    m = 0 
    for v in values:
        if v in valueDict:
            values[m] = valueDict[v]
        m += 1
    return values

#Turns the range of value
def turnValue(values):
    k = 0
    for va in values:
        values[k] = max(values) - va
        k += 1
    return values

#Projects the values to the range of the graph
def project(values):
    values = map(float, values)
    if max(values) > 0:
        j = 0
        tmp = 10/max(values)
        for v in values:
            values[j] = v * tmp
            j += 1 
    return values

def mapPosition(form):
    pos = map(str, form)
    list = []
    b = 0
    pos1 = ''
    pos2 = ''
    while pos[0][b]!= ':':
        pos1 += pos[0][b]
        b+=1
    b += 2
    while b < len(pos[0]):
        pos2 += pos[0][b]
        b+=1
    list = [int(pos1), int(pos2)]               
    return list


class config_vis(object):
    def __init__(self, database, expID, configForm):
        db = models.get_database(database) or abort(404)   
        experiment = db.session.query(db.Experiment).get(expID) or abort(404)
        if experiment.configurationExp == False: return # kein Konfiguratorexperiment
        solverConfig = {}
        paramAttribute = {}
        parameterValue = {}
        confidence = {}
        paramList = []
        numValue = 0
        minDict = {}
        maxDict = {}
        selectValueList = {}
        deselectedConfigs = []
        selectedConfigs = []
        turnList = []
        hideList = []
        configList = [] 
        domain = {}
        parameterDomain = {}
        parameterPosition = {}
        

        #db Queries for configuration visualisation
        name = db.session.query(db.Experiment.name).filter(db.Experiment.idExperiment == expID).first()
        configuration['expName'] = str(name[0])
        solverConfigName =  dict((s.idSolverConfig, s.name) 
                        for s in db.session.query(db.SolverConfiguration).
                            filter(db.SolverConfiguration.Experiment_idExperiment == expID))
        configurable = [p.Parameters_idParameter for p in experiment.configuration_scenario.parameters if p.configurable and p.parameter.name not in ('instance', 'seed')]
        parameterName  =  dict((p.idParameter, p.name) 
                        for p in db.session.query(db.Parameter).
                            filter(db.Parameter.idParameter.in_(configurable)).distinct())
                            
       # start = time.clock()
        for name in parameterName.values():
            parameterDomain[name] = experiment.configuration_scenario.get_parameter_domain(name)

       # print time.clock() - start, "sec domain"
        solverConfigCosts = dict((s.idSolverConfig, s.cost) for s in experiment.solver_configurations) 
        
        ##TODO: query optimieren
        for scn in solverConfigName:
            parameterValue[scn] = dict((pv.Parameters_idParameter, pv.value) 
                            for pv in db.session.query(db.ParameterInstance).
                                filter(db.ParameterInstance.SolverConfig_idSolverConfig == scn).
                                filter(db.ParameterInstance.Parameters_idParameter.in_(parameterName.keys())).
                                filter(db.ParameterInstance.value != '')) 
        for scn in solverConfigName:
            confidence[scn] = int(db.session.query(db.ExperimentResult.idJob).
                            filter(db.ExperimentResult.SolverConfig_idSolverConfig == scn).count())
                   

        paramList.append('confidence')
        paramList.append('performance')
        domain['confidence']='num'
        domain['performance']='num'
        for pd in parameterDomain.keys():
                selectValueList[pd]= []
                if parameterDomain[pd] == "realDomain" or parameterDomain[pd] == "integerDomain":
                    domain[pd] = 'num'
                else:
                    domain[pd] = 'cat'
                                
        #maps the web formular in lists
        if configForm != None:
            for pm in parameterName.values(): 
                if str(pm) in configForm.keys():
                    parameterPosition[pm] = mapPosition(configForm.getlist(pm))                    
                if domain[pm] == "num":
                    indexMin = "min: "+pm
                    minList = []
                    if indexMin in configForm.keys():                    
                        minList = map(str, configForm.getlist(indexMin))
                    minDict[pm]=minList[0]
                    indexMax = "max: "+pm
                    maxList = []
                    if indexMax in configForm.keys():                    
                        maxList = map(str, configForm.getlist(indexMax))
                    maxDict[pm]=maxList[0]
                elif domain[pm] == "cat":
                    index = "select: " +pm
                    if index in configForm.keys():                    
                        select = map(str, configForm.getlist(index))
                        selectValueList[pm]=select
                        
            if "confidence" in configForm.keys():
                parameterPosition["confidence"] = mapPosition(configForm.getlist("confidence"))
            if "performance" in configForm.keys():
                parameterPosition["performance"] = mapPosition(configForm.getlist("performance"))
                
            if "min: confidence" in configForm.keys():
                minList = map(str, configForm.getlist('min: confidence'))
                minDict['confidence']=minList[0]
            if "max: confidence" in configForm.keys():
                maxList = map(str, configForm.getlist('max: confidence'))
                maxDict['confidence']=maxList[0] 
            if "min: performance" in configForm.keys():
                minList = map(str, configForm.getlist('min: performance'))
                minDict['performance']=minList[0]
            if "max: performance" in configForm.keys():
                maxList = map(str, configForm.getlist('max: performance'))
                maxDict['performance']=maxList[0] 
                
            if 'turn' in configForm.keys():
                turnList =  map(str, configForm.getlist('turn'))
            if 'hide' in configForm.keys():
                hideList = map(str, configForm.getlist('hide')) 
                
            if 'solverConfigs' in configForm.keys():
                configList = map(str, configForm.getlist('solverConfigs'))

        #creates a dictionary with values of the parameters of each solverConfig
        for scn in solverConfigName:
            parameterInstance = {} 
            parameter = {}
            
            parameterInstance['name'] = str(solverConfigName[scn])
            n = 2
            for p in parameterValue[scn]: 
                #assigns the value to the parameter of the solverConfig
                parameter[str(parameterName[p])]= str(parameterValue[scn][p])
                #creates a list of parameters              
                if str(parameterName[p]) not in paramList:
                    paramList.append(str(parameterName[p]))
                    
            #creates the list deselectedConfigs of solverConfigs which are deselected if the values are restricted
                if configForm != None and domain[str(parameterName[p])] == 'cat':
                    if "select: "+str(parameterName[p]) in configForm.keys():                 
                        if str(parameterValue[scn][p]) not in selectValueList[str(parameterName[p])]:
                            deselectedConfigs.append(scn)
                        else:
                            if [scn, solverConfigName[scn]] not in selectedConfigs[0]:
                                selectedConfigs.append([scn, solverConfigName[scn]])

                ##TODO: irgendwas stimmt noch im webfrontend mit min max eingabe noch nicht
                elif configForm != None and domain[str(parameterName[p])] == 'num':
                    if float(parameterValue[scn][p]) < float(minDict[str(parameterName[p])]) or float(parameterValue[scn][p]) > float(maxDict[str(parameterName[p])]):
                        deselectedConfigs.append(scn)
                    else:
                        if [scn, solverConfigName[scn]] not in selectedConfigs:
                            selectedConfigs.append([scn, solverConfigName[scn]])
                n += 1
            
                       
            if len(minDict)>0:
                if float(confidence[scn]) < float(minDict['confidence']) or float(confidence[scn]) > float(maxDict['confidence']):                       
                    deselectedConfigs.append(scn)
                else:
                    if [scn, solverConfigName[scn]] not in selectedConfigs:
                        selectedConfigs.append([scn, solverConfigName[scn]])
                if solverConfigCosts[scn] != None:
                    if float(solverConfigCosts[scn]) < float(minDict['performance']) or float(solverConfigCosts[scn]) > float(maxDict['performance']):
                        deselectedConfigs.append(scn)
                    else:
                        if [scn, solverConfigName[scn]] not in selectedConfigs:
                            selectedConfigs.append([scn, solverConfigName[scn]])
                           
            parameter['confidence'] = confidence[scn]
        
            if solverConfigCosts[scn] != None:
                parameter['performance'] = solverConfigCosts[scn]
            else:
                parameter['performance'] = 0.0          
                   
            parameterInstance['parameter']= parameter 
            solverConfig[scn]= parameterInstance
        #chance the position
        if configForm != None:
            tmpList = paramList[:]
            for pl in paramList:
                pos0 = int(parameterPosition[pl][0])-1
                pos1 = int(parameterPosition[pl][1])-1
                if pos0 != pos1:
                    del tmpList[tmpList.index(pl)] 
                    tmpList.insert(pos1, pl)
            paramList = tmpList[:]
        
        i=0
        for pl in paramList:
            values = []
            valueList = []
            minValue = 0
            maxValue = 0
            turn = False
            
            if (pl not in paramAttribute):
                i += 1
            
            #creates a list of possible values (valueList) and an list of values for each parameter
            for scn in solverConfigName:
                if (pl in solverConfig[scn]['parameter']):
                    if (solverConfig[scn]['parameter'][pl] not in valueList):
                        valueList.append(solverConfig[scn]['parameter'][pl])
                    if scn not in deselectedConfigs:
                        values.append(solverConfig[scn]['parameter'][pl])
                else:
                    if scn not in deselectedConfigs:
                        values.append(0)        

            #maps the values of each parameter suitable for domains       
            if domain[pl] == "cat":
                values = classify(values, valueList)
            
            elif domain[pl] == "num":
                values = map(float, values)
                valueList = map(float, valueList)     
                 
            if len(turnList)>0 and (pl in turnList):
                turn = True
                values = turnValue(values)          
            
            #checks if a parameter is shielded
            ##TODO: bei hide veraendert sich im webfrontend die max position noch nicht
            hide = False
            if len(hideList)>0 and (pl in hideList):
                hide = True
            
            positionList = []
            length = len(paramList)
            for p in range(length):
                pos = (p + i -1) % length
                positionList.append(pos+1)   
            
            if numValue < len(values):
                numValue = len(values)    
                        
            if domain[pl] == 'num': 
                if configForm != None and len(minDict[pl])>0 and float(minDict[pl])>=min(valueList) and float(minDict[pl])<=max(valueList):
                    minValue = minDict[pl]
                else:
                    minValue = min(valueList)
                if configForm != None and len(maxDict[pl])>0 and float(maxDict[pl])>=min(valueList) and float(maxDict[pl])<=max(valueList):
                    maxValue = maxDict[pl]
                else:
                    maxValue = max(valueList)
    
                values = project(values)
                paramAttribute[i] = {'values': values,'min': minValue, 'max': maxValue, 'name': pl, 'hide': hide, 'turn': turn, 'positionList': positionList, 'domain': domain[pl]}

                
            elif domain[pl] == 'cat':
                values = project(values)
                paramAttribute[i] = {'values': values,'valueList': valueList, 'selectValueList': selectValueList[pl], 'name': pl, 'hide': hide, 'turn': turn, 'positionList': positionList, 'domain': domain[pl]}
        
        configuration['paramAttribute'] = paramAttribute
        list = []
        for i in range(numValue):
            list.append(i)
        configuration['numValue'] = list
        if configForm != None:
            d = 0
            for sc in selectedConfigs:
                if str(sc[0]) in configList:
                    selectedConfigs[d].append(1)
                else:
                    selectedConfigs[d].append(0)
                d += 1
            print configList   
            configuration['solverConfigs'] = selectedConfigs
        else:
            configuration['solverConfigs'] = solverConfigName.values()
       
    def getConfiguration(self):
        return configuration
    