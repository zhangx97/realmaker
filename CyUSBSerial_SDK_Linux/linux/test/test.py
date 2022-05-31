# -*- coding: utf8 -*-
#!/usr/bin/python

from ctypes import *

CY_STRING_DESCRIPTOR_SIZE = 256
CY_MAX_DEVICE_INTERFACE = 5

class CY_DATA_BUFFER(Structure):
    _fields_ = [("buffer", POINTER(c_ubyte)),("length", c_uint),("transferCount", c_uint)]

class CY_I2C_DATA_CONFIG(Structure):
    _fields_= [("slaveAddress", c_ubyte),("isStopBit", c_bool),("isNakBit",c_bool)]

class CY_VID_PID(Structure):
    _fields_=[("vid", c_ushort), ("pid", c_ushort)]

class CY_DEVICE_INFO(Structure):
    _fields_ = [
            ("vidPid", CY_VID_PID),
            ("numInterfaces", c_ubyte),
            ("manufacturerName", c_ubyte * CY_STRING_DESCRIPTOR_SIZE),
            ("productName", c_ubyte * CY_STRING_DESCRIPTOR_SIZE),
            ("serialNum", c_ubyte * CY_STRING_DESCRIPTOR_SIZE),
            ("deviceFriendlyName", c_ubyte * CY_STRING_DESCRIPTOR_SIZE),
            ("deviceType", c_uint * CY_MAX_DEVICE_INTERFACE),
            ("deviceClass", c_uint * CY_MAX_DEVICE_INTERFACE),
            ("deviceBlock", c_uint)]

def initCyDevice():
    global cyusb, cyDeviceNum, cyInterfaceNum

    cyDeviceNum = 0
    cyInterfaceNum = 0

    cyusb = CDLL('libcyusbserial.so')
    cyinit = cyusb.CyLibraryInit
    cyinit.argtypes = []
    cyinit.restype = c_uint
    rStatus = cyinit()
    if rStatus:
        print "CY: Error in Doing library init Error NO:<%d> \n" % rStatus
        return False

    return findI2cDeviceNum()

def isCypressDevice(deviceNum):
    global cyusb

    handle = c_void_p()
    array_type  = c_ubyte * 6
    sig = array_type()

    cyopen = cyusb.CyOpen
    cyopen.argtypes = [c_uint, c_uint]
    cyopen.restype = c_uint

    cygetsig = cyusb.CyGetSignature
    cygetsig.argtypes = [c_void_p, POINTER(c_ubyte)]
    cygetsig.restype = c_uint

    cyclose = cyusb.CyClose
    cyclose.argtypes = [c_void_p]
    cyclose.restype = c_uint
 
    rStatus =  cyopen(deviceNum, 0, byref(handle))
    if not rStatus:
        rStatus = cygetsig(handle, sig)
        if not rStatus :
            cyclose(handle)
            return True
        else:
            cyclose(hanlde)
            return False
    else:
        return False

def findI2cDeviceNum():
    global cyusb, cyDeviceNum, cyInterfaceNum

    numDevices = c_int(0)
    numInterfaces = 0
    interfaceNum = 0

    cygetinfo = cyusb.CyGetDeviceInfo
    cygetinfo.argtypes = [c_int, POINTER(CY_DEVICE_INFO)]
    cygetinfo.restype = c_uint

    cyusb.CyGetListofDevices(byref(numDevices))
    
    deviceInfo = CY_DEVICE_INFO()

    for devNum in range(pointer(numDevices)[0]):
        rStatus = cygetinfo(devNum, byref(deviceInfo))
        if not rStatus:
            if not isCypressDevice(devNum):
                continue
            numInterfaces = deviceInfo.numInterfaces
            while numInterfaces:
                if deviceInfo.deviceClass[interfaceNum] == 255:
                    if deviceInfo.deviceType[interfaceNum] == 3:
                        cyDeviceNum = devNum
                        cyInterfaceNum = interfaceNum
                        return True

                interfaceNum += 1
                numInterfaces -= 1
    return False

def i2cReadData(slaveaddr, regaddr, length, rData):
    global cyusb, cyDeviceNum, cyInterfaceNum

    handle = c_void_p()
    array_type  = c_ubyte * length
    rbuffer = array_type()

    cyopen = cyusb.CyOpen
    cyopen.argtypes = [c_uint, c_uint]
    cyopen.restype = c_uint

    cyclose = cyusb.CyClose
    cyclose.argtypes = [c_void_p]
    cyclose.restype = c_uint
 
    cyi2cwrite = cyusb.CyI2cWrite
    cyi2cwrite.argtypes = [c_void_p, POINTER(CY_I2C_DATA_CONFIG), POINTER(CY_DATA_BUFFER), c_uint]
    cyi2cwrite.restype = c_uint
 
    cyi2cread = cyusb.CyI2cRead
    cyi2cread.argtypes = [c_void_p, POINTER(CY_I2C_DATA_CONFIG),POINTER(CY_DATA_BUFFER), c_uint]
    cyi2cread.restype = c_uint
 
    rStatus = cyopen(cyDeviceNum, cyInterfaceNum, byref(handle))
    if rStatus:
        print "CY_I2C_READ: Open failed \n"
        return False

    rbuffer[0] = regaddr
    dataConfigBuffer = CY_DATA_BUFFER(rbuffer, 1, 1)
    i2cDataConfig = CY_I2C_DATA_CONFIG(slaveaddr, False, False)

    rStatus = cyi2cwrite(handle, byref(i2cDataConfig), byref(dataConfigBuffer), 5000)
    if rStatus:
        print "Error in doing i2c subaddr write ... \n"
        cyclose(handle)
        return False

    dataConfigBuffer = CY_DATA_BUFFER(rbuffer, length, length)
    i2cDataConfig = CY_I2C_DATA_CONFIG(slaveaddr, True, True)

    rStatus = cyi2cread(handle, byref(i2cDataConfig), byref(dataConfigBuffer), 5000)
    if rStatus:
        print "Error in doing i2c read ... \n"
        cyclose(handle)
        return False

    #for ubyte in rbuffer[0:8]:
        #print hex(ubyte)

    rData[:length] = rbuffer[:]

    cyclose(handle)
    return True

def i2cWriteData(slaveaddr, regaddr, wdata):
    global cyusb, cyDeviceNum, cyInterfaceNum

    length = len(wdata)
    
    handle = c_void_p()
    array_type  = c_ubyte * (length + 1)
    wbuffer = array_type()

    cyopen = cyusb.CyOpen
    cyopen.argtypes = [c_uint, c_uint]
    cyopen.restype = c_uint

    cyclose = cyusb.CyClose
    cyclose.argtypes = [c_void_p]
    cyclose.restype = c_uint

    cyi2cwrite = cyusb.CyI2cWrite
    cyi2cwrite.argtypes = [c_void_p, POINTER(CY_I2C_DATA_CONFIG), POINTER(CY_DATA_BUFFER), c_uint]
    cyi2cwrite.restype = c_uint
 

    rStatus = cyopen(cyDeviceNum, cyInterfaceNum, byref(handle))
    if rStatus:
        print "CY_I2C_WRITE: Open failed \n"
        return False
    
    wbuffer[0] = regaddr
    wbuffer[1:] = wdata[:]
    
    dataConfigBuffer = CY_DATA_BUFFER(wbuffer, length + 1, length + 1)
    i2cDataConfig = CY_I2C_DATA_CONFIG(slaveaddr, True, False)
    
    rStatus = cyi2cwrite(handle, byref(i2cDataConfig), byref(dataConfigBuffer), 5000)
    if rStatus:
        print "Error in doing i2c write \n"
        return False

    cyclose(handle)
    return True

def projOnOff(projectEnable):
    global cyusb, cyDeviceNum, cyInterfaceNum

    handle = c_void_p()
    
    cyopen = cyusb.CyOpen
    cyopen.argtypes = [c_uint, c_uint]
    cyopen.restype = c_uint

    cyclose = cyusb.CyClose
    cyclose.argtypes = [c_void_p]
    cyclose.restype = c_uint

    cysetgpio = cyusb.CySetGpioValue
    cysetgpio.argtypes = [c_void_p, c_ubyte, c_ubyte]
    cysetgpio.restype = c_uint
    
    rStatus = cyopen(cyDeviceNum, cyInterfaceNum, byref(handle))
    if rStatus:
        print "CY_PROJ_ONOFF: Error in open device ..."
        return False
    
    if projectEnable:
        rStatus = cysetgpio(handle, 2, 1)
        print "on"
    else:
        rStatus = cysetgpio(handle, 2, 0)
        print "off"

    if rStatus:
        print "CY_PROJ_ONOFF: Erroring in doing project on ..."
        cyclose()
        return False
    
    cyclose(handle)
    return True
    
#global cyusb
initCyDevice()
projOnOff(False)
#rData = []
#wdata = [0x00,0x00,0x95,0x02,0x33,0x00]
#i2cWriteData(0x1B, 0x54, 6, wdata)
#if i2cReadData(0x1B,0x53,1, rData):
    #print rData[0]
