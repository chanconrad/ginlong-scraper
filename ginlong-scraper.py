import os
import time
import urllib.parse
import urllib.request
from datetime import datetime

import requests
from dateutil.tz import tzlocal
from influxdb_client import InfluxDBClient, Point

# solis/ginlong portal config
GINLONG_USERNAME = os.getenv("GINLONG_USERNAME")  # your portal username
GINLONG_PASSWORD = os.getenv("GINLONG_PASSWORD")  # your portal password
GINLONG_DOMAIN = "m.ginlong.com"  # domain ginlong used multiple domains with same login but different versions, could change anytime. monitoring.csisolar.com, m.ginlong.com
GINLONG_LANGUAGE = "2"  # lanuage (2 = English)
GINLONG_DEVICE_ID = "deviceid"  # your deviceid, if set to deviceid it will try to auto detect, if you have more then one device then specify.

# Influx settings
INFLUX_URL = os.getenv("INFLUX_URL")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN")
INFLUX_ORG = os.getenv("INFLUX_ORG")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET")
INFLUX_MEASUREMENT = os.getenv("INFLUX_MEASUREMENT")

# Create session for requests
session = requests.session()

# building url
url = "https://" + GINLONG_DOMAIN + "/cpro/login/validateLogin.json"
params = {
    "userName": GINLONG_USERNAME,
    "password": GINLONG_PASSWORD,
    "lan": GINLONG_LANGUAGE,
    "domain": GINLONG_DOMAIN,
    "userType": "C",
}

# default heaeders gives a 403, seems releted to the request user agent, so we put curl here
headers = {"User-Agent": "curl/7.58.0"}

# login call
resultData = session.post(url, data=params, headers=headers)

resultJson = resultData.json()
if resultJson["result"].get("isAccept") == 1:
    print("Login Succesful on", GINLONG_DOMAIN, "!")
else:
    print("Login Failed on", GINLONG_DOMAIN, "!!")
    exit()

if GINLONG_DEVICE_ID == "deviceid":
    print("")
    print("Your deviceId is not set, auto detecting")
    url = "http://" + GINLONG_DOMAIN + "/cpro/epc/plantview/view/doPlantList.json"

    cookies = {"language": GINLONG_LANGUAGE}
    resultData = session.get(url, cookies=cookies, headers=headers)
    resultJson = resultData.json()

    plantId = resultJson["result"]["pagination"]["data"][0]["plantId"]

    url = "http://" + GINLONG_DOMAIN + "/cpro/epc/plantDevice/inverterListAjax.json?"
    params = {"plantId": int(plantId)}

    cookies = {"language": GINLONG_LANGUAGE}
    resultData = session.get(url, params=params, cookies=cookies, headers=headers)
    resultJson = resultData.json()

    # .result.paginationAjax.data
    deviceId = resultJson["result"]["paginationAjax"]["data"][0]["deviceId"]

    print("Your deviceId is ", deviceId)


# get device details
url = "http://" + GINLONG_DOMAIN + "/cpro/device/inverter/goDetailAjax.json"
params = {"deviceId": int(deviceId)}

cookies = {"language": GINLONG_LANGUAGE}
resultData = session.get(url, params=params, cookies=cookies, headers=headers)
resultJson = resultData.json()

# Get values from json
data = {}
data["updateDate"] = resultJson["result"]["deviceWapper"].get("updateDate")
data["DC_Voltage_PV1"] = resultJson["result"]["deviceWapper"]["dataJSON"].get("1a")
data["DC_Voltage_PV2"] = resultJson["result"]["deviceWapper"]["dataJSON"].get("1b")
data["DC_Current_PV1"] = resultJson["result"]["deviceWapper"]["dataJSON"].get("1j")
data["DC_Current_PV2"] = resultJson["result"]["deviceWapper"]["dataJSON"].get("1k")
data["AC_Voltage"] = resultJson["result"]["deviceWapper"]["dataJSON"].get("1ah")
data["AC_Current"] = resultJson["result"]["deviceWapper"]["dataJSON"].get("1ak")
data["AC_Power"] = resultJson["result"]["deviceWapper"]["dataJSON"].get("1ao")
data["AC_Frequency"] = resultJson["result"]["deviceWapper"]["dataJSON"].get("1ar")
data["DC_Power_PV1"] = resultJson["result"]["deviceWapper"]["dataJSON"].get("1s")
data["DC_Power_PV2"] = resultJson["result"]["deviceWapper"]["dataJSON"].get("1t")
data["Inverter_Temperature"] = resultJson["result"]["deviceWapper"]["dataJSON"].get(
    "1df"
)
data["Daily_Generation"] = resultJson["result"]["deviceWapper"]["dataJSON"].get("1bd")
data["Monthly_Generation"] = resultJson["result"]["deviceWapper"]["dataJSON"].get("1be")
data["Annual_Generation"] = resultJson["result"]["deviceWapper"]["dataJSON"].get("1bf")
data["Total_Generation"] = resultJson["result"]["deviceWapper"]["dataJSON"].get("1bc")
data["Generation_Last_Month"] = resultJson["result"]["deviceWapper"]["dataJSON"].get(
    "1ru"
)

timestamp = int((data["updateDate"]) / 1000)

dt = time.time() - timestamp
if dt < 600:
    print("Results are ", dt, " seconds old")
    niceTimestamp = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime(timestamp))

    # Print collected values
    print("results from", GINLONG_DOMAIN)
    print("")
    print(niceTimestamp)
    print("")
    for key in data:
        print(f"{key}: {data[key]}")
    print("")

    # Write to Influxdb

    influx_data = {}
    influx_data["DC_Voltage"] = float(data["DC_Voltage_PV1"])
    influx_data["DC_Current"] = float(data["DC_Current_PV1"])
    influx_data["AC_Voltage"] = float(data["AC_Voltage"])
    influx_data["AC_Current"] = float(data["AC_Current"])
    influx_data["AC_Power"] = float(data["AC_Power"])
    influx_data["AC_Frequency"] = float(data["AC_Frequency"])
    influx_data["Inverter_Temperature"] = float(data["Inverter_Temperature"])

    units = {}
    units["DC_Voltage"] = "V"
    units["DC_Current"] = "A"
    units["AC_Voltage"] = "V"
    units["AC_Current"] = "A"
    units["AC_Power"] = "W"
    units["AC_Frequency"] = "Hz"
    units["Inverter_Temperature"] = "°C"

    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = client.write_api()

    for key in influx_data:
        t = datetime.fromtimestamp(timestamp, tz=tzlocal())
        p = (
            Point(INFLUX_MEASUREMENT)
            .field(key, influx_data[key])
            .tag("units", units[key])
            .time(t)
        )
        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=p)

    # Flush write
    write_api.close()
