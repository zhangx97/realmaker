# -*- coding: utf-8 -*-
#!/usr/bin/python

import time, os, struct, commands
from Tkinter import *
from PIL import Image, ImageTk, ImageChops
import threading
import serial
import serial.tools.list_ports as port_list
from xml.etree import ElementTree
import re
import datetime
import socket,shutil,zipfile
import RPi.GPIO as GPIO
from lightengineon import *
from resin_temp import *
import itertools
import struct, commands
from StringIO import StringIO
import logging
import logging.handlers

def ExceptionMessage(msg):#将错误信息写入日志中
    global logger, PrintException,CurState, states,DevSer

    print msg
    logger.error(msg, exc_info = True)
    PrintException = msg
    if not DevSer is None:
        send_a_cmd(DevSer, 'M90')

    if CurState != states[1] and CurState != 'NULL':
        WriteTextLines('Error', 'rb+')

def enmuerate_serial_port():
    port_serial = list(port_list.comports())#获得所有串口
    for i in range(len(port_serial)):
        try:
            yield list(port_serial[i])[0]
        except EnvironmentError:
            break

def com_search_open(portname):
    global SerialTimeOut, BaudRate
    global logger

    try:
        ser_index = serial.Serial(portname, BaudRate, timeout=10)
        header = ser_index.readline()
        #logger.info("[arduino]recive:"+header)
        if 'Start' in header:
            header=ser_index.readline()
            if 'Dev Init OK' in header:
                ser_index.timeout=SerialTimeOut
                logger.info("search open finish")
                return ser_index
        elif header == "":
            ser_index.timeout=SerialTimeOut
            logger.info("search open finish")
            return ser_index

        ExceptionMessage("Serial Read Error")
        logger.info("Serial Read Error")
        close_serial(ser_index)
        return False
    except Exception, e:
        ExceptionMessage(str(e))
        return False

def close_serial(serialPort):
    global logger

    try:
        if serialPort.isOpen():
            serialPort.close()
    except Exception:
        logger.error('Fail to close serialport', exc_info = True)

#raspberry pi communicate with arduino by serial port ##################
def send_a_cmd(ser, cmd, writeLog = False):
    global PrintState
    global states, logger
    global pluseCount,ifPluse

    print "send_a_cmd", cmd

    try:
        send_cmd = cmd+'\n'
        ser.write(send_cmd)
        if writeLog:
            logger.info("[write to arduino]:"+send_cmd)
        DEVback = ser.readline()

        cmdback = DEVback
        if writeLog:
            logger.info("[recive from arduino]:"+cmdback)
        if cmdback[0:-2] != cmd:
            print "err: "+cmdback[0:-2],cmd
            if cmdback[0:-2] == "Start":
                if writeLog:
                    logger.info("[recive != send]:cmdback == start,following is the cleaning process:")
                    logger.info("[cleaning]:"+ser.readline())
                    logger.info("[cleaning]:"+ser.readline())
            if cmdback[0:6] == 'Press1':
                pluseCountReceived = int(cmdback.split()[-1])
                logger.info("[recive != send]:pluseCountReceived :"+str(pluseCountReceived))
                if pluseCountReceived > 0:
                    logger.info("[recive != send]:get press,stop print...")
                    #ifPluse = True
                    PrintState = states[5]
                else:
                    logger.info("[recive != send]:get press before G28cmd send,following is the cleaning process:")
                    logger.info("[cleaning]:"+ser.readline())
                    logger.info("[cleaning]:"+ser.readline())
                    if pluseCount > 0:
                        PrintState = states[5]
        else:
            ack = ''
            while ack != 'OK':
                DEVback = ser.readline()
                if DEVback != '':
                    cmdback = DEVback
                    ack = cmdback[0:2]
                    if writeLog:
                        logger.info("[recive = send]:twice recive:"+ack)
                    print ack
                    if ack == 'ER':
                        if writeLog:
                            logger.info("[recive = send]:recive error "+ser.readline())
                    if ack == 'pl':
                        strList = cmdback.split(":")
                        logger.info("[recive = send]:pluse adjust")
                        pluseCount = str(int(strList[1])-1000)
                        WriteParam("PluseCount",pluseCount)
                        continue
                    if ack == 'Pr':                        
                        pluseCountReceived = int(cmdback.split()[-1])
                        logger.info("[recive = send]:pluseCountReceived "+str(pluseCountReceived))
                        if pluseCountReceived > 0:
                            logger.info("[recive = send]:get press,stop print...")
                            #ifPluse = True
                            PrintState = states[5]
                            send_a_cmd(ser, "M18",True)
                            continue
                        else:
                            logger.info("[recive = send]:No G28 But Under Pressure,following is the cleaning process:")
                            logger.info("[cleaning]:"+ser.readline())
                            continue
                    break
                else:
                    print "err cmd: ", DEVback
                    #logger.info("[arduino]err:"+DEVback)
                    PrintState = states[1]
                    break
    except Exception, e:
        close_serial(ser)
        PrintState = states[1]
        ExceptionMessage(str(e))
            
def PrintBlackScreen():
    global file_path
    
    imageFile=file_path + "/projection/" + "blackscreen.png"
    image1 = Image.open(imageFile)
    image2 = ImageTk.PhotoImage(image1)
    PreViewImage.configure(image=image2)
    PreViewImage.image = image2
    root.update()

def PrintThread():
    global PrintState, states,logger, isLock
    global isPrintingFlag

    try:
        isPrintingFlag = True
        if isLock or CurState == states[4]:#heat
            logger.info('Fail to start print , device is locked or heating ...')
            return
       
        if not ControlInit():
            return
        print_thread = threading.Thread(target= ControlPrint)
        print_thread.start()
    except Exception, e:
        PrintState = states[1]
        ExceptionMessage(str(e))

def ControlInit():#初始化控制，返回是否成功打开文件
    global finish_count, DevSer, TFSer

    filname = file_path + "/" + "images.zip"
    dirname = file_path + "/" + "images"
    finish_count = 0

    if InputFile(filname, dirname) == 'unknown file':
        return False    

    ReadXmlConf()
    DevSer = com_search_open(DevSer.name)#打开该端口并初始化
    #TFSer = com_search_open(TFSer.name)
    if not DevSer:
        return False
    
    return True

def SelfTest():#自检，有文件缺失什么的，都可以补上
    global light_engine, Heater_Temp, isSleep, TFSer, DevSer, Debug
    global sleepFlag, logger, LOG_FILE, heater_version, ModelType
    
    try:
        FileSizeDel(LOG_FILE, 1024 * 1024 * 1024)
        DetectFile()

        COMList = []
        for key in enmuerate_serial_port():
            if key.startswith('/dev/ttyACM'):
                COMList.append(key)

        for i in range(len(COMList)):
            serialPort = com_search_open(COMList[i])
            print serialPort.name
            serialPort.write('M11\n')
            serialPort.readline()
            back = serialPort.readline()
            if back[0:-2] == 'RealMaker':
                DevSer = serialPort
                WriteParam("DevSerial", DevSer.name)
            elif back[0:-2] == 'RealMaker-TF':
                TFSer = serialPort
        
        if not DevSer is None:
            send_a_cmd(DevSer, 'M94')
        else:
            if ModelType == 3 and Debug == 0:
                ExceptionMessage("Failed to init distance sensor.")
            
        #close_serial(TFSer)
        send_a_cmd(DevSer, "M18")
        close_serial(DevSer)
        #LightengineProjState(False)
        
        #if float(Heater_Temp) == 0:
            #sleepFlag = False
            #return

        HeatingWireOff()
        sleepFlag = False
        """
        if float(Heater_Temp) != 0:
            resin_heater = resintempstate(logger)
            heater_version = resin_heater.GetVersion()
        else:
            heater_version = "0.00"
        """
 
        logger.info("Device Init OK!")
        print "Self-Test"
    except Exception,e:
        ExceptionMessage(str(e))
    
def ControlPrint():#控制打印
    global PrintState, ModelCount, BottomCount, SensorValIndex, file_path
    global lock, PrintException, finish_count,CurState, states
    global logger,isSleep,resin_heater, sleepFlag, nSleepTime, Heater_Temp
    global Material, LightList, curBrightness, ModelName,DevSer, TFSer, curResinTemp, curHeatData
    global pluseCount,hasPluseFunction
    
    try:
        if PrintState == states[1]:#stop
            ControlStop()
            return

        WriteTextLines('Begin')
        WriteParam("TargetLight",str(LightList[Material]))
        curBrightness = 0
        #RaspiCamOn(True)

        if isSleep and float(Heater_Temp) != 0:
            nSleepTime = datetime.datetime.now()
            isSleep = False
            sleepFlag = True
            curResinTemp = ReadHeater()
            curHeatData = datetime.datetime.now()
            #resin_heater = resintempstate(logger)
            #resin_heater.start() 

        if float(Heater_Temp):
            while ReadHeater() < float(Heater_Temp):
                if PrintState == states[1]:
                    ControlStop()
                    return
                CurState = states[4] 
                time.sleep(0.5)

        CurState = states[0]
        SensorValIndex = 0
        logger.info('Begin ready for print...')
        
        #begin print ####
        if not TFSer is None:
            send_a_cmd(TFSer, 'M100',True)

        logger.info("pluseCount to arduino "+str(pluseCount))
        #if(hasPluseFunction == 1):
        send_a_cmd(DevSer,"PRESS_INIT "+ str(pluseCount),True)
        #else:
        #    send_a_cmd(DevSer,"PRESS_INIT "+ str(0))

        for i in range(len(start_cmds)):
            #print PrintState

            send_a_cmd(DevSer, start_cmds[i],True)
            if PrintState == states[2]:
                ControlPause()
            if (PrintState == states[1]):
                ControlStop()
                return
            if(PrintState == states[5]):
                ControlStop()
                CurState = states[5]
                return

        if LightengineProjState(True)<0:
            LightengineProjState(False)
            return

        logger.info('Begin print...')
       
        #tempFlag = 0

        #print model count #####
        while finish_count < ModelCount + BottomCount: 
            build_a_layer(finish_count)
            if PrintState == states[2]:            
                ControlPause()
            if PrintState == states[1]:
                ControlStop()
                return
        
        ControlStop()      
    except Exception, e:
        PrintStop = True
        ExceptionMessage(str(e))
      
def build_a_layer(layer_num):#新建图层
    global LayerThickness, CrackDistance, AscendSpeed, DescendSpeed, SensorValIndex
    global BottomCuringTimes, ResinCuringTime, finish_count, BottomCount
    global file_path, light_engine, ModelCount, LightSensor, PrintException
    global curBrightness, curCurrent, curLEDTemp, states, PrintState,DevSer,SpecialExposeLayer,offset

    logger.info("The platform starts to move")
    if layer_num >= BottomCount:
        if layer_num >= int(SpecialExposeLayer[0]) and layer_num <= int(SpecialExposeLayer[1]):
            LayerResinCuringTime  = float(SpecialExposeLayer[2])
        else:
            LayerResinCuringTime = ResinCuringTime
        TimeMovelayer_up = time.time()
        send_a_cmd(DevSer,("G1 Z{0:.3f} F{1:d}").format(LayerThickness*layer_num+CrackDistance, AscendSpeed))
        send_a_cmd(DevSer,("G1 Z{0:.3f} F{1:d}").format(LayerThickness*(layer_num+1), DescendSpeed))
        TimeMovelayer_down = time.time()
        TimeMovelayer = TimeMovelayer_down - TimeMovelayer_up
        print "TimeMovelayer="+str(TimeMovelayer)
    else:
        LayerResinCuringTime = int(BottomCuringTimes[layer_num])
        TimeMovelayer_up = time.time()
        send_a_cmd(DevSer,("G1 Z{0:.3f} F{1:d}").format(LayerThickness*layer_num+CrackDistance, AscendSpeed))
        send_a_cmd(DevSer,("G1 Z{0:.3f} F{1:d}").format(LayerThickness*(layer_num+1), DescendSpeed))
        TimeMovelayer_down = time.time()
        TimeMovelayer = TimeMovelayer_down - TimeMovelayer_up
        print "TimeMovelayer="+str(TimeMovelayer)
    logger.info("Platform stops moving. layer_num : "+str(layer_num))
    #if light_engine.ReadLEDState() <= 0: #如果光机状态读取异常，结束打印，上报异常
    #    logger.info('Read LED State Error when printing')
    #    PrintException = "Read LED State Error"
    #    logger.info('light engine error when printing')
    #    PrintState = states[1]
    #    return
    
    #printLayerLight = light_engine.ReadLEDSensorValue()
    #printLayerCurrent = light_engine.ReadLEDCurrentValue()
    #printLightTemperature = light_engine.ReadLEDTemp()


    try:
        path = file_path + "/" + "images/{0:0>4}.bmp"
        imageFile = path.format(layer_num)
        #imageFileMask = LayerMask(imageFile)     #layer mask image
        CuringTimeParam = int(LayerResinCuringTime * 60)
        light_engine.SPIPrint_py(CuringTimeParam, imageFile, layer_num)
        time.sleep(1.5)
        #image1 = Image.open(imageFileMask)
        #image2 = ImageTk.PhotoImage(imageFileMask)
        #PreViewImage.configure(image=image2)
        #PreViewImage.image = image2
        #root.update()
    except Exception, e:
        logger.info('UI error when change photo!')
        PrintException = "UI error when change photo!"
        PrintState = states[1]
        return
            
    #timestart = time.time()
    #timeend = time.time()
    #CuringTimePass = timeend - timestart
    #while CuringTimePass < LayerResinCuringTime:
        #root.update()
        #time.sleep(0.1)
        #timeend = time.time()
        #CuringTimePass = timeend - timestart
                
    #print "Real " + str(CuringTimePass)+" senconds Curing" + "count: " + str(layer_num)

    finish_count = finish_count + 1
    #PrintBlackScreen()
    try:
        if layer_num == int((ModelCount + BottomCount) * 0.1 * SensorValIndex):
            logger.info("3 print start")
            dark_image = threading.Thread(target = light_engine.SPIPrint_py, args = (180, "/home/pi/python_project/projection/blackscreen.bmp", 0))
            dark_image.start()
            time.sleep(4)
            SensorValIndex += 1
            curBrightness = light_engine.ReadLEDSensorValue()
            time.sleep(0.5)
            curCurrent = light_engine.ReadLEDCurrentValue()
            time.sleep(0.5)
            curLEDTemp = light_engine.ReadLEDTemp()
            print curBrightness, curCurrent, curLEDTemp
            logger.info('light_brightness:'+str(curBrightness)+'  light_current:'+str(curCurrent)+'  light_temp:'+str(curLEDTemp))
            logger.info("3 print end")
            time.sleep(4)
            #lightval = light_engine.ReadLEDSensorValue()
            #print "====> ", layer_num, lightval
            #if  lightval < (LightSensor * 0.8):
                #PrintException = "LightSensor Value Error!"
    except Exception, e:
        logger.info('fail to record light message while printing')
        PrintException = "Can't get light message!"
        PrintState = states[1]
        return
      
    return True

def ImageProjection(img_name):#图像投影
    global file_path, logger

    try:
        imageFile = file_path + "/projection/" + img_name
        #imageFileMask = LayerMask(imageFile)     #layer mask image
        ret = light_engine.SPIPrint_py(1800, imageFile, 0)
        if ret is not 0:
            logger.info("ImageProjection SPIPrint False")
            return False
        #image1 = Image.open(imageFileMask)
        #image2 = ImageTk.PhotoImage(imageFileMask)
        #PreViewImage.configure(image=image2)
        #PreViewImage.image = image2
        #root.update()#刷新屏幕，投影新图像
    except Exception, e:
        ExceptionMessage(str(e))

def LayerMask(imgPath):#图层掩码
    global mask_img, is_mask

    image_im = Image.open(imgPath)
    im_filter = Image.open(mask_img)

    image_im = image_im.transpose(Image.FLIP_TOP_BOTTOM) #FLIP Y

    if image_im.mode != "RGB":
        image_im = image_im.convert('RGB')
    if im_filter != "RGB":
        im_filter = im_filter.convert('RGB')

    if is_mask:
        im_out = ImageChops.multiply(im_filter, image_im)
        #Full_Image = Image.new("RGB", (1920, 1080))
        #Full_Image.paste(im_out, (0,0,1920,1080))
    else:
        im_out = image_im
        
    return im_out

def ControlContinue():#继续
    global continue_cmds, CurState, states
    global logger
    global isPrintingFlag,moveUpDistance

    isPrintingFlag = True
    CurState = states[3]
    LightengineState(True)#LED OFF
    logger.info('Continue...')
    WriteTextLines('Continue','rb+')
    
def ControlPause():#暂停
    global lock, pause_cmds, states, CurState
    global logger,DevSer
    global isPrintingFlag

    isPrintingFlag = False
    CurState = states[2]
    
    lock.acquire()

    LightengineState(False)
    send_a_cmd(DevSer, ("G1 Z{0} F200").format(str(moveUpDistance)))
    logger.info('pause...')
    WriteTextLines('Pause', 'rb+')
        
    lock.wait()
    lock.release()

    ControlContinue()

def ControlStop():#停止
    global stop_cmds, states, PrintState, CurState, states
    global logger, DevSer,TFSer,PrintException, ModelType, isLock, isLocker
    global isPrintingFlag

    isPrintingFlag = False
    CurState = states[1]#stop
    
    LightengineProjState(False)

    for i in range(len(stop_cmds)):
        send_a_cmd(DevSer, stop_cmds[i])

    PrintState = 'NULL'
    CurState = 'NULL'
    #PrintBlackScreen()
    close_serial(DevSer)
    #RaspiCamOn(False)
    if PrintException == 'NULL':
        if not TFSer is None:
            send_a_cmd(TFSer,'M101')
        WriteTextLines('Finish','rb+')
    
    if isLocker:
        isLock = True
        WriteParam("LockState", "True")
    logger.info('Finish!')
    

def WriteIni(iniPath, nodeKey, nodeValue):#写入初始化文件
    global file_path, logger

    list_content = []

    try:
        f_ini = open(iniPath, "rb")
        for i in f_ini.readlines():
            list_content.append(i)
        f_ini.close()

        _content = ''

        for i in list_content:
            if i.find(nodeKey) >=0:
                i = nodeKey + ' ' + nodeValue + '\r\n'
            _content = _content + i
           
        s_file = open(iniPath, 'wb')
        s_file.writelines(_content)
        s_file.close()
        
    except IOError, e:
        ExceptionMessage(str(e))

#read config.ini and xml: .ini is device's and .xml is accepted #########
def ReadIni(inipath = "RealMakerConfig.ini"):
    global SerialTimeOut, BaudRate, SleepMinTime
    global CrackDistance, AscendSpeed, DescendSpeed,logger
    global TcpHostIp, TcpHostPort, file_path, is_mask, LightSensor, Heater_Temp
    global SVN, isLock, LightList, MovementTime, ModelType, Debug, isLocker
    global lightSensorType, offset
    global pluseCount,hasPluseFunction
    global moveUpDistance
        
    try:
        path = file_path + "/" + inipath
        f_ini = open(path, "r")
        readLines = f_ini.readlines()

        SerialTimeOut = int(SplitFile(readLines, 'SerialTimeOut')[1])
        BaudRate = int(SplitFile(readLines, 'BaudRate')[1])
        #BottomCuringTimes = SplitFile(readLines, 'BottomCuringTimes')[1].split(',')
        CrackDistance = int(SplitFile(readLines, 'CrackDistance')[1])
        AscendSpeed = int(SplitFile(readLines, 'AscendSpeed')[1])
        DescendSpeed = int(SplitFile(readLines, 'DescendSpeed')[1])
        TcpHostIp = SplitFile(readLines, 'TcpHostIp')[1]
        TcpHostPort = int(SplitFile(readLines, 'TcpHostPort' )[1])
        ApplyMask = SplitFile(readLines, 'ApplyMask')[1]
        LightSensor = int(SplitFile(readLines, 'TargetLight')[1])
        Heater_Temp = SplitFile(readLines, 'Heater')[1]
        SleepMinTime = SplitFile(readLines, 'SleepTime')[1]
        SVN = SplitFile(readLines, 'SVN')[1]
        islock = SplitFile(readLines, 'LockState')[1]
        LightList = eval(SplitFile(readLines, 'LightList')[1])
        ModelType = int(SplitFile(readLines, 'ModelType' )[1])
        Debug =  int(SplitFile(readLines, 'Debug' )[1])
        isLocker = SplitFile(readLines, 'Locker')[1]
        lightSensorType = int(SplitFile(readLines, 'LightSensorType')[1])
        offset = int(SplitFile(readLines, 'offset')[1])
        pluseCount = int(SplitFile(readLines, 'PluseCount')[1])
        #hasPluseFunction = int(SplitFile(readLines, 'PluseFunction')[1])

        AscendTime = float(CrackDistance * 60)/float(AscendSpeed)
        DescendTime = float(CrackDistance * 60)/float(DescendSpeed)
        MovementTime = AscendTime + DescendTime
        
        if ApplyMask == "True":
            is_mask = True
        else:
            is_mask = False

        if islock == "True":
            isLock = True
        else:
            isLock = False

        if isLocker == "True":
            isLocker = True
        else:
            isLocker = False
                     
        if str(ModelType) == "5":
            moveUpDistance = 50
        else:
            moveUpDistance = 100

        f_ini.close()
        logger.info("pluseCount:"+str(pluseCount))
    except IOError, e:
        ExceptionMessage(str(e))

#a:追加，'rb+'：二进制打开。最终效果是把最后一行删了并写进去一行
def WriteTextLines(msg, state='a', txtFile="/home/pi/python_project/DeviceLog.txt"):
    global PrintStartTime, ModelName
    
    parts=[PrintStartTime, ModelName, msg, "\n"]
    msg = ' '.join(parts)#使用空格连接
    #msg = PrintStartTime + " " + ModelName + " " + msg + "\n"
    with open(txtFile,state) as f:
        if state == 'a':  #追加打印记录
            f.write(msg.encode('utf-8'))
        elif state == 'rb+': #整个部分为修改最后一行打印信息
            f.seek(0,os.SEEK_END)#seek(0,2)，指针在末尾
            pos=f.tell() - 1#返回当前位置并-1
            while pos > 0 and f.read(1) != "\n":#pos大于0且指针在文件结尾
                pos -= 1
                f.seek(pos, os.SEEK_SET)#SEEK_SET=0
            if pos > 0:
                f.seek(pos, os.SEEK_SET)
                f.truncate()#从当前位置起截断，后面的全删
                f.write('\n' + msg.encode('utf-8'))       
        f.close()

def ReadTextLastLines(num=2, txtFile="/home/pi/python_project/DeviceLog.txt"): #读取文件末尾指定行数 
    try:
        num = int(num)
        filesize = os.path.getsize(txtFile)
        blocksize = 1024
        dat_file = open(txtFile, 'rb')
        last_line = ""
        if filesize > blocksize:
            maxseekpoint = (filesize // blocksize)
            dat_file.seek((maxseekpoint - 1) * blocksize)
        elif filesize:
            dat_file.seek(0, 0)
        lines = dat_file.readlines()
        if len(lines) <= num:
            num = len(lines) - 1
        if lines:
            last_lines = lines[-num:]
        dat_file.close()
        return ''.join(last_lines)
    except Exception,e:
        ExceptionMessage(str(e))
        return 'Fail!'
            
def ReadXmlConf():
    global ResinCuringTime, ModelCount, LayerThickness
    global BottomCuringTimes, BottomCount, ModelName, file_path, PrintStartTime
    global Material, LightList, SpecialExposeLayer

    path = file_path + "/" + "images/model.pack"
    if not os.path.exists(path):
        return

    BottomCount = int(ReadXml('bottom_count'))
    ModelCount = int(ReadXml('count'))
    ResinCuringTime = float(ReadXml('layer_expose_time'))
    LayerThickness = float(ReadXml('thick'))
    BottomCuringTimes = ReadXml('bottom_expose_time').split(',')
    #bottom_curing_time_multiple = ReadXml('bottom_curing_time_multiple')
    #if bottom_curing_time_multiple is None:
    #    BottomCuringTimes = ReadXml('bottom_expose_time').split(',')
    #else:


    ModelName = ReadXml('model_name')
    PrintStartTime = ReadXml('print_time')
    Material = ReadXml('material')
    special = ReadXml('special_expose_time')
    if special != "null" and special != None:
        SpecialExposeLayer = special.split(',')
    

    print "count: ",ModelCount
    print "CuringTime: ", ResinCuringTime
    print "thick: ", LayerThickness
    print "BottomCount: ", BottomCount
    print "BottomCuringTimes", BottomCuringTimes
    print LightList[Material]
    #print "ModelName",ModelName
    

def ReadXml(nodeName, path="images/model.pack"):#读取xml
    global file_path, logger

    path = file_path + "/" + path
    try:
        tree = ElementTree.parse(path)
        root = tree.getroot()
        for node in root:
             if nodeName == node.tag:#返回该标签内的信息
                 return node.text
             #else:
             #    logger.info("nodeName does not exist")

    except IOError, e:
        ExceptionMessage(str(e))

def WriteXml(Arguments, nodeName="print_count", path="PrintData.pack"):
    global file_path, logger
    
    path = file_path +  "/" + path
    try:
        tree = ElementTree.parse(path)
        root = tree.getroot()
        for node in root:
            if nodeName == node.tag:
                node.text = str(Arguments)
        tree.write(path)
    except IOError, e:
        ExceptionMessage(str(e))

def ReadCmd():
    global start_cmds, pause_cmds, stop_cmds, continue_cmds
    global file_path, logger

    try:
        path = file_path + "/" + "print_cmd.cmd"
        f_cmd = open(path, "r")
        readLines = f_cmd.readlines()
        
        start_cmds = SplitFile(readLines, 'start:')[1:]
        pause_cmds = SplitFile(readLines, 'pause')[1:]
        stop_cmds = SplitFile(readLines, 'stop')[1:]
        continue_cmds = SplitFile(readLines, 'continue')[1:]

        f_cmd.close()
                    
    except IOError, e:
        ExceptionMessage(str(e))
        
def UploadProgram(fileName):
    global logger, DevSer, TFSer

    if os.path.basename(fileName)[0:6] == "RMK_TF" and TFSer is None:
            return 'UploadFail!'

    try:
        fileSplit = os.path.splitext(fileName)
        filedirname = sys.path[0]
        logger.info(filedirname)
        
        if fileSplit[1] == '.hex':
            up_cmd = "sudo /usr/share/arduino/hardware/tools/avrdude -C/usr/share/arduino/hardware/tools/avrdude.conf -v -patmega2560 -cwiring"
            file_cmd = "-b115200 -D -Uflash:w:" + fileName + ":i"
            filename = os.path.basename(fileName)[0:6]
            if filename == "RMK_TF":
                tf_cmd = "-P " + TFSer.name
                hexname = [up_cmd, tf_cmd, file_cmd]
            elif filename == "RealMa":
                dev_cmd = "-P" + DevSer.name
                hexname = [up_cmd, dev_cmd, file_cmd]
            hexupload = ' '.join(hexname)
            os.system(hexupload)
        elif fileSplit[1] == ('.pyc'):
            filename = os.path.basename(fileName).split('_V')[0]
            filename = filename + fileSplit[1]
            filesysname = filedirname + '/' + filename
            fileNameBak = filesysname + ".bak"

            if os.path.exists(filesysname):
                if os.path.exists(fileNameBak):
                    os.remove(fileNameBak)
                os.rename(filesysname, fileNameBak)
                
            shutil.move(fileName, filesysname)

        logger.info('upload file success')
        return 'UploadOk！'
    except Exception, e:
        logger.error('Fail to upload file', exc_info = True)
        return 'UploadFail!'
    
def UnzipFile(fileName, dirName):#解压zip
    z_file = zipfile.ZipFile(fileName,'r')
    #z_file.setpassword("realmaker123")
    z_file.extractall(dirName)

def InputFile(fileName, dirName):
    global logger
    
    try:
        if not os.path.exists(fileName):
            ExceptionMessage("unknown unzip file")
            return "unknown file"

        logger.info('begin unzip file ...')
        shutil.rmtree(dirName)
        UnzipFile(fileName, dirName)
        
        fileNameBak = fileName+".bak"
        if os.path.exists(fileNameBak):
            os.remove(fileNameBak)
            
        os.rename(fileName, fileNameBak)
        logger.info('inputfile finish ...')
        return "inputfile!"
    except Exception, e:
        ExceptionMessage(str(e))
        return PrintException
    
def SplitFile(readLines, name):
    for i in readLines:
        if name in i:
            return i.split()

def RestartProgram():
    os.system('sudo reboot')

def Raspistill(images):
    output = commands.getoutput('raspistill -o /home/pi/%s' % images)
    if output == "":
        return "OK"
    return output

def ShutdownProgram():
    #GPIO.output(LED_PIN, GPIO.LOW)
    os.system('sudo shutdown -h now')

def WriteParam(param, value, inipath = "RealMakerConfig.ini"):
    global file_path ,logger

    try:
        path = file_path + "/" + inipath
        WriteIni(path, param, value)
        ReadIni(inipath)
        return True
    except Exception, e:
        ExceptionMessage(str(e))
        return False

def FileOpreation(command, filepath="rmkrecord.txt", param="NULL"):#文件操作
    global file_path

    path = file_path + "/" + filepath
    if command == 'a':
        if os.stat(path).st_size == 0:
            f = open(path, 'w')
            f.write(param)
            f.close()
        else:
            os.system("sed -i '$a %s' %s" % (param, path))
        
    elif command == 'del':
        os.system("sed -i '1,$d' %s" % path)
    elif command == 'rev':       
        os.system("sed -i '$d' %s" % path)

def WriteLightList(key, value):
    global file_path, LightList, LightSensor
    global logger

    try:
        if not value.isdigit():
            logger.info('error light value!')
            return
        
        path = file_path + "/" + "RealMakerConfig.ini"
        LightList[key] = int(value)
        WriteIni(path, 'LightList', ''.join(str(LightList).split()))
        print LightList
    except Exception, e:
        ExceptionMessage(str(e))
    
def WriteLightSensor(lightvalue):
    global file_path, LightSensor
    global logger
    try:
        if not lightvalue.isdigit():
            logger.info('error light value!')
            return
        path = file_path + "/" + "RealMakerConfig.ini"
        WriteIni(path, 'LightSensor', lightvalue)
        LightSensor = lightvalue
    except Exception, e:
        ExceptionMessage(str(e))


def WriteMotorSpeed(command, f_value, s_value):
    global TFSer, CurState, logger

    if CurState != 'NULL' or TFSer is None:
        return

    try:
        f_val = int(f_value)
        s_val = int(s_value)
        if command == "openspeed":
            if f_val > 0 and f_val < 255:
                cmd = ('M30 S%s') % f_val
                send_a_cmd(TFSer, cmd)
            if s_val >0 and s_val < 255:
                cmd = ('M31 S%s') % s_val
                send_a_cmd(TFSer, cmd)
        elif command == "closespeed":
            if f_val > 0 and f_val < 255:
                cmd = ('M27 S%s') % f_val
                send_a_cmd(TFSer, cmd)
            if s_val >0 and s_val < 255:
                cmd = ('M28 S%s') % s_val
                send_a_cmd(TFSer, cmd)
        elif command == "waittime":
            if f_val > 0:
                cmd = ('M15 S%s') % f_val
                send_a_cmd(TFSer, cmd)
            if s_val > 0:
                cmd = ('M16 S%s') % s_val
                send_a_cmd(TFSer, cmd)
        elif command == "model":
            if f_value >=0:
                cmd = ('M19 S%s') % f_val
                send_a_cmd(TFSer, cmd)
                
        logger.info(cmd)
    except Exception, e:        
        ExceptionMessage(str(e))
    
def InitPrintState():
    global info
    
    info = dict()
    info = {}.fromkeys(['PrintState','CurrentCount','Exception',
                        'ResinCuringTime','ModelCount','LayerThickness',
                        'ModelName','BottomCount','LightTarget','Heater',#'Debug',
                        'LightCurrent', 'CurCurrent','CurTemperature','PrintTime',#'SpecialExposeLayer',
                        'SVN','LockState','LightEngineSN','MovementTime','Material','BottomCuringTime'#'PluseStatus'
                        ])

def ReadState():
    global info, PrintException, ModelType, Debug
    global PrintState, finish_count, CurState
    global ResinCuringTime, ModelCount, LayerThickness, BottomCount
    global file_path, LightSensor, LightSensor, Heater_Temp
    global curBrightness, curCurrent, curLEDTemp, PrintStartTime
    global SVN, isLock, lightengineSN, Material, BottomCuringTimes, SpecialExposeLayer
    global ifPluse

    info['ResinCuringTime'] = str(ResinCuringTime)
    info['ModelCount'] = str(ModelCount)
    info['LayerThickness'] = str(LayerThickness)
    info['ModelName'] = ModelName
    info['BottomCount'] = str(BottomCount)
    info['PrintTime'] = PrintStartTime
    info['Material'] = Material
    info['BottomCuringTime'] = ",".join(BottomCuringTimes)
    #info['SpecialExposeLayer'] = ",".join(SpecialExposeLayer)

    info['PrintState'] = CurState
    info['Exception'] = PrintException
    info['CurrentCount'] = str(finish_count)
    info['LightTarget'] = str(LightSensor)
    info['Heater'] = Heater_Temp + ',' + str(ReadHeater())
    info['LightCurrent'] = str(curBrightness)
    info['CurCurrent'] = str(curCurrent)
    info['CurTemperature'] = str(curLEDTemp)
    info['SVN'] = SVN
    info['LockState'] = str(isLock)
    info['LightEngineSN'] = lightengineSN
    info['MovementTime'] = str(MovementTime)
    #info['Debug'] = str(Debug)
    #info['PluseStatus'] = str(ifPluse)

    if ModelType != 0:
        if 'ModelType' not in info:
            info['ModelType'] = str(ModelType)
    else:
        if 'ModelType' in info:
            del info['ModelType']
    
    data_info = ""
    for key, value in info.items():
        data_info += key + ": " +value + "\n"
    
    return "state!" + data_info

def initParam():
    global ResinCuringTime, ModelCount, LayerThickness
    global BottomCount, ModelName, PrintStartTime, Material, BottomCuringTimes, SpecialExposeLayer
    
    ResinCuringTime = 0.00
    ModelCount = 0
    LayerThickness = 0.00
    BottomCount = 0
    ModelName = "NULL"
    Material = "NULL"
    BottomCuringTimes = ['0','0','0','0','0']
    SpecialExposeLayer = ['0','0','0']
    PrintStartTime = "2017-01-01 00:00:00"

def getVersion():
    global VERSION, light_engine, heater_version

    v_info = dict()
    v_info = {}.fromkeys(['rmkVersion', 'nvmVersion'])

    v_info['rmkVersion'] = VERSION
    v_info['nvmVersion'] = light_engine.GetVersion()

    data_info = ""
    for key, value in v_info.items():
        data_info += key + ": " +value + "\n"
    
    return "version!" + data_info    

def HelpMsgShow():
    HelpInfo = dict()
    HelpInfo = {}.fromkeys(['start','continue','stop','cancel','state','inputfile'])

    HelpInfo['start'] = 'print start'
    HelpInfo['continue'] = 'continue print'
    HelpInfo['stop'] = 'stop print'
    HelpInfo['cancel'] = 'cancel last print'
    HelpInfo['state'] = 'state information'
    HelpInfo['inputfile'] = 'unzip upload file'

    data_info = ""
    for key, value in HelpInfo.items():
        data_info += key + ": " +value + "\n"
    
    return "help!" + data_info   
    
#Tcp Server: accept a new client create a thread #####
def TcpMessageProcess(Msg, cs):
    global PrintState, file_path, CurState
    global LightSensor, logger, VERSION, PrintException
    global isPrintingFlag

    paramList = ['SVN', 'LockState', 'Heater', 'TargetLight', 'ModelType', 'Debug', 'LockState']
    doorParam = ['openspeed', 'closespeed', 'waittime', 'model']

    if Msg != "state":
        logger.info('recv: %s' % Msg)
        print 'recv: ', Msg

    if Msg == 'state':
        data = ReadState().encode('gb2312')
        cs.send(data)
        return
    
    if Msg == 'help':
        cs.send(HelpMsgShow())
        return

    if Msg == CurState:
        logger.info('Repeat instruction ...')
        return	

    lock.acquire()
    PrintState = Msg
    logger.info('printstate: %s' % PrintState)

    cmd = Msg.split()[0]
    if cmd == 'continue' or Msg == 'stop':
        cs.send(Msg + '!')
        lock.notify()
    elif cmd == 'pause':
        cs.send(Msg + '!')
    elif cmd == 'start':
        cs.send(Msg + '!')
        if not isPrintingFlag:
            PrintThread()
    elif cmd == 'cancel':
        CancelLastPrint()
        cs.send(Msg + '!')
    elif cmd == 'inputfile':
        #loadstr = InputFile(filname, dirname)
        #cs.send(loadstr)
        #logger.info(loadstr)
        cs.send(Msg + '!')
    elif cmd == 'reboot':
        cs.send(Msg + '!')
        RestartProgram()
    elif cmd == 'clear':
        PrintException = 'NULL'    
    elif cmd == 'shutdown':
        cs.send(Msg + '!')
        ShutdownProgram()
    elif cmd == 'version':
        cs.send(getVersion())
    elif cmd in paramList:
        WriteParam(Msg.split()[0], Msg.split()[1])
        cs.send(Msg + '!')
    elif cmd == 'LightList':
        WriteLightList(Msg.split()[1], Msg.split()[2])
        cs.send(Msg + '!')
    elif cmd in doorParam:
        WriteMotorSpeed(cmd, Msg.split()[1], Msg.split()[2])
        cs.send(Msg + '!')
    elif cmd == 'PrintRecord':
        cs.send(ReadTextLastLines(Msg.split()[1])+'!')
    elif cmd == 'still':
        cs.send(Raspistill(Msg.split()[1]) + '!')
    elif cmd == 'addrecord':
        FileOpreation('a', Msg.split()[1], Msg.split()[2])
        cs.send(Msg + '!')
    elif cmd == 'delrecord':
        FileOpreation('del', Msg.split()[1])
        cs.send(Msg + '!')
    elif cmd == 'revrecord':
        FileOpreation('rev', Msg.split()[1])
        cs.send(Msg + '!')
    elif cmd == 'projection':
        LightengineProjState(True)
        ImageProjection(Msg.split()[1])
        logger.info(Msg)
        cs.send(Msg + '!')
    elif cmd == 'upload':
        cs.send(UploadProgram(Msg.split()[1]))
    elif cmd == 'LED':
        LEDState = Msg.split()[1]
        if LEDState == 'ON':            
            LightengineProjState(True)
        elif LEDState == 'OFF':
            LightengineProjState(False)
        elif LEDState == 'up':
            LightengineLedState(True)
        elif LEDState == 'down':
            LightengineLedState(False)
        cs.send(Msg + '!')
    elif cmd == 'display':
        ImageProjection(Msg.split()[1])
        cs.send(Msg + '!')
    elif cmd == 'adjust':
        AdjustPlatform(Msg.split()[1:])
        logger.info(cmd)
        cs.send(Msg + '!')
    elif cmd == 'pluseCalibrate':
        PluseCalibrate()
    elif cmd == 'repluse':
        CancelPluseState()
    elif cmd == 'scaling':
        cs.send(Msg + ' ' + ReadPCConfigIni("PCMagnification") + '!')
    elif cmd == 'getBottomTime':
        cmdType = Msg.split()[1]
        cs.send("bottomTime" + ' ' + ReadPCConfigIni(cmdType) + '!' )
    elif cmd == 'proj_on':
        light_engine.Proj_On()
    elif cmd == 'proj_off':
        light_engine.Proj_Off()
    elif cmd == 'testprint':
        light_engine.Proj_On()
        time.sleep(2)
        dark_image = threading.Thread(target = light_engine.SPIPrint_py, args = (1800, "/home/pi/python_project/projection/test.bmp", 0))
        dark_image.start()
        logger.info("dark_image test")
        time.sleep(4)
        logger.info("dark_image test four")
        dac = light_engine.ReadLEDCurrentValue()
        sensor = light_engine.ReadLEDSensorValue()
        ledtemp = light_engine.ReadLEDTemp()
        logger.info("test")
        logger.info("dac: "+str(dac)+" sensor: "+str(sensor)+" ledtemp: "+str(ledtemp))

    else:
        cs.send("Unknown command!")

         
    lock.release()

def TcpServerConnection(cs, addr):
    #print 'Accept new connection from %s:%s...' % addr
    cs.send('Welcome!')
    while True:
        ra = cs.recv(512)
        #print ra
        if ra == 'exit' or not ra:
            break
        TcpMessageProcess(ra, cs)
    cs.close()
    #print 'Connection from %s:%s closed.' % addr

def ScanServer():
    global SVN, TcpHostPort
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)#ipv4 udp
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.settimeout(1)
    logger.info("start UDP broadcast")
    print("start UDP broadcast")
    while (True):
        time.sleep(1)
        try:
            s.sendto(('realmaker ' + SVN).encode('utf-8'), ('<broadcast>', TcpHostPort))
            #logger.info("broadcast: " + s.getsockname()[0])
        except Exception, e:
            logger.info("broadcast timeout: " + str(e))

def UsbAutoStartThread():
    while true:
        time.sleep(1)
        if os.path.exists("/mnt/slicepack/image.zip"):
            os.system("sudo cp /mnt/slicepack/image.zip /home/pi/python_project")

def TcpServerLink():
    global TcpHostIp, TcpHostPort, logger

    logger.info("Start Get Host IP")
    TcpHostIp = get_host_ip();
    logger.info('Host IP: ' + TcpHostIp)
    print('Host IP: ' + TcpHostIp)
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        sock.bind((TcpHostIp, TcpHostPort))
        sock.listen(2)
        print 'Waiting for connection...'
        
        while True:
            cs, addr = sock.accept()
            t = threading.Thread(target=TcpServerConnection, args=(cs, addr))
            t.start()
    except Exception, e:
        ExceptionMessage(str(e))

def IndexHeaterDir():
    global TEMP_PATH
    
    str_dirs = os.listdir(TEMP_PATH)
    for dirs in str_dirs:
        if dirs.startswith('28'):
            dir_path = dirs
            return dir_path
    return "null"
                        
def ReadHeater():
    global Heater_Temp, TEMP_PATH 

    try:
        if float(Heater_Temp) == 0:
            return 0.0

        dir_path = IndexHeaterDir()
        if dir_path  == "null":
            ExceptionMessage("Failed to read heater data.")
            return 0.0
         
        f_tmp = open(TEMP_PATH + dir_path + "/" + "w1_slave")
        text = f_tmp.read()
        f_tmp.close()
        temp = text.split("\n")[1].split(" ")[9]
        temp = float(temp[2:])/1000
        return temp
    except Exception, e:
        ExceptionMessage(str(e))
        return 0.00       
    
def enum(**enums):
    return type('Enum',(),enums)

def LightengineLedState(led_state):
    global light_engine

    if led_state:
        light_engine.LED_On()
    else:   
        light_engine.LED_Off()
    time.sleep(1)
    return light_engine.ReadLEDState()
    

def LightengineProjState(proj_state):
    global light_engine

    #PrintBlackScreen()

    if proj_state:
        for i in range(20):
            status = light_engine.Proj_On()
            if status == 0:
                logger.info("Successfully set projector on.")
                time.sleep(2)
                break
        if LightengineState(True) < 0:
            ExceptionMessage("LED ERR")
            return -1          
    else:
        light_engine.Proj_Off()
    return 0

def InitPowerPin():
    GPIO.setmode(GPIO.BCM)#BCM GPIO
    GPIO.setwarnings(False)
    GPIO.setup(DEVICE_POWER_PIN, GPIO.IN)
    GPIO.setup(DEVICE_TEMP_PIN, GPIO.OUT)
    GPIO.setup(LED_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                
def InitLightengine():
    global light_engine,logger, lightengineSN
    global lightSensorType

    light_engine = lightenginestate(logger, lightSensorType)
    status = light_engine.InitLED()
    if status < 0:
        logger.info(status)
        ExceptionMessage("Failed to init LED.")
        return -1
    lightengineSN = light_engine.lightengineSN

def SetLEDOnIndex(set_num):
    global light_engine

    num = 0
    while num < set_num:
        if light_engine.LED_On() < 0:
            light_engine.Proj_Off()#关闭光机
            time.sleep(10)
            light_engine.Proj_On()
            time.sleep(1)
            num = num + 1
        else:
            return 0
    return -1
            
    
def LightengineState(state):
    global light_engine, offset

    logger.info("LightengineState start")
    if state :
        dark_image = threading.Thread(target = light_engine.SPIPrint_py, args = (600, "/home/pi/python_project/projection/blackscreen.bmp", 0))
        dark_image.start()
        #logger.info("dark_image 1337")
        time.sleep(4)
        status = 0
        if status == 0:
            #logger.info("dark_image 1341")
            status = light_engine.AutoSetLightValue(LightSensor,offset)
            #logger.info("dark_image 1343")
            if status < 0:
                ExceptionMessage("RMK-LightengineState: Set Light Value Error.")
                return -1
            logger.info("LightengineState end")
            time.sleep(2)
        else:
            ExceptionMessage("RMK-LightengineState: True On LED Error.")
            return -1         
    else:
        #status = light_engine.LED_Off()
        status = light_engine.Proj_Off()
        if status < 0:
            ExceptionMessage("RMK-LightengineState: Trun Off LED Error.")
            return -1
    return 0

def HeatingWireOn():
    global pinState, logger
    
    logger.info('heater-pin on')
    GPIO.output(DEVICE_TEMP_PIN, GPIO.HIGH)
    pinState = 1

def HeatingWireOff():
    global pinState, logger
    
    logger.info('heater-pin off')
    GPIO.output(DEVICE_TEMP_PIN, GPIO.LOW)
    pinState = 0
    
"""
def AutoResinHeating():
    global Heater_Temp, sleepFlag, TempDeviation, pinState

    while True:
        if Heater_Temp == 0 or isSleep:
            time.sleep(2)
            continue

        if ReadHeater() - float(Heater_Temp) > TempDeviation and pinState:
            HeatingWireOff()
        elif ReadHeater() < float(Heater_Temp) and not pinState:
            HeatingWireOn()
        time.sleep(1)

    HeatingWireOff()
"""

def AutoResinHeating():
    global Heater_Temp, sleepFlag, TempDeviation, pinState

    while True:
        h_val = ReadHeater()
        
        if float(Heater_Temp) == 0 or isSleep or h_val == 0.0:
            if pinState:
                HeatingWireOff()
            time.sleep(2)
            continue

        if h_val - float(Heater_Temp) > TempDeviation and pinState:
            HeatingWireOff()
        elif h_val < float(Heater_Temp) and not pinState:
            HeatingWireOn()
        time.sleep(1)
        

def AutoSleepThread():
    global PrintState, states, nSleepTime,isSleep,states, curResinTemp, curHeatData
    global DEVICE_POWER_PIN, sleepFlag, SleepMinTime, Heater_Temp

    if float(Heater_Temp) == 0:
        return
    
    while True:  
        time.sleep(1)

        """ #加热状态下,长时间温度检测,如果温度未变化就报错提醒
        if CurState == states[4] and curHeatData != 0 and curResinTemp != 0:
           curData = datetime.datetime.now()
           if ((curData - curHeatData).seconds)/60 > 5:
               if ReadHeater() - curHeatData < 2:
                   ExceptionMessage("Abnormal Temperature Sensor Data.")
        """
       
        if CurState != "NULL" :
            nSleepTime = datetime.datetime.now()
            continue

        SleepTime = datetime.datetime.now()
        seconds = (SleepTime - nSleepTime).seconds
        minutes = seconds / 60
        #print hours
        if minutes >= int(SleepMinTime) and sleepFlag:
            print "SLEEP"
            HeatingWireOff()
            isSleep = True
            sleepFlag = False

def InitLog():
    global logger, LOG_FILE

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(LOG_FILE)
    handler.setLevel(logging.INFO)   
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

def FileSizeDel(filename, maxsize):
    if os.path.getsize(filename) > (maxsize):
        os.remove(filename)
        InitLog()

def RaspiCamOn(enable):
    global is_Cam
    
    if not is_Cam:
        return

    if enable:
        os.system("sudo sh /home/pi/.rmkcfg/rmk_cam.sh")
    else:
        info = commands.getoutput("ps aux | grep './mjpg_streamer'")
        infos = info.split()
        if len(infos) > 1:
            cmd = "sudo kill -9 '%s'" % infos[1]
            os.system(cmd)

def GetLocalIP():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect(('8.8.8.8', 80))
    addr, port = sock.getsockname()
    sock.close()   
    return addr

def press_callback(channel):
    global isLock, CurState, logger     

    if CurState == "NULL" and GPIO.input(LED_PIN):
        isLock = False
        WriteParam("LockState", "False")
        logger.info("Release the print lock!")
        
def get_host_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(1)
    logger.info("Host IP Get: connect  12");
    while True:
        try:
            s.connect(('8.8.8.8', 80))
            logger.info("Host IP Get: Get IP");
            ip = s.getsockname()[0]
            if ip.find("169") >0:
                continue
            else:
                logger.info("final ip"+str(ip))
                break;
        except Exception,e:
            logger.info("Get Host IP: " + str(e))
            time.sleep(1)
    s.close()
    return ip
                    
def DetectFile():
    global file_path, TcpHostIp, mask_img, is_Cam, lightengineSN
    global fileDevLog

    fileName = file_path + "/" + "rmkrecord.txt"
    fileNamebak = file_path + "/" + "rmkrecordbak.txt"
    fileDeviceLog = file_path + "/" + "DeviceLog.txt"
    filemaskdir = file_path + "/" + "mask/"
    fileimgdir = file_path + "/" + "images"
    if not os.path.exists(fileName):
        f = open(fileName, 'w')
        f.close()
    if not os.path.exists(fileNamebak):
        f = open(fileNamebak, 'w')
        f.close()
    if not os.path.exists(fileDeviceLog):
        f = open(fileDeviceLog, 'w')
        f.write('No Print Record\n')
        f.close()
    if not os.path.exists(fileimgdir):
        os.makedirs(fileimgdir)

    #if lightengineSN != "NULL":
        #mask_img = filemaskdir + lightengineSN + ".png"
        
    if os.path.exists(filemaskdir):
        for root, subFolders, files in os.walk(filemaskdir):#遍历文件
            for f in files:
                if f.find('.png') > 0:
                    mask_img = filemaskdir + f

def AdjustPlatform(cmdList):
    global DevSer
    global pluseCount
    cmd = " ".join(cmdList)
    logger.info("receive cmd adjust machine: "+cmd)
    cmdToMachine=com_search_open(DevSer.name)
    if not DevSer is None:
        logger.info("serial is exist: "+DevSer.name)
        logger.info("start push cmd")
        send_a_cmd(cmdToMachine,"G91")
        if(cmd == 'G28'):
            send_a_cmd(cmdToMachine,"PRESS_INIT "+str(pluseCount))
        send_a_cmd(cmdToMachine,cmd)
    close_serial(cmdToMachine)

def PluseCalibrate():
    global DevSer
    logger.info("receive cmd adjust pluse")
    cmdToMachine=com_search_open(DevSer.name)
    if not DevSer is None:
        logger.info("serial is exist: "+DevSer.name)
        logger.info("start calibrate pluse")
        send_a_cmd(cmdToMachine,"G15")
        send_a_cmd(cmdToMachine,"PRESS_INIT 1300000000")
        send_a_cmd(cmdToMachine,"G28")
        send_a_cmd(cmdToMachine,"M18")
    close_serial(cmdToMachine)

def CancelPluseState():
    global CurState,PrintState
    #ifPluse = False
    CurState = 'NULL'
    PrintState = 'NULL'

def ReadPCConfigIni(cmdType):
    global file_path, PCMagnification, MX, MXSpci, YG, YGSpci, DB, DBSpci, ZJ, ZJSpci, YY, YYSpci
    file=file_path+"/"+"PCConfig.ini"
    if not os.path.isfile(file):
        file_pcconfig = open(file, 'w')
        file_pcconfig.write("PCMagnification 1\n") 
        file_pcconfig.write("MX 5,5,3,3,3\n")
        file_pcconfig.write("MXSpci 1,1,1,1,1\n")
        file_pcconfig.write("YG 10,10,5,5,5\n")
        file_pcconfig.write("YGSpci 10,10,5,5,5\n")
        file_pcconfig.write("DB 20,20,10,10,10\n")
        file_pcconfig.write("DBSpci 20,20,10,10,10\n")
        file_pcconfig.write("ZJ 20,20,10,10,10\n")
        file_pcconfig.write("ZJSpci 20,20,10,10,10\n")
        file_pcconfig.write("YY 20,20,10,10,10\n")
        file_pcconfig.write("YYSpci 20,20,10,10,10\n")
        file_pcconfig.close()
        logger.info("Create PCConfig.ini")
    file_pcconfig = open(file, 'r')
    readLines = file_pcconfig.readlines()
    PCMagnification = SplitFile(readLines, 'PCMagnification')[1]
    MX = SplitFile(readLines, 'MX')[1]
    MXSpci = SplitFile(readLines, 'MXSpci')[1]
    YG = SplitFile(readLines, 'YG')[1]
    YGSpci = SplitFile(readLines, 'YGSpci')[1]
    DB = SplitFile(readLines, 'DB')[1]
    DBSpci = SplitFile(readLines, 'DBSpci')[1]
    ZJ = SplitFile(readLines, 'ZJ')[1]
    ZJSpci = SplitFile(readLines, 'ZJSpci')[1]
    YY = SplitFile(readLines, 'YY')[1]
    YYSpci = SplitFile(readLines, 'YYSpci')[1]
    file_pcconfig.close()
    if cmdType == "init":
        logger.info("PCConfig.init is exist")
    elif cmdType == "PCMagnification":
        return PCMagnification
    elif cmdType == "MX":
        return MX
    elif cmdType == "MXSpci":
        return MXSpci
    elif cmdType == "YG":
        return YG
    elif cmdType == "YGSpci":
        return YGSpci
    elif cmdType == "DB":
        return DB
    elif cmdType == "DBSpci":
        return DBSpci
    elif cmdType == "ZJ":
        return ZJ
    elif cmdType == "ZJSpci":
        return ZJSpci
    elif cmdType == "YY":
        return YY
    elif cmdType == "YYSpci":
        return YYSpci
    else:
        logger.info("ReadPCConfigIni error cmdType")

    
global root, PrintState, PrintException
global states, CurState, finish_count
global file_path, mask_img, TEMP_PATH
global ResinCuringTime, ModelCount, LayerThickness
global nSleepTime, isSleep, sleepFlag, pinState
global curBrightness, curCurrent, curLEDTemp
global DEVICE_POWER_PIN, VERSION, ModelType, Debug, TFSer, DevSer, isLocker
global logger, LOG_FILE, is_Cam, lightengineSN, TempDeviation, curResinTemp, curHeatData
global lightSensorType, offset
global pluseCount,ifPluse,hasPluseFunction

DEVICE_POWER_PIN= 16
DEVICE_TEMP_PIN = 20
PRESS_PIN=17
LED_PIN = 23
ModelType = 0
VERSION = '4.02.15'
TEMP_PATH = "/sys/bus/w1/devices/"
file_path = "/home/pi/python_project"

PrintException = 'NULL'
PrintState = 'NULL'
CurState = 'NULL'
states = ['start', 'stop', 'pause', 'continue', 'heat','pluse']
finish_count = 0
ResinCuringTime = 0
ModelCount = 0
lightengineSN = "NULL"
LayerThickness = 0
curBrightness = 0
curCurrent = 0
curLEDTemp = 0
TempDeviation = 5.0
pinState= 0
curResinTemp = 0
curHeatData = 0
TFSer = None
DevSer = None
isLocker = False
#file_path = sys.path[0]
mask_img = file_path + "/" + "mask.png"
LOG_FILE = file_path + "/" + 'info.log'
isSleep = True
is_Cam = False
nSleepTime = datetime.datetime.now()
lightSensorType = 0
offset = 1
ifPluse= False
hasPluseFunction = 0
isPrintingFlag = False #true表示正在打印
moveUpDistance = 50 #平台回到最上方要走的距离
PCMagnification = 1 #模型缩放比例
MX = "5,5,3,3,3"
MXSpci = "1,1,1,1,1"
YG = "10,10,5,5,5"
YGSpci = "10,10,5,5,5"
DB = "20,20,10,10,10"
DBSpci = "20,20,10,10,10"
ZJ = "20,20,10,10,10"
ZJSpci = "20,20,10,10,10"
YY = "20,20,10,10,10"
YYSpci = "20,20,10,10,10"


#Read RealMakerConfig.ini and model.pack#########
initParam()
InitLog()
ReadIni()
#ReadXmlConf()
ReadCmd()

#init print state #########
InitPrintState()
InitLightengine()
InitPowerPin()

#root = Tk()
#root.attributes("-fullscreen", True)
#f = Frame(root, width=1920, height=1080)
#PreViewFrame = Frame(f)
#PreViewFrame.place(relx=0.5, rely=0.5, anchor=CENTER)
#imageFile = file_path + "/projection/" + "blackscreen.png"
#imageSplash = ImageTk.PhotoImage(Image.open(imageFile))
#PreViewImage = Label(PreViewFrame, image=imageSplash)
#PreViewImage.pack()
#f.pack()

ReadPCConfigIni("init")

#power on Self-test
SelfTest()

#PrintThread()
GPIO.add_event_detect(LED_PIN, GPIO.FALLING, press_callback, bouncetime=30)
lock = threading.Condition()
scan_server = threading.Thread(target=ScanServer)
scan_server.start()
Tcp_Server = threading.Thread(target= TcpServerLink)
Tcp_Server.start()
#usb_start_thread = threading.Thread(target= UsbAutoStartThread)
#usb_start_thread.start()
#time.sleep(2)
ast = threading.Thread(target= AutoSleepThread)
ast.start()
heat_thread = threading.Thread(target = AutoResinHeating)
heat_thread.start()
root.mainloop()
