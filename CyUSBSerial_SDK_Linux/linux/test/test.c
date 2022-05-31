#include <stdio.h>
#include <unistd.h>
#include <getopt.h>
#include <stdlib.h>
#include <signal.h>

#include <stdbool.h>
#include <unistd.h>
#include <sys/time.h>
#include <pthread.h>
#include <ctype.h>

#include "../../common/header/CyUSBSerial.h"
#define CY_MAX_DEVICES 30
#define CY_MAX_INTERFACES 4

typedef struct _CY_DEVICE_STRUCT {
	int deviceNumber;
	int interfaceFunctionality[CY_MAX_INTERFACES];
	bool isI2c;
	bool isSpi;
	int numInterface; 
}CY_DEVICE_STRUCT;

CY_DEVICE_STRUCT *glDevice;
int i2cDeviceIndex[CY_MAX_DEVICES][CY_MAX_INTERFACES];
unsigned char *deviceNumber = NULL;
int cyDevices, i2cDevices = 0, numDevices = 0;
int cyDeviceNum , cyInterfaceNum ;

bool isCypressDevice (int deviceNum) {
	 CY_HANDLE handle;
	 unsigned char interfaceNum = 0;
	 unsigned char sig[6];
	 CY_RETURN_STATUS rStatus;
	 printf("handle is %d \n", handle);
	 rStatus = CyOpen (deviceNum, interfaceNum, &handle);
	 printf("handle is %d \n", handle);
	 printf("handle is %d \n", &handle);
	 if (rStatus == CY_SUCCESS){
		 rStatus = CyGetSignature (handle, sig);
		 if (rStatus == CY_SUCCESS){
			CyClose (handle);
			return true;
		 }
		 else {
			 CyClose (handle);
			 return false;
		 }
	 }
	 else 
		 return false;
}

void findDeviceNum()
{
	int i, j, devNum;
	int index = 0, numInterfaces, interfaceNum;

	CY_DEVICE_INFO deviceInfo;
	CY_RETURN_STATUS rStatus;
	CY_DEVICE_CLASS deviceClass[CY_MAX_INTERFACES];
	CY_DEVICE_TYPE  deviceType[CY_MAX_INTERFACES];

	glDevice = (CY_DEVICE_STRUCT *)malloc(CY_MAX_DEVICES *sizeof(CY_DEVICE_STRUCT));
	if(glDevice == NULL)
	{
		printf("Memory allocation failed .... \n");
		return -1;
	}

	CyGetListofDevices(&numDevices);
	printf("num devices %d \n", numDevices);

	for(i=0; i<numDevices; i++)
	{
		for(j=0; j<CY_MAX_INTERFACES; j++)
		{
			glDevice[i].interfaceFunctionality[j] = -1;
		}
	}
	for(devNum = 0; devNum < numDevices; devNum ++)
	{	
		rStatus = CyGetDeviceInfo(devNum, &deviceInfo);
		interfaceNum = 0;
		if(!rStatus)
		{
			if(!isCypressDevice(devNum))
			{
				continue;
			}
			numInterfaces = deviceInfo.numInterfaces;
			glDevice[index].numInterface = numInterfaces;
			printf("num interface: %d \n", numInterfaces);

			while(numInterfaces)
			{
				if(deviceInfo.deviceClass[interfaceNum] == CY_CLASS_VENDOR)
				{	
					glDevice[index].deviceNumber = devNum;
					switch(deviceInfo.deviceType[interfaceNum])
					{
						case CY_TYPE_I2C:
							//glDevice[index].interfaceFunctionality[interfaceNum] = CY_TYPE_I2C;
							//glDevice[index].isI2c = true;
							cyDeviceNum = glDevice[index].deviceNumber;
							cyInterfaceNum = interfaceNum;
							break;
						default:
							break;
					}
				}
				interfaceNum ++;
				numInterfaces --;
			}
			index ++;
		}
	}
	printf("cyDeviceNum %d, cyInterfaceNum %d \n", cyDeviceNum, cyInterfaceNum);
}


/*
void deviceHotPlug()
{	    
	CY_RETURN_STATUS rStatus;
	//deviceAddedRemoved = true;
	selectedDeviceNum = -1;
	selectedInterfaceNum = -1;
	printf ("Device of interest Removed/Added \n");
	rStatus = CyGetListofDevices (&numDevices);
	if (rStatus != CY_SUCCESS) {
		printf ("CY:Error in Getting List of Devices: Error NO:<%d> \n", rStatus);
		return rStatus;
	}
	printListOfDevices (false);
}
*/

int i2cReadData(unsigned char slaveaddr, unsigned char regaddr, int length)
{
	CY_DATA_BUFFER	dataBufferRead;
	CY_HANDLE handle;
	CY_RETURN_STATUS rStatus;
	CY_I2C_DATA_CONFIG i2cDataConfig;
	CY_I2C_CONFIG cyI2CConfig;

	unsigned char rbuffer[66];

	memset(rbuffer, 0, 66);

	rStatus = CyOpen(cyDeviceNum, cyInterfaceNum, &handle);
	if(rStatus != CY_SUCCESS){
		printf("CY_I2C: Open failed \n");
		return rStatus;
	}
	
	/*
	rStatus = CyGetI2cConfig(handle, &cyI2CConfig);
	if(rStatus != CY_SUCCESS)
	{
		printf("get fail config \n");
		return -1;
	}
	printf("I2C Frequency:%d, Slave address:%d, isMaster:%d \n",
			cyI2CConfig.frequency, 
			cyI2CConfig.slaveAddress,
			cyI2CConfig.isMaster);	
	*/
	
	rbuffer[0] = regaddr;
	//rbuffer[1] = 0;

	i2cDataConfig.slaveAddress = slaveaddr;
	//i2cDataConfig.isStopBit = false;
	dataBufferRead.length = 1;
	dataBufferRead.buffer = rbuffer;
	rStatus = CyI2cWrite(handle, &i2cDataConfig, &dataBufferRead, 5000);
	if(rStatus != CY_SUCCESS)
	{
		printf("Error in doing i2c write ... Error is %d \n", rStatus);
		CyClose(handle);
		return -1;
	}

	memset(rbuffer, 0, 66);

	dataBufferRead.buffer = rbuffer;	
	i2cDataConfig.isStopBit = true;
	i2cDataConfig.isNakBit = true;
	//i2cDataConfig.slaveAddress = slaveaddr;
	dataBufferRead.length = length;
	dataBufferRead.buffer = rbuffer;

	rStatus = CyI2cRead(handle, &i2cDataConfig, &dataBufferRead, 5000);
	if(rStatus != CY_SUCCESS){
		printf("Error in doing i2c read ... Error is %d \n", rStatus);
		CyClose(handle);
		return -1;
	}

	printf("transfercount is %d  \n", dataBufferRead.transferCount);

	printf("\n Data that is read from i2c ... \n");
	printf("\n---------------------------------------------------\n");
	for(rStatus = 0; rStatus < length ; rStatus++)
	{
		printf("%x ", rbuffer[rStatus]);
	}
	printf("\n----------------------------------------------------\n");

	printf("Data read finish ... \n");

	CyClose(handle);
}

int i2cWriteData(unsigned char slaveaddr, unsigned char regaddr, int length, unsigned char *wdata)
{
	CY_DATA_BUFFER	dataBufferWrite;
	CY_HANDLE handle;
	CY_RETURN_STATUS rStatus;
	CY_I2C_DATA_CONFIG i2cDataConfig;
	CY_I2C_CONFIG cyI2CConfig;

	unsigned char wbuffer[33];

	memset(wbuffer, 0, 33);

	rStatus = CyOpen(cyDeviceNum, cyInterfaceNum, &handle);
	if(rStatus != CY_SUCCESS){
		printf("CY_I2C: Open failed \n");
		return rStatus;
	}
	
	wbuffer[0] = regaddr;
	//wbuffer[1] = wdata;
	memcpy(wbuffer + 1, wdata, length);
		
	i2cDataConfig.isStopBit = true;
	i2cDataConfig.slaveAddress = slaveaddr;

	dataBufferWrite.buffer = wbuffer;
	dataBufferWrite.length = length + 1;

	rStatus = CyI2cWrite(handle, &i2cDataConfig, &dataBufferWrite, 5000);
	if(rStatus != CY_SUCCESS)
	{
		printf("Error in doing i2c write \n");
	}
	
	printf("\n Data that is write from i2c ... \n");
	printf("\n---------------------------------------------------\n");
	for(rStatus = 1; rStatus < length + 1; rStatus++)
	{
		printf("%x ", wbuffer[rStatus]);
	}
	printf("\n----------------------------------------------------\n");

	printf("Data write finish ... \n");


	CyClose(handle);
}

/*
void init()
{
	CY_RETURN_STATUS rStatus;

	rStatus = CyLibraryInit();
	if(rStatus != CY_SUCCESS)
	{
		printf("CY:Error in doing library init Error NO:<%d> \n", rStatus);
		return rStatus;
	}
}
*/

int main (int argc, char **agrv)
{
	CY_RETURN_STATUS rStatus;
	//signal (SIGUSR1, deviceHotPlug);

    rStatus = CyLibraryInit ();
	if (rStatus != CY_SUCCESS) {
		printf ("CY:Error in Doing library init Error NO:<%d> \n", rStatus);
		return rStatus;
	}
	
	unsigned char data[6];

	memset(data, 0, 6);
	
	data[2] = 0x95;
	data[3] = 0x02;
	
	findDeviceNum();
	//i2cWriteData(0x1B,0x54, 6, data);	
	i2cReadData(0x48,0x1,8);
}


