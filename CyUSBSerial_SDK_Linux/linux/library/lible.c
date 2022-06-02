#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <getopt.h>
#include <string.h>
#include <signal.h>

#include <stdbool.h>
#include <unistd.h>
#include <sys/time.h>
#include <pthread.h>
#include <ctype.h>
#include "CyUSBSerial.h"

#include "yo_spi.h"

#define CY_MAX_DEVICES 30
#define CY_MAX_INTERFACES 4
#define I2C_IF_NUM 0
#define SPI_IF_NUM 1
#define GPIO_IF_NUM 2

typedef struct _CY_DEVICE_STRUCT {
    int deviceNumber;
    int interfaceFunctionality[CY_MAX_INTERFACES];
    bool isI2c;
    bool isSpi;
    bool isGpio;
    int numInterface; 
}CY_DEVICE_STRUCT;

CY_DEVICE_STRUCT *glDevice;

struct data_stream {
	unsigned commandop : 8;
	unsigned col_start_index : 5;
	unsigned col_end_index : 5;
	unsigned row_start_index : 11;
	unsigned rdummy : 7;             //all 0
	unsigned datacheck : 4;          //all 1
	unsigned dummy : 8;              // 1000 0000
};

static spi* spi_dev0;
static int SPIWriteData(int data_len, char* data);

int DEVICE0_NUM;
int DEVICE1_NUM;
int i2cDeviceIndex[CY_MAX_DEVICES][CY_MAX_INTERFACES];
unsigned char *deviceNumber = NULL;
unsigned char numDevices = 0;
int cyDevices, i2cDevices = 0;
int selectedDeviceNum = -1, selectedInterfaceNum = -1;
bool exitApp = false;
unsigned short pageAddress = -1;
short readWriteLength = -1;
bool deviceAddedRemoved = false;
static int isNewLED = 0;



bool isCypressDevice (int deviceNum) {
    CY_HANDLE handle;
    unsigned char interfaceNum = 0;
    unsigned char sig[6];
    CY_RETURN_STATUS rStatus;
    rStatus = CyOpen (deviceNum, interfaceNum, &handle);
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

bool ResetCypressDevice (int deviceNum, int interfaceNum) {
    CY_HANDLE handle;
    unsigned char sig[6];
    CY_RETURN_STATUS rStatus;
    rStatus = CyOpen (deviceNum, interfaceNum, &handle);
    if (rStatus == CY_SUCCESS){
        rStatus = CyGetSignature (handle, sig);
        if (rStatus == CY_SUCCESS){
	    	CyResetDevice(handle);
 		printf ("CY:Reset Devices Number:<%d> \n", deviceNum);
	    	CyClose (handle);
			return 0;
        }
		else {
		    //printf ("CY:Failed to reset Devices Number:<%d> \n", deviceNum);
            CyClose (handle);
            return -1;
        }
    }
    else
        return -1;
}

void printListOfDevices (bool isPrint)
{
    int  index_i = 0, index_j = 0, i, j, countOfDevice = 0, devNum;
    int length, index = 0, numInterfaces, interfaceNum;
    bool set1 = false;

    unsigned char deviceID[CY_MAX_DEVICES];
    unsigned char functionality[64];
    CY_DEVICE_INFO deviceInfo;
    CY_DEVICE_CLASS deviceClass[CY_MAX_INTERFACES];
    CY_DEVICE_TYPE  deviceType[CY_MAX_INTERFACES];
    CY_RETURN_STATUS rStatus;

    deviceAddedRemoved = false; 
    CyGetListofDevices (&numDevices);
    //printf ("The number of devices is %d \n", numDevices); 
    for (i = 0; i < numDevices; i++){
        for (j = 0; j< CY_MAX_INTERFACES; j++)
            glDevice[i].interfaceFunctionality[j] = -1;
    }
    if (isPrint){
        printf ("\n\n---------------------------------------------------------------------------------\n");
        printf ("Device Number | VID | PID | INTERFACE NUMBER | FUNCTIONALITY \n");
        printf ("---------------------------------------------------------------------------------\n");
    }
    cyDevices = 0;
    for (devNum = 0; devNum < numDevices; devNum++){
        rStatus = CyGetDeviceInfo (devNum, &deviceInfo);
        interfaceNum = 0;
        if (!rStatus)
        {
            if (!isCypressDevice (devNum)){
                continue;
            }
            strcpy (functionality, "NA");
            numInterfaces = deviceInfo.numInterfaces;
            glDevice[index].numInterface = numInterfaces;
            cyDevices++;
            
            while (numInterfaces){
                if (deviceInfo.deviceClass[interfaceNum] == CY_CLASS_VENDOR)
                {
                    glDevice[index].deviceNumber = devNum;
                    switch (deviceInfo.deviceType[interfaceNum]){
                        case CY_TYPE_I2C:
                            glDevice[index].interfaceFunctionality[interfaceNum] = CY_TYPE_I2C;
                            strcpy (functionality, "VENDOR_I2C");
                            glDevice[index].isI2c = true;
                            break;
                        case CY_TYPE_SPI:
                            glDevice[index].interfaceFunctionality[interfaceNum] = CY_TYPE_SPI;
                            strcpy (functionality, "VENDOR_SPI");
                            glDevice[index].isSpi = true;
                            break;
                        case CY_TYPE_MFG:
							glDevice[index].interfaceFunctionality[interfaceNum] = CY_TYPE_MFG;
							strcpy (functionality, "VENDOR_GPIO");
							glDevice[index].isGpio = true;
							break;
                        default:
                            strcpy (functionality, "NA");
                            break;    
                    }
                }
                else if (deviceInfo.deviceClass[interfaceNum] == CY_CLASS_CDC){
                    strcpy (functionality, "NA");
                }
                if (isPrint) {
                	printf ("%d             |%x  |%x    | %d     | %s\n", \
                			devNum, \
							deviceInfo.vidPid.vid, \
							deviceInfo.vidPid.pid,  \
							interfaceNum, \
							functionality \
							);
                }
                interfaceNum++;
                numInterfaces--;
            }
            index++;
        }
    }
    if (isPrint){
        printf ("---------------------------------------------------------------------------------\n\n");
    }
}

//#define DEBUG
#ifdef DEBUG
#  define D(x) x
#else
#  define D(x)
#endif

enum CommandId {
	WRITE_LED_ENABLE = 0x52,
	READ_LED_ENABLE = 0x53,
	WRITE_LED_CURRENT = 0x54,
	READ_LED_CURRENT = 0x55,
	READ_TEMPERATRUE = 0xd6,
	WRITE_TEST_PATTERNS = 0x0b,
	WRITE_PROJCETOR_FLIP = 0x14,
	READ_PROJCETOR_FLIP = 0x15,
	READ_FB_VER = 0xd9,
	WRITE_PWR = 0xa0,
	READ_LIGHT = 0xac,
	WRITE_FPGA_CONTROL = 0xCA,
	WRITE_ACTIVE_BUFFER = 0xC5,
	WRITE_INPUT_SOURCE = 0x05,
	WRITE_EXTERNAL_PRINT_CONFIGURATION = 0xA8,
	WRITE_PARALLEL_VIDEO = 0xC3,
	WRITE_EXTERNAL_PRINT_CONTROL = 0xC1,
};

#define cSlaveAddress7bit 0x1B
#define cReadSlaveAddress "37"
#define cWriteSlaveAddress "36"
#define aSlaveAddress7bitOLD 0x39
#define aSlaveAddress7bitNEW 0x29
#define aReadSlaveAddress "73"
#define aWriteSlaveAddress "72"

static UINT8 aSlaveAddress7bit = aSlaveAddress7bitNEW;
static UINT8 lightSensorPowerOnCommand = 0xA0;
static UINT8 lightSensorPowerOnData = 0x03;
//static UINT8 lightSensorReadSensorValueCommand = 0xAC;
static UINT8 lightSensorReadSensorValueCommand = 0xB4;
static UINT8 lightSensorPowerOffData = 0x00;

CY_RETURN_STATUS FlashBlockRead(int deviceNumber, int interfaceNum, int address, int len, char *buf);

//SPi Flash functions
enum Flash_CommandCode
{
	WRITE_ENABLE = 0x06,
	WRITE_DISABLE = 0x04,
	READ_STATUS1 = 0x05,
	READ_STATUS2 = 0x35,
	WRITE_STATUS = 0x01,
	PAGE_PROGRAM = 0x02,
	READ_DATA = 0x03,
	SECTOR_ERASE = 0x20,
	BLOCK_ERASE_64KB = 0xd8
};

// Define VID & PID
// These numbers depends on individual products
#define VID 0x04B4
#define PID 0x000A

//Variable to store cyHandle of the selected device
CY_HANDLE cyHandle;

//Variables used by application
unsigned char deviceID[16];

/*
Function Name: CY_RETURN_STATUS cySPIWaitForIdle (CY_HANDLE cyHandle)
Purpose: Function to check for SPI status

Arguments:
cyHandle - cyHandle of the device
Retrun Code: returns falure code of USB-Serial API

*/

CY_RETURN_STATUS cySPIWaitForIdle(CY_HANDLE cyHandle)
{
	char rd_data[2], wr_data[2];
	CY_DATA_BUFFER writeBuf, readBuf;
	int timeout = 0xFFFF;
	CY_RETURN_STATUS status;

	D(printf("\nSending SPI Status query command to device..."));
	writeBuf.length = 2;
	writeBuf.buffer = (unsigned char *)wr_data;

	readBuf.length = 2;
	readBuf.buffer = (unsigned char *)rd_data;

	// Loop here till read data indicates SPI status is not idle
	// Condition to be checked: rd_data[1] & 0x01

	do
	{
		wr_data[0] = READ_STATUS1; /* Get SPI status */
		status = CySpiReadWrite(cyHandle, &readBuf, &writeBuf, 5000);

		if (status != CY_SUCCESS)
		{
			D(printf("\nFailed to send SPI status query command to device."));
			break;
		}
		timeout--;
		if (timeout == 0)
		{
			D(printf("\nMaximum retries completed while checking SPI status, returning with error code."));
			status = CY_ERROR_IO_TIMEOUT;
			return status;
		}

	} while (rd_data[1] & 0x03); //Check SPI Status

	D(printf("\nSPI is now in idle state and ready for receiving additional data commands."));
	return status;
}

CY_RETURN_STATUS FlashBlockRead(int deviceNumber, int interfaceNum, int address, int len, char *buf)
{
	int BlockSize = 0x1000; //Block read 4KB size
	unsigned char wbuffer[0x1004], rbuffer[0x1004];  //array size is equal to BlockSize+4

	CY_DATA_BUFFER cyDatabufferWrite, cyDatabufferRead;
	CY_RETURN_STATUS rStatus;
	int cWriteSize, cReadSize;
	int str_addr = address;


	D(printf("Opening SPI device with device number %d...\n", deviceNumber));

	rStatus = CyOpen(deviceNumber, interfaceNum, &cyHandle);

	if (rStatus != CY_SUCCESS){
		D(printf("SPI Device open failed.\n"));
		return rStatus;
	}

	D(printf("SPI Open successfull ...\n"));

	//D(printf("Performing Flash Read operation..."));
	while (len > 0)
	{
		D(printf("Read data from start address :0x%X \n", address));
		wbuffer[0] = READ_DATA;
		wbuffer[1] = (address >> 16 & 0xff);
		wbuffer[2] = (address >> 8 & 0xff);
		wbuffer[3] = (address & 0xff);

		cWriteSize = 4;
		if (len > BlockSize)
			cReadSize = BlockSize;
		else
			cReadSize = len;

		//SPI uses a single CySpiReadWrite to perform both read and write
		//and flush operations.
		cyDatabufferWrite.buffer = wbuffer;
		cyDatabufferWrite.length = 4 + cReadSize; //4 bytes command + 256 bytes page size

		cyDatabufferRead.buffer = rbuffer;
		cyDatabufferRead.length = 4 + cReadSize;
		// As per the EEPROM datasheet we need to perform simeltanious read and write
		// to do read/write operation on EEPROM.
		// In this case cyDatabufferRead contains data pushed out by EEPROM and not real data.
		rStatus = CySpiReadWrite(cyHandle, &cyDatabufferRead, &cyDatabufferWrite, 5000);
		if (rStatus != CY_SUCCESS){

			D(printf("Error in doing SPI data write :0x%X \n", cyDatabufferWrite.transferCount));
			CyClose(cyHandle);
			return rStatus;
		}

		int i;
		for (i = 0; i < cReadSize; i++)
			buf[address - str_addr + i] = rbuffer[cWriteSize + i];

		//D(printf("Wait for EEPROM active state..."));
		rStatus = cySPIWaitForIdle(cyHandle);
		if (rStatus){
			D(printf("Error in Waiting for Flash active state:0x%X \n", rStatus));
			CyClose(cyHandle);
			return rStatus;
		}

		address += BlockSize;
		if (len > BlockSize)
			len -= BlockSize;
		else
			len = 0;
	}

	D(printf("Closeing SPI device...\n"));
	CyClose(cyHandle);
	D(printf("Flash Read Done ..."));
	return CY_SUCCESS;
}

CY_RETURN_STATUS I2CWrite(int deviceNumber, int interfaceNum, UINT8 address, int len, UINT8 *buf)
{
	CY_DATA_BUFFER cyDatabuffer;
	CY_I2C_DATA_CONFIG cyI2CDataConfig;

	CY_RETURN_STATUS rStatus;

	printf("Opening %x I2C device with device number %d...\n", address, deviceNumber);

	//Open the device at deviceNumber
	rStatus = CyOpen(deviceNumber, interfaceNum, &cyHandle);

	if (rStatus != CY_SUCCESS){
		printf("I2C Device open failed...\n");
		return rStatus;
	}

	// I2C Read/Write operations
	printf("Performing %x I2C Write operation...\n", address);

	//Initialize the CY_I2C_DATA_CONFIG variable
	cyI2CDataConfig.slaveAddress = address;
	cyI2CDataConfig.isStopBit = true;
	//Initialize the CY_DATA_BUFFER variable
	cyDatabuffer.buffer = buf;
	cyDatabuffer.length = len;

	rStatus = CyI2cWrite(cyHandle, &cyI2CDataConfig, &cyDatabuffer, 5000);
	if (rStatus != CY_SUCCESS){
		printf("CyI2cWrite %x Failed ...retrying %d \n", address, rStatus);
		CyClose (cyHandle);
		return rStatus;
	}

	printf("Completed %x I2C write transfer with %d bytes.\n", address, len);
	printf("End %x status is %d.\n", address, rStatus);
	CyClose (cyHandle);
	return rStatus;
}

CY_RETURN_STATUS I2CRead(int deviceNumber, int interfaceNum, UINT8 address, int len, UINT8 *buf)
{
	CY_DATA_BUFFER cyDatabuffer;
	CY_I2C_DATA_CONFIG cyI2CDataConfig;

	CY_RETURN_STATUS rStatus;

	D(printf("Opening I2C device with device number %d...\n", deviceNumber));

	//Open the device at deviceNumber
	rStatus = CyOpen(deviceNumber, interfaceNum, &cyHandle);

	if (rStatus != CY_SUCCESS){
		D(printf("I2C Device open failed...\n"));
		return rStatus;
	}


	// I2C Read/Write operations
	D(printf("Performing I2C Read operation...\n"));

	//Initialize the CY_I2C_DATA_CONFIG variable
	cyI2CDataConfig.slaveAddress = address;
	cyI2CDataConfig.isStopBit = true;
	cyI2CDataConfig.isNakBit = true;
	//Initialize the CY_DATA_BUFFER variable
	cyDatabuffer.buffer = buf;
	cyDatabuffer.length = len;


	rStatus = CyI2cRead(cyHandle, &cyI2CDataConfig, &cyDatabuffer, 5000);
	if (rStatus != CY_SUCCESS){
		D(printf("I2C Device Read failed...\n"));
		CyClose (cyHandle);
		return rStatus;
	}
	D(printf("Completed I2C read successfully. Read %d bytes of data.\n", len));

	CyClose (cyHandle);
	return rStatus;
}

CY_RETURN_STATUS GpioWrite(int deviceNumber, int interfaceNum, UINT8 gpioNumber, UINT8 value)
{
	CY_RETURN_STATUS rStatus;

	D(printf("Opening GPIO device with device number %d...\n", deviceNumber));

	//Open the device at deviceNumber
	rStatus = CyOpen(deviceNumber, interfaceNum, &cyHandle);

	if (rStatus != CY_SUCCESS){
		D(printf("I2C Device open failed...\n"));
		return rStatus;
	}

	// I2C Read/Write operations
	D(printf("Performing GPIO Write operation...\n"));

	if (value > 0)
		value = 1;
	else
		value = 0;
	rStatus = CySetGpioValue(cyHandle, gpioNumber, value);
	if (rStatus != CY_SUCCESS){
		D(printf("GpioWrite Failed ...retrying %d \n", rStatus));
		CyClose (cyHandle);
		return rStatus;
	}

	D(printf("Completed GPIO write !\n"));
	CyClose (cyHandle);
	return CY_SUCCESS;
}

CY_RETURN_STATUS GpioRead(int deviceNumber, int interfaceNum, UINT8 gpioNumber, UINT8* value)
{
	CY_RETURN_STATUS rStatus;

	D(printf("Opening GPIO device with device number %d...\n", deviceNumber));

	//Open the device at deviceNumber
	rStatus = CyOpen(deviceNumber, interfaceNum, &cyHandle);

	if (rStatus != CY_SUCCESS) {
		printf("GPIO Device open failed. Error NO:<%d>\n", rStatus);
		return rStatus;
	}


	// I2C Read/Write operations
	D(printf("Performing GPIO Read operation...\n"));

	rStatus = CyGetGpioValue(cyHandle, gpioNumber, value);
	if (rStatus != CY_SUCCESS) {
		printf("CyGetGpioValue Failed. Error NO:<%d>\n", rStatus);
		CyClose(cyHandle);
		return rStatus;
	}

	D(printf("Completed GPIO read !\n"));
	CyClose(cyHandle);
	return CY_SUCCESS;
}

int SetProjectorOnOff(int deviceNumber, int interfaceNum, int PorjectorEnable) {
	int status;
	UINT8 GpioNum = 7;
	status = GpioWrite(deviceNumber, interfaceNum, GpioNum, PorjectorEnable);
	if (status != CY_SUCCESS)
	{
		D(printf("\nFailed to write Projector On/Off.\n"));
		return -1;
	}
	return 0;
}

int SetInputSource(int deviceNumber, int interfaceNum, UINT8 Select) {
	int status;
	int cWriteSize = 2;
	UINT8 * sendBuf = NULL;
	sendBuf = (UINT8 *)malloc(cWriteSize);

	D(printf("Select input source \n"));

	sendBuf[0] = WRITE_INPUT_SOURCE;
	sendBuf[1] = Select;

	status = I2CWrite(deviceNumber, interfaceNum, cSlaveAddress7bit, cWriteSize, sendBuf);
	if (status != CY_SUCCESS)
	{
		D(printf("\nFailed to select input source."));
		free(sendBuf);
		return -1;
	}

	free(sendBuf);
	return 0;
}

int SetTestPattern(int deviceNumber, int interfaceNum, UINT8 PatternSel) {
	int status;
	int cWriteSize = 7;
	UINT8 * sendBuf = NULL;
	sendBuf = (UINT8 *)malloc(cWriteSize);

	D(printf("Select input source \n"));

	sendBuf[0] = WRITE_TEST_PATTERNS;
	sendBuf[1] = PatternSel;
	if ((PatternSel & 0x7F) == 0x01) //Fixed Step Horizontal Ramp
	{
		sendBuf[2] = 0x70;
		sendBuf[3] = 0x00;
		sendBuf[4] = 0xff;
		sendBuf[5] = 0x00;
		sendBuf[6] = 0x00;
	}
	else if ((PatternSel & 0x7F) == 0x07) //Checkerboard
	{
		sendBuf[2] = 0x70;
		sendBuf[3] = 0x04;
		sendBuf[4] = 0x00;
		sendBuf[5] = 0x04;
		sendBuf[6] = 0x00;
	}
	else
	{
		sendBuf[2] = 0x00;
		sendBuf[3] = 0x00;
		sendBuf[4] = 0x00;
		sendBuf[5] = 0x00;
		sendBuf[6] = 0x00;
	}
	status = I2CWrite(deviceNumber, interfaceNum, cSlaveAddress7bit, cWriteSize, sendBuf);
	if (status != CY_SUCCESS)
	{
		D(printf("\nFailed to select input source."));
		free(sendBuf);
		return -1;
	}

	free(sendBuf);
	return 0;
}

int SetLedOnOff(int deviceNumber, int interfaceNum, int LedEnableRed, int LedEnableGreen, int LedEnableBlue) {
	int status;
	UINT8 enableByte = 0;

	if (LedEnableRed > 0)
	{
		enableByte |= 0x01;
	}

	if (LedEnableGreen > 0)
	{
		enableByte |= 0x02;
	}

	if (LedEnableBlue > 0)
	{
		enableByte |= 0x04;
	}

	int cWriteSize = 2;
	UINT8 * sendBuf = NULL;
	sendBuf = (UINT8 *)malloc(cWriteSize);

	D(printf("Write LED current \n"));

	sendBuf[0] = WRITE_LED_ENABLE;
	sendBuf[1] = enableByte;

	status = I2CWrite(deviceNumber, interfaceNum, cSlaveAddress7bit, cWriteSize, sendBuf);
	if (status != CY_SUCCESS)
	{
		D(printf("\nFailed to write LED On/Off."));
		free(sendBuf);
		return -1;
	}

	free(sendBuf);
	return 0;

}

int GetLedOnOff(int deviceNumber, int interfaceNum, int *LedEnableRed, int *LedEnableGreen, int *LedEnableBlue) {
	int status;
	const int cWriteSize = 1;
	const int cReadSize = 1;
	UINT8 * sendBuf = NULL;
	sendBuf = (UINT8 *)malloc(cWriteSize);
	UINT8 * recvBuf = NULL;
	recvBuf = (UINT8 *)malloc(cReadSize);

	sendBuf[0] = READ_LED_ENABLE;
	status = I2CWrite(deviceNumber, interfaceNum, cSlaveAddress7bit, cWriteSize, sendBuf);
	if (status != CY_SUCCESS)
	{
		D(printf("\nFailed to get LED On/Off."));
		free(sendBuf);
		free(recvBuf);
		return -1;
	}

	status = I2CRead(deviceNumber, interfaceNum, cSlaveAddress7bit, cReadSize, recvBuf);
	if (status != CY_SUCCESS)
	{
		D(printf("\nFailed to get LED On/Off."));
		free(sendBuf);
		free(recvBuf);
		return -1;
	}

	if ((recvBuf[0] & 0x01) == 0x01){
		*LedEnableRed = 1;
	}
	else{
		*LedEnableRed = 0;
	}

	if ((recvBuf[0] & 0x02) == 0x02){
		*LedEnableGreen = 1;
	}
	else{
		*LedEnableGreen = 0;
	}

	if ((recvBuf[0] & 0x04) == 0x04){
		*LedEnableBlue = 1;
	}
	else{
		*LedEnableBlue = 0;
	}
	
	free(sendBuf);
	free(recvBuf);
	return 0;
}

int SetLedCurrent(int deviceNumber, int interfaceNum, int currentRed, int currentGreen, int currentBlue) {
	int status;
	int cWriteSize = 7;
	UINT8 * sendBuf = NULL;
	sendBuf = (UINT8 *)malloc(cWriteSize);

	D(printf("Write LED current \n"));

	sendBuf[0] = WRITE_LED_CURRENT;
	sendBuf[1] = currentRed & 0xff;
	sendBuf[2] = (currentRed >> 8) & 0xff;
	sendBuf[3] = currentGreen & 0xff;
	sendBuf[4] = (currentGreen >> 8) & 0xff;
	sendBuf[5] = currentBlue & 0xff;
	sendBuf[6] = (currentBlue >> 8) & 0xff;

	status = I2CWrite(deviceNumber, interfaceNum, cSlaveAddress7bit, cWriteSize, sendBuf);
	if (status != CY_SUCCESS)
	{
		D(printf("\nFailed to write LED current."));
		free(sendBuf);
		return -1;
	}

	free(sendBuf);
	return 0;

}

int GetLedCurrent(int deviceNumber, int interfaceNum, int *currentRed, int *currentGreen, int *currentBlue) {
	int status;
	const int cWriteSize = 1;
	const int cReadSize = 6;
	UINT8 * sendBuf = NULL;
	sendBuf = (UINT8 *)malloc(cWriteSize);
	UINT8 * recvBuf = NULL;
	recvBuf = (UINT8 *)malloc(cReadSize);

	sendBuf[0] = READ_LED_CURRENT;
	status = I2CWrite(deviceNumber, interfaceNum, cSlaveAddress7bit, cWriteSize, sendBuf);
	if (status != CY_SUCCESS)
	{
		D(printf("\nFailed to get LED current."));
		free(sendBuf);
		free(recvBuf);
		return -1;
	}

	status = I2CRead(deviceNumber, interfaceNum, cSlaveAddress7bit, cReadSize, recvBuf);
	if (status != CY_SUCCESS)
	{
		D(printf("\nFailed to get LED current."));
		free(sendBuf);
		free(recvBuf);
		return -1;
	}

	*currentRed = (recvBuf[1] << 8) | recvBuf[0];
	*currentGreen = (recvBuf[3] << 8) | recvBuf[2];
	*currentBlue = (recvBuf[5] << 8) | recvBuf[4];

	free(sendBuf);
	free(recvBuf);
	return 0;
}

int GetLight(int deviceNumber, int interfaceNum, int *lightValue)
{
	int status;
	const int cWriteSize = 2;
	const int cReadSize = 2;
	UINT8 * sendBuf = NULL;
	sendBuf = (UINT8 *)malloc(cWriteSize);
	UINT8 * sendBuf2 = NULL;
	sendBuf2 = (UINT8 *)malloc(1);
	UINT8 * recvBuf = NULL;
	recvBuf = (UINT8 *)malloc(cReadSize);
	sendBuf[0] = lightSensorPowerOnCommand;
	sendBuf[1] = lightSensorPowerOnData;
	fflush(stdout);
	setvbuf(stdout, NULL, _IONBF, 0);
	freopen("./my.log", "a", stdout); //打印到my.log文件
	printf("\naSlaveAddress7bit is %x\n", aSlaveAddress7bit);
	printf("lightSensorPowerOnCommand is %x\n", lightSensorPowerOnCommand);
	printf("lightSensorPowerOnData is %x\n", lightSensorPowerOnData);
	printf("lightSensorReadSensorValueCommand is %x\n", lightSensorReadSensorValueCommand);
	status = I2CWrite(deviceNumber, interfaceNum, aSlaveAddress7bit, cWriteSize, sendBuf);
	if(status != CY_SUCCESS)
	{
		printf("\nFailed to get LED Light 1. %d\n", status);
		free(sendBuf);
		free(sendBuf2);
		free(recvBuf);
		return -1;
	}
	sleep(1);
	sendBuf2[0] = lightSensorReadSensorValueCommand;
	status = I2CWrite(deviceNumber, interfaceNum, aSlaveAddress7bit, 1, sendBuf2);
	if(status != CY_SUCCESS)
	{
		printf("\nFailed to get LED Light 2. %d\n", status);
		free(sendBuf);
		free(sendBuf2);
		free(recvBuf);
		return -1;
	}
	status = I2CRead(deviceNumber, interfaceNum, aSlaveAddress7bit, cReadSize, recvBuf);
	if (status != CY_SUCCESS)
	{
		printf("\nFailed to get LED Light 3. %d\n", status);
		free(sendBuf);
		free(sendBuf2);
		free(recvBuf);
		return -1;
	}
	*lightValue = recvBuf[1] << 8 | recvBuf[0];
	sendBuf[0] = lightSensorPowerOnCommand;
	sendBuf[1] = lightSensorPowerOffData;
	status = I2CWrite(deviceNumber, interfaceNum, aSlaveAddress7bit, cWriteSize, sendBuf);
	if(status != CY_SUCCESS)
	{
		printf("\nFailed to get LED Light 4. %d\n", status);
		free(sendBuf);
		free(sendBuf2);
		free(recvBuf);
		return -1;
	}
	free(sendBuf);
	free(sendBuf2);
	free(recvBuf);
	printf("success read %d\n", *lightValue);
	return 0;			
}

int GetTemperature(int deviceNumber, int interfaceNum, int *tempValue)
{
	int status;
	int val_r, val_g, val_b;
	int led_r,led_g,led_b;
	double num1=5.8593;
	double num2=4.0;
	double num3=1.6;
	const int cWriteSize = 1;
	const int cReadSize = 2;
	UINT8 * sendBuf = NULL;
	sendBuf = (UINT8 *)malloc(cWriteSize);
	UINT8 * recvBuf = NULL;
	recvBuf = (UINT8 *)malloc(cReadSize);	

	status = GetLedCurrent(deviceNumber, interfaceNum, &val_r, &val_g, &val_b);
	if (status != CY_SUCCESS)
	{
		D(printf("\nFailed to get LED current."));
		free(sendBuf);
		free(recvBuf);
		return -1;
	}
	
	sendBuf[0] = 0xD6;
	status = I2CWrite(deviceNumber, interfaceNum, cSlaveAddress7bit, cWriteSize, sendBuf);
	if (status != CY_SUCCESS)
	{
		D(printf("\nFailed to get LED Temperature."));
		free(sendBuf);
		free(recvBuf);
		return -1;
	}
	status = I2CRead(deviceNumber, interfaceNum, cSlaveAddress7bit, cReadSize, recvBuf);	
	if (status != CY_SUCCESS)
	{
		D(printf("\nFailed to get LED Temperature."));
		free(sendBuf);
		free(recvBuf);
		return -1;
	}
	*tempValue = recvBuf[1] <<8 | recvBuf[0];
	status = GetLedOnOff(deviceNumber,interfaceNum,&led_r,&led_g,&led_b);
	if (status != CY_SUCCESS)
	{
		D(printf("\nFailed to get LED Temperature."));
		free(sendBuf);
		free(recvBuf);
		return -1;
	}
	int value = 0;
	if (isNewLED == 0)
	{
		value += (int)((led_g ? (((num3*num2)*num1)*val_g):0.0)/100.0);
		*tempValue = *tempValue + value;
	}
	else
	{
		double DW = 1.2;
		double DI_CBM25X = 0.0048828;
		double LED_CURRENT_I = DI_CBM25X * (val_b + 1);
		double Vol_CBM25X_405 = 0.0301 * LED_CURRENT_I * LED_CURRENT_I * LED_CURRENT_I - 0.3248 * LED_CURRENT_I * LED_CURRENT_I + 1.5666 * LED_CURRENT_I + 6.1046;
		value += (int)(led_b ? (DW*Vol_CBM25X_405*LED_CURRENT_I):0.0);
		*tempValue = *tempValue / 10 + value;
	}
	return 0;	
}

int spiWriteEnable (CY_HANDLE handle)
{
    unsigned char wr_data,rd_data;
    CY_RETURN_STATUS status = CY_SUCCESS;
    CY_DATA_BUFFER writeBuf;
    CY_DATA_BUFFER readBuf;

    writeBuf.buffer = &wr_data;
    writeBuf.length = 1;

    readBuf.buffer = &rd_data;
    readBuf.length = 1;

    wr_data = 0x06; /* Write enable */
    status = CySpiReadWrite (handle, &readBuf, &writeBuf, 5000);
    if (status != CY_SUCCESS)
    {
        return status;
    }
    return status;
}

//Helper functions for doing data transfer to/from SPI flash
int spiWaitForIdle (CY_HANDLE handle)
{
    char rd_data[2], wr_data[2];
    CY_DATA_BUFFER writeBuf, readBuf;
    writeBuf.length = 2;
    writeBuf.buffer = (unsigned char *)wr_data;
    int timeout = 0xFFFF;
    CY_RETURN_STATUS status;

    readBuf.length = 2;
    readBuf.buffer = (unsigned char *)rd_data;
    do
    {
        wr_data[0] = 0x05; /* Status */
        status = CySpiReadWrite (handle, &readBuf, &writeBuf, 5000);
        if (status != CY_SUCCESS)
        {
            break;
        }
        timeout--;
        if (timeout == 0)
        {
            status = CY_ERROR_IO_TIMEOUT;
            return status;
        }
    } while (rd_data[1] & 0x01);
    return status;
}

int spiVerifyData (int deviceNumber, int interfaceNum)
{
    CY_DATA_BUFFER dataBufferWrite,dataBufferRead;
    CY_HANDLE handle;
    bool isVerify = true;
    unsigned char wbuffer[256 + 4], rbuffer[256 + 4];
    int rStatus, length;

    memset (rbuffer, 0x00, 256);
    memset (wbuffer, 0x00, 256);

    rStatus = CyOpen (deviceNumber, interfaceNum, &handle);
    if (rStatus != CY_SUCCESS){
        D(printf ("CY_SPI: Open failed \n"));
        return rStatus;
    }
    dataBufferWrite.buffer = wbuffer;
    dataBufferRead.buffer = rbuffer;

    rStatus = spiWaitForIdle (handle);
    if (rStatus){
        D(printf("Error in Waiting for EEPOM active state %d \n", rStatus));
        CyClose (handle);
        return CY_ERROR_REQUEST_FAILED;
    }
    D(printf ("Calling spi write enable \n"));
    rStatus = spiWriteEnable (handle);
    if (rStatus){
        D(printf("Error in setting Write Enable %d \n", rStatus));
        CyClose (handle);
        return CY_ERROR_REQUEST_FAILED;
    }
    //Write SPI write command
    wbuffer[0] = 0x02;
    //SPI flash address
    wbuffer[1] = (pageAddress >> 8);
    wbuffer[2] = (pageAddress) & 0x00FF;
    wbuffer[3] = 0;

    D(printf ("The Data written is ...\n"));
    for (rStatus = 4; rStatus < (readWriteLength + 4); rStatus++){
        wbuffer[rStatus] = rand() % 256;
        D(printf ("%x ",wbuffer[rStatus]));
    }

    dataBufferRead.length = (4 + readWriteLength);
    dataBufferWrite.length = (4 + readWriteLength);

    rStatus = CySpiReadWrite (handle , &dataBufferRead, &dataBufferWrite, 5000);
    if (rStatus != CY_SUCCESS){
        CyClose (handle);
        D(printf ("Error in doing SPI data write data Write is %d data read is %d\n" , dataBufferWrite.transferCount,dataBufferRead.transferCount));
        return CY_ERROR_REQUEST_FAILED;
    }

    spiWaitForIdle (handle);
    //Write SPI read command
    wbuffer[0] = 0x03;
    dataBufferRead.length =  (4 + readWriteLength);
    dataBufferWrite.length = (4 + readWriteLength);

    rStatus = CySpiReadWrite (handle, &dataBufferRead, &dataBufferWrite, 5000);
    if (rStatus != CY_SUCCESS){
        CyClose (handle);
        D(printf ("The Error is %d \n", rStatus));
        D(printf ("Error in doing SPI data write data Write is %d data read is %d\n" , dataBufferWrite.transferCount,dataBufferRead.transferCount));
        return CY_ERROR_REQUEST_FAILED;
    }
    D(printf ("Data Read back is \n"));
    for (rStatus = 4; rStatus < (readWriteLength + 4); rStatus++){
        D(printf ("%x ",rbuffer[rStatus]));
        if (rbuffer[rStatus] != wbuffer[rStatus]){
            isVerify = false;
        }
    }
	/*
    if (isVerify)
        printf ("Data verified successfully \n");
    else
        printf ("Data corruption occured!!\n");
	*/

    CyClose (handle);
    return CY_SUCCESS;
}

int i2cVerifyData (int deviceNumber, int interfaceNum)
{
    CY_DATA_BUFFER dataBufferWrite, dataBufferRead;
    CY_HANDLE handle;
    int length = 0;
    bool isVerify = true;
    int loopCount = 100, i;
    CY_RETURN_STATUS rStatus;
    unsigned char bytesPending = 0, address[2], wbuffer[66], rbuffer[66];
    CY_I2C_DATA_CONFIG i2cDataConfig;

    memset (wbuffer, 0, 66);
    memset (rbuffer, 0, 66);

    i2cDataConfig.isStopBit = true;
    i2cDataConfig.slaveAddress = 0x51;

    rStatus = CyOpen (deviceNumber, interfaceNum, &handle);
    if (rStatus != CY_SUCCESS){
        D(printf("CY_I2C: Open failed \n"));
        return rStatus;
   }
    loopCount = 100;
    length = readWriteLength;
    wbuffer[0]= pageAddress;
    wbuffer[1] = 0;
    dataBufferWrite.buffer = wbuffer;
    i2cDataConfig.isStopBit = true;
    dataBufferWrite.length = (length + 2);
    D(printf ("\n Data that is written on to i2c ...\n"));
    for (i = 2; i < (length +2); i++){
        wbuffer[i] = rand() % 256;
        D(printf ("%x ", wbuffer[i]));
    }
    rStatus = CyI2cWrite (handle, &i2cDataConfig, &dataBufferWrite, 5000);
    if (rStatus != CY_SUCCESS){
        D(printf ("Error in doing i2c write \n"));
        CyClose (handle);
        return -1;
    }
    //We encountered a error in I2C read repeat the procedure again
    //Loop here untill Read vendor command passes
    i2cDataConfig.isStopBit = false;
    dataBufferWrite.length = 2;

    do {
        rStatus = CyI2cWrite (handle, &i2cDataConfig, &dataBufferWrite, 5000);
        loopCount--;
    }while (rStatus != CY_SUCCESS && loopCount != 0);

    if (loopCount == 0 && rStatus != CY_SUCCESS){
        D(printf ("Error in sending read command \n"));
        CyClose (handle);
        return -1;
    }

    dataBufferRead.buffer = rbuffer;
    rbuffer[0]= address[0];
    rbuffer[1] = 0;
    i2cDataConfig.isStopBit = true;
    i2cDataConfig.isNakBit = true;
    dataBufferRead.length = length;
    dataBufferRead.buffer = rbuffer;

    memset (rbuffer, 0, 64);

    rStatus = CyI2cRead (handle, &i2cDataConfig, &dataBufferRead, 5000);
    if (rStatus != CY_SUCCESS){
        D(printf ("Error in doing i2c read ... Error is %d \n", rStatus));
        CyClose (handle);
        return -1;
    }

    D(printf ("\n Data that is read from i2c ...\n"));
    for (rStatus = 0; rStatus < length; rStatus++){
        printf ("%x ", rbuffer[rStatus]);
        if (rbuffer[rStatus] != wbuffer[rStatus + 2]){
            isVerify = false;
        }
    }
	
	/*
    if (!isVerify)
        printf ("Data corruption occured ..!!!\n");
    else
        printf ("Data verified successfully \n");
	*/

    CyClose (handle);
}

CY_RETURN_STATUS cyAPIInit(int lightSensorType)
{
    CY_RETURN_STATUS rStatus;
	isNewLED = lightSensorType;
	if (lightSensorType == 0)
	{
		aSlaveAddress7bit = aSlaveAddress7bitOLD;
		lightSensorPowerOnCommand = 0xA0;
		lightSensorPowerOnData = 0x03;
		lightSensorReadSensorValueCommand = 0xAC;
		lightSensorPowerOffData = 0x00;
	}
	else
	{
		aSlaveAddress7bit = aSlaveAddress7bitNEW;
		lightSensorPowerOnCommand = 0xA0;
		lightSensorPowerOnData = 0x03;
		lightSensorReadSensorValueCommand = 0xB4;
		lightSensorPowerOffData = 0x00;
	}
	
	fflush(stdout);
	setvbuf(stdout, NULL, _IONBF, 0);
	freopen("./my.log", "a", stdout); //打印到my.log文件

    glDevice = (CY_DEVICE_STRUCT *)malloc (CY_MAX_DEVICES *sizeof (CY_DEVICE_STRUCT));
    if (glDevice == NULL){
        D(printf ("Memory allocation failed ...!! \n"));
        return -1;
    }
    rStatus = CyLibraryInit ();
    if (rStatus != CY_SUCCESS) {
        D(printf ("CY:Error in Doing library init Error NO:<%d> \n", rStatus));
        return rStatus;
    }
    rStatus = CyGetListofDevices (&numDevices);
    if (rStatus != CY_SUCCESS) {
        D(printf ("CY:Error in Getting List of Devices: Error NO:<%d> \n", rStatus));
        return rStatus;
    }
    printListOfDevices(false);
    
    DEVICE0_NUM = glDevice[0].deviceNumber;

    int ProjectgorEnable = 1;
	rStatus = SetProjectorOnOff(DEVICE0_NUM, GPIO_IF_NUM, ProjectgorEnable);

	int LedEnableRed = 0, LedEnableGreen = 1, LedEnableBlue = 0;
	rStatus = GetLedOnOff(DEVICE0_NUM, I2C_IF_NUM, &LedEnableRed, &LedEnableGreen, &LedEnableBlue);  //dummy read

	sleep(1); //waiting for LE is ready!

	LedEnableRed = 0; LedEnableGreen = 1; LedEnableBlue = 0;
	rStatus = GetLedOnOff(DEVICE0_NUM, I2C_IF_NUM, &LedEnableRed, &LedEnableGreen, &LedEnableBlue);  //dummy read checking
	if (rStatus == CY_SUCCESS)
	{
		//printf("\nSuccess to turn on LED.");
		return CY_SUCCESS;
	}
  	
  	//if i2c communication fail, then do hot plug procedures
  	rStatus = ResetCypressDevice(DEVICE0_NUM, I2C_IF_NUM);
	if (rStatus != CY_SUCCESS)
	{
		D(printf("Failed to reset i2c device.\n"));
		CyLibraryExit ();
		free (glDevice);
		return -1;
	}

	CyLibraryExit ();
	sleep(1); //waiting for hot plug is ready !

	rStatus = CyLibraryInit ();
    if (rStatus != CY_SUCCESS) {
        D(printf ("CY:Error in Doing library init Error NO:<%d> \n", rStatus));
        return rStatus;
    }
    rStatus = CyGetListofDevices (&numDevices);
    if (rStatus != CY_SUCCESS) {
        D(printf ("CY:Error in Getting List of Devices: Error NO:<%d> \n", rStatus));
        return rStatus;
    }
	printListOfDevices(false);

    DEVICE0_NUM = glDevice[0].deviceNumber;

	return rStatus;
}

CY_RETURN_STATUS FlashBlockReadMask(char *str,char *lightengineSN)
{
    //SPI Flash memory map
    #define ADDR_SNUM 0			//Serial number ; 19 bytes
    #define ADDR_LEDC 43		//LED current	; 4 bytes
    #define ADDR_LGHT 51		//Light sensor value at dark frame ; 4bytes
    #define ADDR_MASK 0x10000	//maske file start address

    int len = 0;
    int i;
    char *buffer = NULL;
    FILE *pFile;
    char header_buf[] = { 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00}; //4bytes file length and 4bytes file check sum
    char *png_buf = NULL;
    int status;
    UINT32 png_len = 0;
    UINT32 png_cksum = 0;
    char *sn = NULL;
    int ProjectgorEnable = 0;

    buffer = (char *)malloc(128);
    status = FlashBlockRead(DEVICE0_NUM, SPI_IF_NUM, 0x00000, 128, buffer);
    if (status != CY_SUCCESS)
    {
        ProjectgorEnable = 0;
	status = SetProjectorOnOff(DEVICE0_NUM, GPIO_IF_NUM, ProjectgorEnable);
	if (status != CY_SUCCESS)
	{
		lightengineSN = NULL;
		return -1;
	}
	lightengineSN = NULL;
	return -1;
    }   
    sn = (char *)malloc(19+5);
    for (i = 0; i < 19; i++)
	sn[i] = buffer[i];

    sn[19] = 0x00;
    memcpy(lightengineSN, sn, 19);

    //Reading LED power from buffer
    float DI = 5.8593; //mA per digital
    float LedCurrent;  
    LedCurrent = (((UCHAR)buffer[ADDR_LEDC + 3] << 24 | (UCHAR)buffer[ADDR_LEDC + 2] << 16 | (UCHAR)buffer[ADDR_LEDC + 1] << 8 | (UCHAR)buffer[ADDR_LEDC])*DI)/1000.0;

    //Reading light sensor value from buffer
    int LightSen;
    LightSen = (UCHAR)buffer[ADDR_LGHT + 3] << 24 | (UCHAR)buffer[ADDR_LGHT + 2] << 16 | (UCHAR)buffer[ADDR_LGHT + 1] << 8 | (UCHAR)buffer[ADDR_LGHT];

    //Saving the mask file
    sn[19] = 0x2e;//char(".");
    sn[20] = 0x74;//char("t");
    sn[21] = 0x78;//char("x");
    sn[22] = 0x74;//char("t");
    sn[23] = 0x00;

    pFile = fopen(sn, "w");
    if(NULL == pFile)
    {
	ProjectgorEnable = 0;
	status = SetProjectorOnOff(DEVICE0_NUM, GPIO_IF_NUM, ProjectgorEnable);
	if (status != CY_SUCCESS)
	{
		return -1;
	}
	return -1;
    }
    else{
	fprintf(pFile, "****** Light Engine parameters ********\n");
	fprintf(pFile, "LED current(A): %2.2f\n", LedCurrent);
	fprintf(pFile, "Light Sensor  : %d\n", LightSen);
    }
    fclose(pFile);


    //Reading mask file Lenght and check sum from SPI Flash
    status = FlashBlockRead(DEVICE0_NUM, SPI_IF_NUM, ADDR_MASK, 8, header_buf);
    if (status != CY_SUCCESS)
    {		
        ProjectgorEnable = 0;
	status = SetProjectorOnOff(DEVICE0_NUM, GPIO_IF_NUM, ProjectgorEnable);
	if (status != CY_SUCCESS)
	{
	    return -1;
	}
	return -1;
    }
    png_len = header_buf[0] & 0xff | header_buf[1] << 8 & 0xff00 | header_buf[2] << 16 & 0xff0000 | header_buf[3] << 24 & 0xff000000;
    png_cksum = header_buf[4] & 0xff | header_buf[5] << 8 & 0xff00 | header_buf[6] << 16 & 0xff0000 | header_buf[7] << 24 & 0xff000000;


    //png_buf = new char[png_len];
    png_buf = (char*)malloc(png_len);
    status = FlashBlockRead(DEVICE0_NUM, SPI_IF_NUM, ADDR_MASK + 8, png_len, png_buf);
    if (status != CY_SUCCESS)
    {
	ProjectgorEnable = 0;
	status = SetProjectorOnOff(DEVICE0_NUM, GPIO_IF_NUM, ProjectgorEnable);
	if (status != CY_SUCCESS)
	{
	    return -1;
	}
	return -1;
     }

    UINT32 cksum = 0;
    for (i = 0; i < png_len; i++)
    {
	cksum += png_buf[i] & 0xff;
    }

    if (cksum==0 || cksum != png_cksum)
    {
	ProjectgorEnable = 0;
	status = SetProjectorOnOff(DEVICE0_NUM, GPIO_IF_NUM, ProjectgorEnable);
	if (status != CY_SUCCESS)
	{
	    return -1;
	}
	return -1;
    }

    //Saving the mask file
    sn[19] = 0x2e;//char(".");
    sn[20] = 0x70;//char("p");
    sn[21] = 0x6e;//char("n");
    sn[22] = 0x67;//char("g");
    sn[23] = 0x00;
    
    strcat(str,sn);
    pFile = fopen(str, "wb");

    if (NULL == pFile){
	ProjectgorEnable = 0;
	status = SetProjectorOnOff(DEVICE0_NUM, GPIO_IF_NUM, ProjectgorEnable);
	if (status != CY_SUCCESS)
	{
	    return -1;
	}
        return -1;
    }
    else{
	fwrite(png_buf, 1, png_len, pFile);
    }
    fclose(pFile);
    free(png_buf);
    return 0;		
}

void freegl()
{
    free (glDevice);
}

CY_RETURN_STATUS I2CSetCRC16OnOff(int deviceNumber, int interfaceNum, bool enable)
{
	CY_RETURN_STATUS rStatus;

	int cWRITESIZE = 2;
	UINT8* sendBuf;

	sendBuf = (UINT8*)malloc(cWRITESIZE);

	sendBuf[0] = WRITE_FPGA_CONTROL;  //CAh
	if (enable)
	{
		sendBuf[1] = 0x04;
	}
	else
	{
		sendBuf[1] = 0x00;
	}

	rStatus = I2CWrite(deviceNumber, interfaceNum, cSlaveAddress7bit, cWRITESIZE, sendBuf);
	if (rStatus != CY_SUCCESS)
	{
		puts("## I2CSetCRC16OnOff: I2CWrite Fail ##");
		free(sendBuf);
		return rStatus;
	}
	puts("## I2CSetCRC16OnOff: I2CWrite succeed ##");
	free(sendBuf);
	return rStatus;
}

CY_RETURN_STATUS I2CSetActiveBuffer(int deviceNumber, int interfaceNum, bool activebuf)
{
	CY_RETURN_STATUS rStatus;

	int cWRITESIZE = 2;
	UINT8* sendBuf;

	sendBuf = (UINT8*)malloc(cWRITESIZE);

	sendBuf[0] = WRITE_ACTIVE_BUFFER;   //C5h
	if (activebuf)
	{
		sendBuf[1] = 0x01;
	}
	else
	{
		sendBuf[1] = 0x00;
	}

	rStatus = I2CWrite(deviceNumber, interfaceNum, cSlaveAddress7bit, cWRITESIZE, sendBuf);
	if (rStatus != CY_SUCCESS)
	{
		puts("## I2CSetActiveBuffer: I2CWrite Fail ##");
		free(sendBuf);
		return rStatus;
	}
	puts("## I2CSetActiveBuffer: I2CWrite succeed ##");
	free(sendBuf);
	return rStatus;
}

CY_RETURN_STATUS I2cSetInputSource(int deviceNumber, int interfaceNum, int select)
{
	CY_RETURN_STATUS rStatus;
	int cWRITESIZE = 2;
	UINT8* sendBuf;


	/*if( !WaitForI2cIdle(dN) )
		return -1;*/


	sendBuf = (UINT8*)malloc(cWRITESIZE);

	sendBuf[0] = WRITE_INPUT_SOURCE;
	sendBuf[1] = select;

	rStatus = I2CWrite(deviceNumber, interfaceNum, cSlaveAddress7bit, cWRITESIZE, sendBuf);
	if (rStatus != CY_SUCCESS)
	{
		puts("## I2cSetInputSource: I2CWrite Fail ##");
		free(sendBuf);
		return rStatus;
	}
	puts("## I2cSetInputSource: I2CWrite succeed ##");
	free(sendBuf);
	return rStatus;
}

CY_RETURN_STATUS I2CSetExternalPrintConfiguration(int deviceNumber, int interfaceNum, int para1, int para2)
{
	CY_RETURN_STATUS rStatus;

	int cWRITESIZE = 3;
	UINT8* sendBuf;

	sendBuf = (UINT8*)malloc(cWRITESIZE);

	sendBuf[0] = WRITE_EXTERNAL_PRINT_CONFIGURATION;   //A8h
	sendBuf[1] = para1;
	sendBuf[2] = para2;

	rStatus = I2CWrite(deviceNumber, interfaceNum, cSlaveAddress7bit, cWRITESIZE, sendBuf);
	if (rStatus != CY_SUCCESS)
	{
		puts("## I2CSetExternalPrintConfiguration: I2CWrite Fail ##");
		return rStatus;
		free(sendBuf);
	}
	puts("## I2CSetExternalPrintConfiguration: I2CWrite succeed ##");
	free(sendBuf);
	return rStatus;
}

CY_RETURN_STATUS I2CSetParallelBuffer(int deviceNumber, int interfaceNum, int para)
{
	CY_RETURN_STATUS rStatus;

	int cWRITESIZE = 2;
	UINT8* sendBuf;

	sendBuf = (UINT8*)malloc(cWRITESIZE);

	sendBuf[0] = WRITE_PARALLEL_VIDEO;   //C3h
	sendBuf[1] = para;

	rStatus = I2CWrite(deviceNumber, interfaceNum, cSlaveAddress7bit, cWRITESIZE, sendBuf);
	if (rStatus != CY_SUCCESS)
	{
		puts("## I2CSetParallelBuffer: I2CWrite Fail ##");
		return rStatus;
	}
	puts("## I2CSetParallelBuffer: I2CWrite succeed ##");
	return rStatus;
}

CY_RETURN_STATUS I2CSetExternalPrintControl(int deviceNumber, int interfaceNum, int para1, int para2, int para3, int para4, int para5)
{
	CY_RETURN_STATUS rStatus;

	int cWRITESIZE = 6;
	UINT8* sendBuf;

	sendBuf = (UINT8*)malloc(cWRITESIZE);

	sendBuf[0] = WRITE_EXTERNAL_PRINT_CONTROL;   //C1h
	sendBuf[1] = para1;
	sendBuf[2] = para2;
	sendBuf[3] = para3;
	sendBuf[4] = para4;
	sendBuf[5] = para5;

	rStatus = I2CWrite(deviceNumber, interfaceNum, cSlaveAddress7bit, cWRITESIZE, sendBuf);
	if (rStatus != CY_SUCCESS)
	{
		puts("## I2CSetExternalPrintControl: I2CWrite Fail ##");
		return rStatus;
	}
	puts("## I2CSetExternalPrintControl: I2CWrite succeed ##");
	return rStatus;
}

CY_RETURN_STATUS GpioGetSpirdyBusy(int deviceNumber, int interfaceNum, bool* isBusy)
{
	CY_RETURN_STATUS rStatus;
	UINT8 SPI_RDY = 5;
	rStatus = GpioRead(deviceNumber, interfaceNum, SPI_RDY, isBusy);  //GPIO5
	if (rStatus != CY_SUCCESS)
	{
		puts("## GpioGetSpirdyBusy: GpioRead Fail ##");
		return rStatus;
	}
	//puts("## GpioGetSpirdyBusy: GpioRead succeed ##");
	*isBusy = !*isBusy;
	return rStatus;
}

void Check_SPI_RDY_Busy(int deviceNumber, int interfaceNum)
{
	bool isBusy = true;
	while (true)
	{
		GpioGetSpirdyBusy(deviceNumber, interfaceNum, &isBusy);
		if (isBusy == false)
		{
			puts("SPI_RDY Get Ready ! ");
			break;
		}
	}
}

CY_RETURN_STATUS GpioGetSysrdyBusy(int deviceNumber, int interfaceNum, bool* isBusy)
{
	CY_RETURN_STATUS rStatus;
	UINT8 SYS_RDY = 6;
	
	rStatus = GpioRead(deviceNumber, interfaceNum, SYS_RDY, isBusy);  //GPIO6
	if (rStatus != CY_SUCCESS)
	{
		puts("## GpioGetSysrdyBusy: GpioRead Fail ##");
		return rStatus;
	}
	//puts("## GpioGetSysrdyBusy: GpioRead succeed ##");
	*isBusy = !*isBusy;
	return rStatus;
}

void Check_SYS_RDY_Busy(int deviceNumber, int interfaceNum)
{
	bool isBusy = true;
	while (true)
	{
		GpioGetSysrdyBusy(deviceNumber, interfaceNum, &isBusy);
		if (isBusy == false)
		{
			puts("SYS_RDY Get Ready ! ");
			break;
		}
	}
}



int SPIPrint(int dN, int frames, char* imageFile, int layer_num)
{
	fflush(stdout);
	setvbuf(stdout, NULL, _IONBF, 0);
	freopen("/home/pi/log/my.log", "a", stdout); //打印到my.log文件

	int ret = 0;
	bool flagbuf = false;

	char framesLow = 0;
	char framesHigh = 0;

	spi_dev0 = yo_spi_init(0, 0);
	spi* spi_dev;
	spi_dev = spi_dev0;
	yo_spi_set_mode(spi_dev, 0);
	yo_spi_set_bits_per_word(spi_dev, 8);
	yo_spi_set_speed(spi_dev, 48000000); //48MHz

	///step 1
	ret = I2CSetCRC16OnOff(dN, I2C_IF_NUM, true);
	if (ret != 0)
		return -1;

	///step 2
	if ((layer_num % 2) == 0)
		flagbuf = false;
	else
		flagbuf = true;
	ret = I2CSetActiveBuffer(dN, I2C_IF_NUM, flagbuf);  //set active buffer 0(Odd Print Layer)
	flagbuf = !flagbuf;
	if (ret != 0)
		return -1;

	usleep(1000);
	///step 3-1
	ret = I2cSetInputSource(dN, I2C_IF_NUM, 0xFF);  //set standby mode
	if (ret != 0)
		return -1;

	usleep(500000);  //500ms
///step 3-2
	ret = I2CSetExternalPrintConfiguration(dN, I2C_IF_NUM, 0x00, 0x04);  //set LED3 enable
	if (ret != 0)
		return -1;

	usleep(5000);  //5ms
///step 4
	//++icycle;
	ret = yo_spidatastream_write(dN, imageFile);  //SPI data stream transmission, send the data and waiting for the SPI_RDY pull high
	if (ret != 0)
		return -1;

	//if (icycle > 3) icycle = 0;

	Check_SPI_RDY_Busy(dN, GPIO_IF_NUM);   //waiting for the SPI_RDY get ready(high)

///step 5
	ret = I2CSetActiveBuffer(dN, I2C_IF_NUM, flagbuf);   //change active buffer to another buffer(Even print layer)
	if (ret != 0)
		return -1;

	usleep(5000);  //5ms
///step 6
	ret = I2CSetParallelBuffer(dN, I2C_IF_NUM, 0x01);  //read and send buffer
	if (ret != 0)
		return -1;

	usleep(5000);  //5ms
///step 7
	ret = I2cSetInputSource(dN, I2C_IF_NUM, 0x06);  //set External Print mode, and waiting for the SYS_RDY pull high
	if (ret != 0)
		return -1;

	usleep(5000);  //5ms
	Check_SYS_RDY_Busy(dN, GPIO_IF_NUM);  //waiting for the SYS_RDY get ready(high)

	framesLow = (char)(frames & 0xff);
	framesHigh = (char)((frames >> 8) & 0xff);

	puts(" ");

	printf("The curing time is  %.2f s.(%d/60 s)\n ", frames / 60.0, frames);

	ret = I2CSetExternalPrintControl(dN, I2C_IF_NUM, 0x00, 0x05, 0x00, framesLow, framesHigh);  //set External Print Layer Control and start print
	if (ret != 0)
		return -1;

	usleep((long)((frames / 60.0) * 1000000.0));
	ret = I2cSetInputSource(dN, I2C_IF_NUM, 0xFF);  //set standby mode
	if (ret != 0)
		return -1;
	return 0;
}

int yo_spidatastream_write(int dN, char* imageFile)
{
	//1440P 2560x1440=3687478, bmp file include header(1078bytes) and image data(3686400).
	int sdata_size;
	unsigned char* pStream_data;
	FILE* fp;

	fp = fopen(imageFile, "rb");

	if (fp == NULL) {
		return -1;
	}
	else {   //write data stream to fpga
		sdata_size = 3687478; //(int *)sdata;
		pStream_data = (unsigned char*)malloc((unsigned long)sdata_size);
		if (pStream_data == NULL) {
			fclose(fp);
			free(pStream_data);
			return -1;
		}
		else {
			fread(pStream_data, 1, (unsigned long)sdata_size, fp);

			if ((SPIWriteData(sdata_size, (char*)pStream_data)) != 0) {
				puts("SPIWriteData fail");
				free(pStream_data);
				return 1;
			}
			fclose(fp);
		}
	}
	free(pStream_data);
	return 0;
}

static int SPIWriteData(int data_len, char* data)
{
	int buffer_size = 1600; //1600
	int rStatus;
	unsigned char wbuffer[buffer_size + 14];
	int i;
	int buffer_tmp = 0;
	int bmpoffset = 1078; //bmp file header 1078; from 0x436
	struct data_stream ds;

	spi* spi_dev;
	spi_dev = spi_dev0;

	ds.commandop = 0x04;
	ds.col_start_index = 0;  //bit 12~8 : 00000
	ds.col_end_index = 19;    //bit 17~13 : 10011
	ds.row_start_index = 0; //bit 28~18 ;
	ds.rdummy = 0b0000000;//bit 35~29 ;
	ds.datacheck = 0b1111; //bit 39~36

	ds.dummy = 0x00;

	wbuffer[0] = ds.commandop;
	wbuffer[1] = (ds.col_end_index << 5) | (ds.col_start_index); // 3 + 5
	wbuffer[2] = (ds.row_start_index << 2) | (ds.col_end_index >> 3); // 6 + 2
	wbuffer[3] = ((ds.row_start_index >> 3) & 0xf1) | ((ds.rdummy) & 0x07); // 5 + 3
	wbuffer[4] = (ds.datacheck << 4) | (ds.rdummy >> 3); // 4 + 4
	//wbuffer[1] = 0x60;    //wbuffer[2] = 0x02;    //wbuffer[3] = 0x00;    //wbuffer[4] = 0xF1;

	wbuffer[5] = ds.dummy;

	wbuffer[6] = (data_len - bmpoffset) & 0xff;     // little endian --> low first
	wbuffer[7] = (data_len - bmpoffset) >> 8 & 0xff;
	wbuffer[8] = (data_len - bmpoffset) >> 16 & 0xff;
	wbuffer[9] = (data_len - bmpoffset) >> 24 & 0xff;

	for (buffer_tmp = 0; buffer_tmp < (data_len - bmpoffset); buffer_tmp += buffer_size)
	{
		if (buffer_tmp == 0)
		{
			memcpy(wbuffer + 10, data + bmpoffset, buffer_size);

			if (buffer_size < (data_len - bmpoffset))
			{
				rStatus = yo_spi_write(spi_dev, wbuffer, (buffer_size + 10));
				if (rStatus != 0) {
					puts("Error in doing SPI data program!");
					return rStatus;
				}
			}
			else
			{
				wbuffer[buffer_size + 10] = 0x12; //crc16[0];
				wbuffer[buffer_size + 11] = 0x34; //crc16[1];
				wbuffer[buffer_size + 12] = 0x00; //dummy byte
				wbuffer[buffer_size + 13] = 0x00; //dummy byte

				rStatus = yo_spi_write(spi_dev, wbuffer, (buffer_size + 14));
				if (rStatus != 0) {
					puts("Error in doing SPI data program!");
					return rStatus;
				}
			}
		}
		else if (buffer_tmp < (data_len - bmpoffset - buffer_size))
		{
			memcpy(wbuffer + 6, data + bmpoffset + buffer_tmp, buffer_size);

			rStatus = yo_spi_write(spi_dev, wbuffer, (buffer_size + 6));
			if (rStatus != 0) {
				puts("Error in doing SPI data program!");
				return rStatus;
			}

		}
		else //when last buffer_size
		{
			buffer_size = data_len - bmpoffset - buffer_tmp;
			memcpy(wbuffer + 6, data + bmpoffset + buffer_tmp, buffer_size);

			wbuffer[buffer_size + 6] = 0x12; //crc16[0];
			wbuffer[buffer_size + 7] = 0x34; //crc16[1];
			wbuffer[buffer_size + 8] = 0x00; //dummy byte
			wbuffer[buffer_size + 9] = 0x00; //dummy byte

			rStatus = yo_spi_write(spi_dev, wbuffer, (buffer_size + 10));
			if (rStatus != 0) {
				puts("Error in doing SPI data program!");
				return rStatus;
			}
		}
	}

	return 0;
}
