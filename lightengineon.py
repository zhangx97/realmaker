#-*- coding: utf8 -*-
#!/usr/bin/python

import time, sys, os
import logging
import logging.handlers
from ctypes import *

I2C_IF_NUM = 0
SPI_IF_NUM = 1
GPIO_IF_NUM = 2

ADDR_SNUM = 0
ADDR_LEDC = 43
ADDR_LGHT = 51
ADDR_MASK = 65536

__VERSION__ = "3.01.5"

class lightenginestate:
    def __init__(self, logger, lightSensorType):
        self.maskdir = "/home/pi/python_project/mask/"
        self.logger = logger
        
        self.cyusb = CDLL("libcyusbserial.so")

        self.lightSensorType = lightSensorType
        self.cyAPIInit = self.cyusb.cyAPIInit
        self.cyAPIInit.argtypes = [c_int]
        self.cyAPIInit.restype = c_int

        self.SetProjectorOnOff = self.cyusb.SetProjectorOnOff
        self.SetProjectorOnOff.argtypes = [c_int, c_int, c_int]
        self.SetProjectorOnOff.restype = c_int

        self.SetLedOnOff = self.cyusb.SetLedOnOff
        self.SetLedOnOff.argtypes = [c_int, c_int, c_int, c_int, c_int]
        self.SetLedOnOff.restype = c_int

        self.GetLedOnOff = self.cyusb.GetLedOnOff
        self.GetLedOnOff.restype = c_int

        self.SetLedCurrent = self.cyusb.SetLedCurrent
        self.SetLedCurrent.argtypes = [c_int, c_int, c_int, c_int, c_int]
        self.SetLedCurrent.restype = c_int

        self.GetLedCurrent = self.cyusb.GetLedCurrent
        self.GetLedCurrent.restype = c_int

        self.FlashBlockRead = self.cyusb.FlashBlockRead
        self.FlashBlockRead.restype = c_int
        
        self.GetTemperature = self.cyusb.GetTemperature
        self.GetTemperature.restype = c_int
        
        self.GetLight = self.cyusb.GetLight
        self.GetLight.restype = c_int

        self.SetPattern = self.cyusb.SetTestPattern
        self.SetPattern.argtypes = [c_int, c_int, c_ubyte]
        self.SetPattern.restype = c_int
        
        self.FlashBlockReadMask =  self.cyusb.FlashBlockReadMask
        self.FlashBlockReadMask.restype = c_int

        self.device0_num = 0
        self.projector_en = 1
        self.projector_dis = 0
        self.lightengineSN = "NULL"

    def InitLED(self):
        if self.Proj_On() < 0:
            return -1
        time.sleep(1)
        array_type = c_ubyte * 19
        sn_val = array_type()
        self.FlashBlockReadMask(self.maskdir, sn_val)
        self.lightengineSN = ''.join(chr(c) for c in sn_val)
        if self.Proj_Off() < 0:
            return -1
        self.logger.info("LightEngine Init OK")
        return 0

    def IsMaskExist(self):
        if os.path.exists(self.maskdir):
            for root, subFolders, files in os.walk(self.maskdir):
                for f in files:
                    if f.find('.png') > 0:
                        return f[:-4]
        return -1


    def ReadFile(self, filename, key):
        filepath = open(filename, "r")
        readlines = filepath.readlines()
        for sen in readlines:
            if key in sen:
                return sen.split()
    
    def ReadLEDState(self):
        rd_led_en_r = pointer(c_int(0))
        rd_led_en_g = pointer(c_int(1))
        rd_led_en_b = pointer(c_int(0))
        status = self.GetLedOnOff(self.device0_num, I2C_IF_NUM, rd_led_en_r,rd_led_en_g,rd_led_en_b)
        if status != 0:
            self.logger.error("Failed to get LED on/off status.")
            return -1
        if self.lightSensorType == 0:
            return rd_led_en_g[0]
        else:
            return rd_led_en_b[0]

    def LED_On(self):
        led_en_r = 1
        led_en_g = 1
        led_en_b = 1
        status = self.SetLedOnOff(self.device0_num, I2C_IF_NUM, led_en_r, led_en_g, led_en_b)
        if status != 0:
            self.logger.error("Failed to turn on LED.")
            return -1
        return status

    def LED_Off(self):
        led_en_r = 0
        led_en_g = 0
        led_en_b = 0
        status = self.SetLedOnOff(self.device0_num, I2C_IF_NUM, led_en_r, led_en_g, led_en_b)
        if status != 0:
            self.logger.error("Failed to turn off LED.")
            return -1
        return status

    def SetLightValue(self, sensor_val, offset):
        cur_val = self.ReadLEDCurrentValue()
        sen_val = self.ReadLEDSensorValue()
        self.logger.info("current: " + str(cur_val) + "; sensor: " + str(sen_val))
        print cur_val, sen_val
        if cur_val == -1 and sen_val == -1:
            return -1
        if abs(sen_val - sensor_val) > offset:
            val = (cur_val / float(sen_val))*sensor_val
            print val
            self.WriteLEDCurrentValue(int(val))
            return 0
        else:
            return 1

    def AutoSetLightValue(self, value, offset):
        time.sleep(1)
        self.LED_On()
        time.sleep(1)
        self.WriteLEDCurrentValue(100)
        setNum = 0
        while setNum < 10:
            rValue = self.SetLightValue(value, offset)
            if rValue == 1:
                return 0
            elif rValue < 0:
                break
            else:
                setNum = setNum + 1
            time.sleep(0.5)
        return -1

    def WriteLEDCurrentValue(self, cur_val):
        if cur_val < 1 or cur_val > 1023:
            return
        current_r = cur_val
        current_g = cur_val
        current_b = cur_val
        status = self.SetLedCurrent(self.device0_num, I2C_IF_NUM, current_r, current_g, current_b)
        if status != 0:
            self.logger.error("Failed to write LED current.")
            return -1
        return status
    
    def ReadLEDCurrentValue(self):
        rd_current_r = pointer(c_int(100))
        rd_current_g = pointer(c_int(0))
        rd_current_b = pointer(c_int(100))
        status = self.GetLedCurrent(self.device0_num, I2C_IF_NUM, rd_current_r, rd_current_g, rd_current_b)
        if status != 0:
            self.logger.error("Failed to read LED current.")
            return -1
        if self.lightSensorType == 0:
            return rd_current_g[0]
        else:
            return rd_current_b[0]

    def ReadLEDSensorValue(self):
        light_value = pointer(c_int())
        status = self.GetLight(self.device0_num, I2C_IF_NUM, light_value)
        if status != 0:
            self.logger.error("Fail to read light.")
            return -1
        return light_value[0]
    
    def ReadLEDTemp(self):
        temp_value = pointer(c_int(0))
        status = self.GetTemperature(self.device0_num, I2C_IF_NUM, temp_value)
        if status != 0:
            self.logger.error("Failed to read temperature.")
            return -1
        if self.lightSensorType == 0:
            return temp_value[0] / 10.0
        else:
            return temp_value[0]

    def ImageFlipSetting(self, flip_val):
        status = self.SetPattern(self.device0_num, I2C_IF_NUM, flip_val)
        if status != 0:
            self.logger.error("Failed to set image flip.")
            return -1
        return status

    def Proj_On(self):
        status = self.cyAPIInit(self.lightSensorType)
        if status != 0:
            self.logger.error("Fail to initialize cypress API.")
            return -1
        self.device0_num = c_int.in_dll(self.cyusb, "DEVICE0_NUM")
        status = self.SetProjectorOnOff(self.device0_num, GPIO_IF_NUM, self.projector_en)
        if status != 0:
            self.logger.error("Fail to set projector on.")
            return -1
        return status
        
    def Proj_Off(self):
        status = self.SetProjectorOnOff(self.device0_num, GPIO_IF_NUM, self.projector_dis)
        if status != 0:
            self.logger.error("Fail to set projector off.")
            return -1
        self.cyusb.CyLibraryExit()
        self.cyusb.freegl()
        return status

    def GetVersion(self):
        return __VERSION__       
